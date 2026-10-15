from __future__ import annotations

import io
import os
import subprocess
import tarfile
import time
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / 'src/context_agent/resources/runtime/bootstrap-context.sh'


def test_runtime_script_uses_ephemeral_context_tree() -> None:
    script = SCRIPT.read_text(encoding='utf-8')
    assert '*.ctxbundle' in script
    assert 'mktemp -d /tmp/context-agent-lmtx' in script
    assert 'mktemp -d /mnt/data/context-agent-lmtx' not in script
    assert '''trap 'rm -rf "$temporary"' EXIT''' in script
    assert '--compile' in script


def test_compilation_keeps_thousands_of_temporary_files_outside_mnt_data(tmp_path: Path) -> None:
    """A running ConTeXt distribution must not exceed /mnt/data's file-count limit."""
    marker = tmp_path / 'tree.txt'
    release = tmp_path / 'release'
    source = tmp_path / 'main.tex'
    source.write_text('\\starttext test \\stoptext', encoding='utf-8')
    output_log = tmp_path / 'context.log'
    archive = tmp_path / 'context.tar.xz'
    bundle = tmp_path / 'context.ctxbundle'

    # This fake compiler stops while its large distribution tree is still unpacked.
    script = r'''#!/bin/sh
set -eu
printf '%s\n' "$(dirname "$0")" > "$TEST_TREE_MARKER"
while [ ! -f "$TEST_RELEASE" ]; do sleep 0.05; done
printf '%%PDF' > "${1%.tex}.pdf"
'''
    with tarfile.open(archive, mode='w:xz') as tar:
        encoded = script.encode()
        entry = tarfile.TarInfo('fake-lmtx/context-local.sh')
        entry.size = len(encoded)
        entry.mode = 0o755
        tar.addfile(entry, io.BytesIO(encoded))
        for i in range(1_020):
            entry = tarfile.TarInfo(f'fake-lmtx/tex/texmf-context/test/{i:04}.tex')
            entry.size = 0
            tar.addfile(entry, io.BytesIO(b''))
    bundle.write_bytes(b'CONTEXT_AGENT_ARCHIVE_V1\n' + archive.read_bytes())

    environment = dict(os.environ, CONTEXT_AGENT_CONTEXT_BUNDLE=str(bundle),
                       TEST_TREE_MARKER=str(marker), TEST_RELEASE=str(release),
                       TMPDIR='/mnt/data')
    process = subprocess.Popen(
        ['bash', str(SCRIPT), '--compile', str(source), str(output_log)],
        env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    extracted: Path | None = None
    try:
        deadline = time.monotonic() + 15
        while not marker.exists() and time.monotonic() < deadline:
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                raise AssertionError(f'runner exited before marker: {stdout!r}, {stderr!r}')
            time.sleep(0.03)
        assert marker.exists(), 'fake ConTeXt command was not started'
        extracted = Path(marker.read_text().strip()).resolve()
        assert extracted.is_relative_to('/tmp')
        assert not extracted.is_relative_to('/mnt/data')
        assert sum(1 for p in extracted.rglob('*') if p.is_file()) >= 1_021
    finally:
        release.touch()
        try:
            stdout, stderr = process.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            raise AssertionError(f'runner hung: {stdout!r}, {stderr!r}')

    assert process.returncode == 0, stderr.decode(errors='replace')
    assert output_log.exists()
    assert (tmp_path / 'main.pdf').read_bytes() == b'%PDF'
    assert extracted is not None and not extracted.exists(), 'temporary tree was not removed'
