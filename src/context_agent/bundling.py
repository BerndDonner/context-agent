from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

from context_agent.models import ResolvedJob
from context_agent.include_sync import read_include_snapshot
from context_agent.quality_rules import QualityRule

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def build_job_bundle(job: ResolvedJob, destination: Path, runtime_dir: Path,
                     *, resume_result: Path | None = None,
                     rules: tuple[QualityRule, ...] = ()) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "task": f"job/{job.config.task}",
        "template": f"job/{job.config.template.path}",
        "inputs": [
            {
                "path": f"job/{item.relative_path}",
                "role": item.role.value,
                "policy": item.policy.value,
            }
            for item in job.inputs
        ],
        "references": [f"job/{path.relative_to(job.root).as_posix()}" for path in job.references],
        "result_directory": "job/result",
    }
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")

    overrides = (read_include_snapshot(resume_result / 'include-snapshot.tar.gz')
                 if resume_result is not None and
                 (resume_result / 'include-snapshot.tar.gz').is_file() else {})
    if resume_result is not None and not overrides and any(job.include_dir.rglob('*')):
        # Empty snapshots are valid only for projects without include files.
        if any(x.is_file() for x in job.include_dir.rglob('*')):
            raise ValueError('resume requires a complete include snapshot')

    with tarfile.open(destination, mode="w:gz") as archive:
        # These directories must exist in the Hosted container even when empty.
        # The file-only walk below does not otherwise preserve empty directories.
        for directory in ("job/include", "job/result"):
            info = tarfile.TarInfo(f"{directory}/")
            info.type = tarfile.DIRTYPE
            info.mode = 0o755
            archive.addfile(info)

        for path in sorted(job.root.rglob("*")):
            if _skip_path(job, path):
                continue
            if path.is_symlink():
                continue
            if path.is_file():
                relative = path.relative_to(job.root)
                if relative.parts[0] == 'include' and relative.as_posix()[8:] in overrides:
                    continue
                arcname = Path("job") / relative
                archive.add(path, arcname=arcname, recursive=False)

        # Dependencies are declared by selected rules, without activating others.
        seen_resources: dict[str, bytes] = {}
        for rule in rules:
            for resource in rule.resources:
                content = resource.source.read_bytes()
                if resource.target in seen_resources:
                    if seen_resources[resource.target] != content:
                        raise ValueError(f'conflicting resource declarations: {resource.target}')
                    continue
                seen_resources[resource.target] = content
                if resource.target in overrides or (job.include_dir / resource.target).is_file():
                    continue
                info = tarfile.TarInfo('job/include/' + resource.target)
                info.mode = 0o644
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))

        if resume_result is not None:
            for relative, data in sorted(overrides.items()):
                info = tarfile.TarInfo(f'job/include/{relative}')
                info.mode = 0o644
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
            for name in ('main.tex', 'main.pdf', 'context.log', 'include-snapshot.tar.gz',
                         'report.json', 'checkpoint.json', 'transcript.jsonl', 'uncertainties.md'):
                source = resume_result / name
                if source.is_file():
                    archive.add(source, arcname=f'job/result/{name}', recursive=False)

        for path in sorted(runtime_dir.rglob("*")):
            if path.is_file() and not path.is_symlink():
                archive.add(
                    path,
                    arcname=Path("runtime") / path.relative_to(runtime_dir),
                    recursive=False,
                )

        info = tarfile.TarInfo("agent-manifest.json")
        info.size = len(manifest_bytes)
        info.mode = 0o644
        archive.addfile(info, fileobj=io.BytesIO(manifest_bytes))

    return destination


def direct_model_files(job: ResolvedJob) -> tuple[Path, ...]:
    """PDFs and configured images are attached directly for multimodal reading."""
    paths: list[Path] = []
    for item in job.inputs:
        if item.path.suffix.lower() == ".pdf" or item.path.suffix.lower() in _IMAGE_SUFFIXES:
            paths.append(item.path)
    for path in job.references:
        if path.suffix.lower() == ".pdf" or path.suffix.lower() in _IMAGE_SUFFIXES:
            paths.append(path)
    return tuple(dict.fromkeys(paths))


def _skip_path(job: ResolvedJob, path: Path) -> bool:
    try:
        relative = path.relative_to(job.root)
    except ValueError:
        return True
    return bool(relative.parts and relative.parts[0] in {"result", "quality_rules", ".resume-work", ".run-history"})

