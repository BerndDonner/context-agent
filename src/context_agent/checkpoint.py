"""Durable checkpoints for runs created by this checkpoint format only."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from context_agent.errors import ContextAgentError
from context_agent.models import ResolvedJob

SCHEMA = 1
CHECKPOINT_NAME = "checkpoint.json"


def fingerprint(job: ResolvedJob) -> dict[str, str]:
    """Protect all inputs that affect the reproduced result (not output files)."""
    paths = [job.config_path, job.task_path, job.template_path, job.context_archive]
    if job.source_path is not None:
        paths.append(job.source_path)
    paths.extend(i.path for i in job.inputs)
    paths.extend(job.references)
    from context_agent.quality_rules import load_rules
    rule_folders = [rule.root for rule in load_rules(job)]
    for folder in (job.include_dir, job.quality_directory, *rule_folders):
        if folder and folder.is_dir():
            paths.extend(p for p in folder.rglob('*') if p.is_file())
    hashes: dict[str, str] = {}
    for path in sorted(set(paths)):
        if path.is_symlink():
            raise ContextAgentError(f"checkpoint cannot fingerprint symlink: {path}")
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        key = (path.relative_to(job.root).as_posix() if path.is_relative_to(job.root)
               else str(path))
        hashes[key] = digest.hexdigest()
    return hashes


def read_checkpoint(job: ResolvedJob) -> dict[str, Any]:
    file = job.result_dir / CHECKPOINT_NAME
    if not file.is_file():
        raise ContextAgentError('resume requires a checkpoint from a new-format run; old runs are not supported')
    try:
        data = json.loads(file.read_text(encoding='utf-8'))
    except (ValueError, OSError) as exc:
        raise ContextAgentError(f'invalid checkpoint: {exc}') from exc
    if not isinstance(data, dict) or data.get('schema') != SCHEMA:
        raise ContextAgentError('unsupported checkpoint version; old runs are not supported')
    if data.get('phase') == 'finished-success':
        raise ContextAgentError('resume is intended for incomplete runs, not already successful runs')
    if data.get('inputs') != fingerprint(job):
        raise ContextAgentError('resume refused: job configuration, source, template, include or runtime files changed')
    return data


def save_checkpoint(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data['updated_at'] = datetime.now(UTC).isoformat()
    tmp = path.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str) + '\n',
                   encoding='utf-8')
    tmp.replace(path)
