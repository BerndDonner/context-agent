from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

from context_agent.models import ResolvedJob

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def build_job_bundle(job: ResolvedJob, destination: Path, runtime_dir: Path) -> Path:
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

    with tarfile.open(destination, mode="w:gz") as archive:
        for path in sorted(job.root.rglob("*")):
            if _skip_path(job, path):
                continue
            if path.is_symlink():
                continue
            if path.is_file():
                arcname = Path("job") / path.relative_to(job.root)
                archive.add(path, arcname=arcname, recursive=False)

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
    return bool(relative.parts and relative.parts[0] in {"result", "nogos"})

