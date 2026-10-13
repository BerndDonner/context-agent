from __future__ import annotations

import io
import subprocess
import tarfile
from pathlib import Path

import pytest

from context_agent.errors import ArtifactError
from context_agent.include_sync import IncludeTransaction, make_snapshot, read_include_snapshot


def git(root: Path, *args: str) -> None:
    subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True)


def setup_git(tmp_path: Path) -> Path:
    root = tmp_path / 'pool'
    (root / 'include').mkdir(parents=True)
    git(root, 'init', '-q')
    git(root, 'config', 'user.email', 'test@example.org')
    git(root, 'config', 'user.name', 'Test')
    (root / 'include' / 'plotmod.lua').write_text('old')
    git(root, 'add', '.')
    git(root, 'commit', '-qm', 'baseline')
    return root


def test_roundtrip_modifies_git_worktree_without_commit(tmp_path: Path) -> None:
    root = setup_git(tmp_path)
    transaction = IncludeTransaction.capture(root / 'include')
    updated = {'plotmod.lua': b'new', 'extra/helper.lua': b'new helper'}
    assert transaction.apply(updated) == ['extra/helper.lua', 'plotmod.lua']
    assert (root / 'include/plotmod.lua').read_bytes() == b'new'
    assert (root / 'include/extra/helper.lua').read_bytes() == b'new helper'
    status = subprocess.run(['git', '-C', str(root), 'status', '--porcelain'],
                            capture_output=True, text=True, check=True)
    assert ' M include/plotmod.lua' in status.stdout
    assert '?? include/extra/' in status.stdout
    log = subprocess.run(['git', '-C', str(root), 'rev-list', '--count', 'HEAD'],
                         capture_output=True, text=True, check=True)
    assert log.stdout.strip() == '1' 


def test_dirty_tracked_file_is_never_overwritten(tmp_path: Path) -> None:
    root = setup_git(tmp_path)
    (root / 'include/plotmod.lua').write_text('uncommitted')
    transaction = IncludeTransaction.capture(root / 'include')
    with pytest.raises(ArtifactError, match='uncommitted'):
        transaction.apply({'plotmod.lua': b'agent changes'})
    assert (root / 'include/plotmod.lua').read_text() == 'uncommitted'


def test_concurrent_edit_is_never_overwritten(tmp_path: Path) -> None:
    root = setup_git(tmp_path)
    transaction = IncludeTransaction.capture(root / 'include')
    (root / 'include/plotmod.lua').write_text('concurrent')
    with pytest.raises(ArtifactError, match='concurrent'):
        transaction.apply({'plotmod.lua': b'agent changes'})
    assert (root / 'include/plotmod.lua').read_text() == 'concurrent'


def test_snapshot_cannot_delete_files(tmp_path: Path) -> None:
    root = setup_git(tmp_path)
    transaction = IncludeTransaction.capture(root / 'include')
    with pytest.raises(ArtifactError, match='removes'):
        transaction.apply({})


def test_valid_snapshot_and_rejects_path_traversal(tmp_path: Path) -> None:
    root = tmp_path / 'include'
    root.mkdir()
    (root / 'a.lua').write_text('data')
    snapshot = tmp_path / 'snapshot.tar.gz'
    make_snapshot(root, snapshot)
    assert read_include_snapshot(snapshot) == {'a.lua': b'data'}
    with tarfile.open(snapshot, 'w:gz') as tf:
        info = tarfile.TarInfo('include/../../pwned')
        info.size = 3
        tf.addfile(info, io.BytesIO(b'bad'))
    with pytest.raises(ArtifactError, match='unsafe'):
        read_include_snapshot(snapshot)


def test_snapshot_rejects_symlink(tmp_path: Path) -> None:
    snapshot = tmp_path / 'snapshot.tar.gz'
    with tarfile.open(snapshot, 'w:gz') as tf:
        info = tarfile.TarInfo('include/escape')
        info.type = tarfile.SYMTYPE
        info.linkname = '../../escape'
        tf.addfile(info)
    with pytest.raises(ArtifactError, match='non-regular'):
        read_include_snapshot(snapshot)
