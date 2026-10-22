"""Durable diagnostics for candidates rejected by the regression gate.

Keep them OUTSIDE the accepted result and never treat them as validated. Copy
only known artifact names, with bounded size and no symlink following.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

_FILES = ('main.tex', 'main.pdf', 'context.log', 'include-snapshot.tar.gz')
_MAX_FILE_BYTES = 64 * 1024 * 1024


def preserve_rejected(result_dir: Path, *, reason_code: str,
                      accepted_tex: Path | None = None) -> str | None:
    """Return the relative diagnostics directory or None when nothing exists."""
    source = result_dir / 'main.tex'
    if not source.is_file() or source.is_symlink():
        return None
    from context_agent.improvement import improvement_diff
    root = result_dir / 'rejected'
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    name = f'{sum(x.is_dir() for x in root.iterdir()) + 1:04d}'
    if (root / name).exists():
        return None
    temporary = Path(tempfile.mkdtemp(prefix='.staging-', dir=root))
    try:
        hashes: dict[str, str] = {}
        for filename in _FILES:
            item = result_dir / filename
            if (not item.is_file() or item.is_symlink() or
                    item.stat().st_size > _MAX_FILE_BYTES):
                continue
            dest = temporary / filename
            shutil.copyfile(item, dest, follow_symlinks=False)
            dest.chmod(0o600)
            hashes[filename] = hashlib.sha256(dest.read_bytes()).hexdigest()
        if accepted_tex and accepted_tex.is_file() and not accepted_tex.is_symlink():
            (temporary / 'candidate.diff').write_text(
                improvement_diff(accepted_tex.read_text(encoding='utf-8'),
                                 source.read_text(encoding='utf-8'), max_lines=1000000) + '\n',
                encoding='utf-8')
        (temporary / 'metadata.json').write_text(json.dumps({
            'status': 'REJECTED_NOT_VALIDATED',
            'reason_code': reason_code,
            'files_sha256': hashes,
        }, indent=2) + '\n', encoding='utf-8')
        os.replace(temporary, root / name)
        return f'rejected/{name}'
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
