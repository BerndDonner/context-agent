from __future__ import annotations

import shutil
from pathlib import Path

import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError

from context_agent.errors import ConfigurationError
from context_agent.models import JobConfig, JobMode, ResolvedInput, ResolvedJob
from context_agent.template import split_template


def _resolve_inside(root: Path, value: str, *, label: str) -> Path:
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ConfigurationError(f"{label} escapes the job directory: {value}") from exc
    return candidate


def _resolve_external(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def _require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise ConfigurationError(f"{label} does not exist or is not a file: {path}")


def load_job(job_directory: Path) -> ResolvedJob:
    root = job_directory.expanduser().resolve()
    if not root.is_dir():
        raise ConfigurationError(f"job directory does not exist: {root}")

    config_path = root / "job.yaml"
    _require_file(config_path, "job.yaml")
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigurationError(f"cannot read {config_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigurationError("job.yaml must contain a YAML mapping")
    try:
        config = JobConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigurationError(str(exc)) from exc

    task_path = _resolve_inside(root, config.task, label="task")
    template_path = _resolve_inside(root, config.template.path, label="template")
    _require_file(task_path, "task")
    _require_file(template_path, "template")
    source_path = None
    if config.mode == JobMode.IMPROVE:
        assert config.source is not None
        source_path = _resolve_inside(root, config.source.path, label="source")
        _require_file(source_path, "source")
        if source_path.suffix.lower() != ".tex":
            raise ConfigurationError("improve source must be a .tex file")
        if source_path.is_relative_to(root / "result"):
            raise ConfigurationError("improve source must not be inside result/")
        if source_path == template_path:
            raise ConfigurationError("improve source must be independent of template")

    try:
        split_template(template_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigurationError(f"invalid ConTeXt template: {exc}") from exc

    resolved_inputs: list[ResolvedInput] = []
    for item in config.inputs:
        path = _resolve_inside(root, item.path, label="input")
        _require_file(path, f"input {item.path}")
        resolved_inputs.append(
            ResolvedInput(
                path=path,
                relative_path=item.path,
                role=item.role,
                policy=item.policy,
            )
        )

    references: list[Path] = []
    for reference in config.references:
        path = _resolve_inside(root, reference, label="reference")
        _require_file(path, f"reference {reference}")
        references.append(path)

    # A reference-based exception to numerical preservation must be explicitly
    # approved in the versioned job configuration, and must identify one of the
    # actual provided PDF sources and a valid page. Never trust a model claim.
    if config.review.reference_resolutions:
        import fitz
        for approval in config.review.reference_resolutions:
            ref = _resolve_inside(root, approval.reference, label="resolution reference")
            if ref not in references or ref.suffix.lower() != ".pdf":
                raise ConfigurationError("approved resolution must cite a configured PDF reference")
            try:
                with fitz.open(ref) as pdf:
                    if approval.page > len(pdf):
                        raise ConfigurationError("approved reference page does not exist")
            except (RuntimeError, OSError) as exc:
                raise ConfigurationError("cannot verify approved reference PDF") from exc
            if source_path is None or approval.source_line > len(source_path.read_text(encoding="utf-8").splitlines()) or approval.before not in source_path.read_text(encoding="utf-8").splitlines()[approval.source_line - 1]:
                raise ConfigurationError("approved resolution does not match source_line")
            if approval.before == approval.after:
                raise ConfigurationError("resolution must name a real source change")

    include_dir = root / "include"
    if not include_dir.exists():
        include_dir.mkdir()
    elif not include_dir.is_dir():
        raise ConfigurationError(f"include is not a directory: {include_dir}")

    result_dir = root / "result"
    result_dir.mkdir(exist_ok=True)

    context_archive = _resolve_external(root, config.runtime.context_archive)
    _require_file(context_archive, "ConTeXt archive")

    quality_directory: Path | None = None
    if config.quality_directory:
        quality_directory = _resolve_external(root, config.quality_directory)
        if not quality_directory.is_dir():
            raise ConfigurationError(f"quality_directory does not exist: {quality_directory}")

    return ResolvedJob(
        root=root,
        config_path=config_path,
        config=config,
        task_path=task_path,
        template_path=template_path,
        source_path=source_path,
        inputs=tuple(resolved_inputs),
        references=tuple(references),
        include_dir=include_dir,
        result_dir=result_dir,
        context_archive=context_archive,
        quality_directory=quality_directory,
    )


def prepare_result_directory(result_dir: Path) -> None:
    result_dir.mkdir(parents=True, exist_ok=True)
    for path in result_dir.iterdir():
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
