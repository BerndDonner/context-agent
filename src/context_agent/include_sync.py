"""Conservative, Git-aware round-trip for a sandbox's include/ directory."""
from __future__ import annotations

import os
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from context_agent.errors import ArtifactError

MAX_FILES = 2000
MAX_TOTAL_BYTES = 80 * 1024 * 1024


def _read_tree(root: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    if not root.is_dir():
        return files
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ArtifactError(f"include contains a symlink: {path}")
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            files[rel] = path.read_bytes()
    return files


def read_include_snapshot(snapshot: Path) -> dict[str, bytes]:
    """Validate archive paths, types and size before touching local files."""
    result: dict[str, bytes] = {}
    total = 0
    try:
        with tarfile.open(snapshot, 'r:gz') as archive:
            members = archive.getmembers()
            if len(members) > MAX_FILES + 100:
                raise ArtifactError('include snapshot contains too many entries')
            for member in members:
                path = PurePosixPath(member.name)
                if (path.is_absolute() or '..' in path.parts or '.git' in path.parts
                        or not path.parts or path.parts[0] != 'include'):
                    raise ArtifactError(f"unsafe include archive member: {member.name}")
                if member.isdir():
                    continue
                if not member.isfile():
                    raise ArtifactError(f"non-regular include archive member: {member.name}")
                if len(path.parts) < 2:
                    raise ArtifactError('include archive contains invalid root file')
                rel = PurePosixPath(*path.parts[1:]).as_posix()
                if rel in result or len(result) >= MAX_FILES or member.size > MAX_TOTAL_BYTES:
                    raise ArtifactError(f"duplicate/oversized include member: {member.name}")
                total += member.size
                if total > MAX_TOTAL_BYTES:
                    raise ArtifactError('include snapshot exceeds size limit')
                stream = archive.extractfile(member)
                if stream is None:
                    raise ArtifactError(f"unreadable include member: {member.name}")
                data = stream.read(MAX_TOTAL_BYTES + 1)
                if len(data) != member.size:
                    raise ArtifactError(f"size mismatch: {member.name}")
                result[rel] = data
    except (OSError, tarfile.TarError) as exc:
        raise ArtifactError(f"invalid include snapshot: {exc}") from exc
    return result


def _git_dirty(root: Path, relative: str) -> bool:
    # Failure to run git is not treated as evidence of a clean tracked file.
    repo = subprocess.run(['git', '-C', str(root), 'rev-parse', '--show-toplevel'],
                          capture_output=True, text=True, check=False)
    if repo.returncode != 0:
        return False  # Outside git, byte-for-byte baseline still guards updates.
    path = root / relative
    tracked = subprocess.run(['git', '-C', str(root), 'ls-files', '--error-unmatch', '--', str(path)],
                             capture_output=True, check=False)
    if tracked.returncode != 0:
        return path.exists()  # untracked existing includes must not be rewritten
    status = subprocess.run(['git', '-C', str(root), 'status', '--porcelain', '--', str(path)],
                            capture_output=True, check=False)
    if status.returncode != 0:
        raise ArtifactError(f'git status failed for {path}')
    return bool(status.stdout.strip())


@dataclass
class IncludeTransaction:
    root: Path
    initial: dict[str, bytes]
    dirty_at_start: set[str]

    @classmethod
    def capture(cls, root: Path) -> 'IncludeTransaction':
        initial = _read_tree(root)
        dirty = {rel for rel in initial if _git_dirty(root.parent, f'include/{rel}')}
        return cls(root, initial, dirty)

    def changes(self, remote: dict[str, bytes]) -> dict[str, bytes]:
        deleted = self.initial.keys() - remote.keys()
        if deleted:
            raise ArtifactError('include snapshot unexpectedly removes existing files: ' + ', '.join(sorted(deleted)))
        changes = {rel: data for rel, data in remote.items() if self.initial.get(rel) != data}
        for rel in changes:
            if rel in self.dirty_at_start:
                raise ArtifactError(f'agent changed a previously uncommitted include file: {rel}')
        return changes

    def apply(self, remote: dict[str, bytes]) -> list[str]:
        changes = self.changes(remote)
        current = _read_tree(self.root)
        for rel in changes:
            if current.get(rel) != self.initial.get(rel) or _git_dirty(self.root.parent, f'include/{rel}'):
                raise ArtifactError(f'concurrent or uncommitted include change: {rel}')
        # Prepare all replacements first; commit as a batch, rolling back on an I/O failure.
        staged: dict[str, Path] = {}
        applied: list[str] = []
        with tempfile.TemporaryDirectory(prefix='.context-agent-includes-', dir=self.root) as temporary:
            for index, (rel, content) in enumerate(changes.items()):
                candidate = Path(temporary) / str(index)
                candidate.write_bytes(content)
                staged[rel] = candidate
            try:
                for rel, candidate in staged.items():
                    target = self.root / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if target.is_symlink():
                        raise ArtifactError(f'symlink target in includes: {target}')
                    os.replace(candidate, target)
                    applied.append(rel)
            except Exception:
                for rel in reversed(applied):
                    target = self.root / rel
                    old = self.initial.get(rel)
                    if old is None:
                        target.unlink(missing_ok=True)
                    else:
                        target.write_bytes(old)
                raise
        return sorted(changes)


def make_snapshot(root: Path, destination: Path) -> None:
    """Test helper; the hosted agent uses the matching shell runtime script."""
    with tarfile.open(destination, 'w:gz') as archive:
        archive.add(root, arcname='include')
