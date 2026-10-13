from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'src/context_agent/resources/runtime/managed-process.py'
MARKER = 'CA-PROCESS-V1 '


def invoke(root: Path, *args: str) -> dict:
    env = dict(os.environ, CONTEXT_AGENT_PROCESS_DIR=str(root))
    result = subprocess.run([sys.executable, str(SCRIPT), *args], env=env,
                            capture_output=True, text=True, timeout=12)
    assert result.returncode == 0, (result.stdout, result.stderr)
    lines = [line for line in result.stdout.splitlines() if line.startswith(MARKER)]
    assert len(lines) == 1
    return json.loads(lines[0][len(MARKER):])


def test_running_process_finishes_independently_of_start_and_status(tmp_path: Path):
    started = invoke(tmp_path, 'start', 'finished', '--', sys.executable, '-c',
                     'import time; time.sleep(.6); print("process complete")')
    assert started['status'] in ('starting', 'running', 'exited')
    pending = invoke(tmp_path, 'status', 'finished')
    assert pending['id'] == 'finished'
    final = invoke(tmp_path, 'wait', 'finished', '--seconds', '3')
    assert final['status'] == 'exited'
    assert final['exit_code'] == 0
    assert final['stdout_tail'] == 'process complete\n'
    assert invoke(tmp_path, 'status', 'finished')['exit_code'] == 0


def test_nonzero_exit_and_stderr_are_durable(tmp_path: Path):
    invoke(tmp_path, 'start', 'err', '--', sys.executable, '-c',
           'import sys; print("details", file=sys.stderr); sys.exit(23)')
    final = invoke(tmp_path, 'wait', 'err', '--seconds', '3')
    assert final['status'] == 'exited'
    assert final['exit_code'] == 23
    assert 'details' in final['stderr_tail']


def test_missing_binary_fails_closed(tmp_path: Path):
    invoke(tmp_path, 'start', 'missing', '--', '/nonexistent-binary')
    final = invoke(tmp_path, 'wait', 'missing', '--seconds', '3')
    assert final['status'] == 'failed'
    assert final['exit_code'] is None
    assert 'FileNotFoundError' in final['error']


def test_duplicate_id_cannot_execute_command_twice(tmp_path: Path):
    output = tmp_path / 'counter.txt'
    command = [sys.executable, '-c',
               f'from pathlib import Path; Path({str(output)!r}).write_text("once")']
    invoke(tmp_path, 'start', 'same', '--', *command)
    env = dict(os.environ, CONTEXT_AGENT_PROCESS_DIR=str(tmp_path))
    duplicate = subprocess.run([sys.executable, str(SCRIPT), 'start', 'same', '--', *command],
                               env=env, capture_output=True, text=True, timeout=12)
    assert duplicate.returncode == 2
    assert 'already exists' in duplicate.stderr
    assert invoke(tmp_path, 'wait', 'same', '--seconds', '3')['exit_code'] == 0
    assert output.read_text() == 'once'


def test_cancel_terminates_process_group_and_records_real_exit(tmp_path: Path):
    started = invoke(tmp_path, 'start', 'stop', '--', sys.executable, '-c', 'import time; time.sleep(60)')
    assert started['status'] in ('starting', 'running')
    invoke(tmp_path, 'cancel', 'stop')
    final = invoke(tmp_path, 'wait', 'stop', '--seconds', '3')
    assert final['status'] == 'cancelled'
    assert final['exit_code'] < 0


def test_long_poll_does_not_set_process_timeout(tmp_path: Path):
    invoke(tmp_path, 'start', 'slow', '--', sys.executable, '-c',
           'import time; time.sleep(1.2); print("slow completed")')
    first = invoke(tmp_path, 'wait', 'slow', '--seconds', '.1')
    assert first['status'] in ('running', 'exited')
    final = invoke(tmp_path, 'wait', 'slow', '--seconds', '3')
    assert final['status'] == 'exited'
    assert final['exit_code'] == 0


def test_malicious_id_is_rejected(tmp_path: Path):
    env = dict(os.environ, CONTEXT_AGENT_PROCESS_DIR=str(tmp_path))
    run = subprocess.run([sys.executable, str(SCRIPT), 'status', '../../unsafe'],
                         env=env, capture_output=True, text=True)
    assert run.returncode == 2
    assert not (tmp_path / 'unsafe').exists()


def test_output_is_recoverable_in_bounded_chunks(tmp_path: Path):
    invoke(tmp_path, 'start', 'big', '--', sys.executable, '-c', 'print("x" * 11000)')
    final = invoke(tmp_path, 'wait', 'big', '--seconds', '3')
    assert final['status'] == 'exited'
    assert final['stdout_size'] == 11001
    import base64
    buffer = bytearray()
    while len(buffer) < final['stdout_size']:
        chunk = invoke(tmp_path, 'read', 'big', '--stream', 'stdout',
                       '--offset', str(len(buffer)), '--length', '4096')
        buffer.extend(base64.b64decode(chunk['data_b64']))
    assert bytes(buffer) == (b'x' * 11000 + b'\n')


def test_dollar_lint_runs_through_manager_without_replacing_source(tmp_path: Path, monkeypatch):
    import json
    lint = SCRIPT.with_name('lint-dollar-math.sh')
    setup = SCRIPT.with_name('lint-dollar-setup.tex')
    assert setup.is_file()
    source = tmp_path / 'main.tex'
    original = b'\\starttext $x$ \\stoptext\n'
    source.write_bytes(original)
    fake = tmp_path / 'fake-context.sh'
    fake.write_text('#!/usr/bin/env bash\n'
                    'printf "%%PDF" > "${1%.tex}.pdf"\n'
                    'echo "CA-DOLLAR-LINT line 5"\n')
    fake.chmod(0o755)
    monkeypatch.setenv('CONTEXT_AGENT_LINT_RUNNER', str(fake))
    report_path = tmp_path / '.report.json'
    nonce = '0123456789abcdef0123456789abcdef'
    invoke(tmp_path / 'processes', 'start', 'linter', '--', 'bash', str(lint),
           str(source), str(report_path), nonce)
    finished = invoke(tmp_path / 'processes', 'wait', 'linter', '--seconds', '3')
    assert finished['status'] == 'exited'
    assert finished['exit_code'] == 0
    assert 'CA-DOLLAR-LINT-REPORT-V1 ' in finished['stdout_tail']
    result = json.loads(report_path.read_text())
    assert result['nonce'] == nonce
    assert result['findings'][0]['line'] == 4
    assert source.read_bytes() == original
