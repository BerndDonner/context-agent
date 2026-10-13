#!/usr/bin/env python3
"""Container-local managed subprocess protocol for Hosted Shell.

Start is detached from a model response. A supervisor owns the child, records
its actual exit status atomically, and writes durable output logs. Status/wait
are read-only (apart from normal log reading); they never restart commands.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

MARKER = 'CA-PROCESS-V1 '
TERMINAL = {'exited', 'failed', 'cancelled'}
ID_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$')


def base_dir() -> Path:
    root = Path(os.environ.get('CONTEXT_AGENT_PROCESS_DIR', '/mnt/data/work/.processes'))
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


def job_dir(process_id: str) -> Path:
    if not ID_PATTERN.fullmatch(process_id):
        raise ValueError('invalid process ID')
    return base_dir() / process_id


def atomic_json(path: Path, data: dict) -> None:
    temporary = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    with temporary.open('x', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def read_json(path: Path) -> dict:
    try:
        with path.open(encoding='utf-8') as stream:
            return json.load(stream)
    except FileNotFoundError:
        return {}


def ticks(pid: int) -> str | None:
    """Linux process start-time ticks guard against PID reuse before signaling."""
    try:
        stat = Path(f'/proc/{pid}/stat').read_text()
        return stat.rsplit(')', 1)[1].split()[19]  # /proc field 22
    except (OSError, IndexError):
        return None


def same_process(pid: int | None, birth: str | None) -> bool:
    return pid is not None and birth is not None and ticks(pid) == birth


def tail(path: Path, limit: int) -> tuple[str, int]:
    if not path.is_file():
        return '', 0
    size = path.stat().st_size
    with path.open('rb') as stream:
        stream.seek(max(0, size - limit))
        return stream.read().decode('utf-8', 'replace'), size


def report(process_id: str, limit: int) -> dict:
    directory = job_dir(process_id)
    state = read_json(directory / 'state.json')
    if not state:
        return {'id': process_id, 'status': 'not_found'}
    # If the supervisor was killed without recording the actual exit code, never
    # treat a preliminary state (or exit_code=0 from Hosted Shell) as success.
    if state['status'] in {'starting', 'running'}:
        pid = state.get('supervisor_pid')
        birth = state.get('supervisor_birth')
        if pid and birth and not same_process(pid, birth):
            state = {**state, 'status': 'failed', 'exit_code': None,
                     'error': 'supervisor disappeared without an exit record'}
    stdout, stdout_size = tail(directory / 'stdout.log', limit)
    stderr, stderr_size = tail(directory / 'stderr.log', limit)
    return {**state, 'stdout_tail': stdout, 'stderr_tail': stderr,
            'stdout_size': stdout_size, 'stderr_size': stderr_size}


def start(process_id: str, cwd: str | None, argv: list[str]) -> dict:
    if not argv:
        raise ValueError('missing command to execute')
    directory = job_dir(process_id)
    try:
        directory.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise ValueError(f'process id already exists: {process_id}') from exc
    command_cwd = str(Path(cwd).resolve()) if cwd else os.getcwd()
    if not Path(command_cwd).is_dir():
        directory.rmdir()
        raise ValueError(f'working directory does not exist: {command_cwd}')
    info = {'id': process_id, 'status': 'starting', 'exit_code': None,
            'created_at': time.time(), 'cwd': command_cwd, 'argv': argv,
            'supervisor_pid': None, 'supervisor_birth': None}
    atomic_json(directory / 'state.json', info)
    # The worker is detached from the shell tool's session/stdio. The worker
    # itself owns and reaps the target subprocess even after the model returns.
    worker = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), '_worker', process_id],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True,
        cwd=command_cwd,
    )
    # Wait for the worker to publish its own PID and running state to avoid a
    # race where the parent overwrites a newly written terminal state.
    until = time.monotonic() + 2.0
    while time.monotonic() < until:
        state = read_json(directory / 'state.json')
        if state.get('supervisor_pid') == worker.pid or state.get('status') in TERMINAL:
            return report(process_id, 1000)
        time.sleep(0.02)
    return report(process_id, 1000)


def worker_main(process_id: str) -> None:
    directory = job_dir(process_id)
    state_path = directory / 'state.json'
    state = read_json(state_path)
    if not state or state['status'] != 'starting':
        return
    state.update(supervisor_pid=os.getpid(), supervisor_birth=ticks(os.getpid()))
    atomic_json(state_path, state)
    child: subprocess.Popen[bytes] | None = None
    try:
        with (directory / 'stdout.log').open('wb') as stdout, (directory / 'stderr.log').open('wb') as stderr:
            child = subprocess.Popen(state['argv'], cwd=state['cwd'], stdin=subprocess.DEVNULL,
                                     stdout=stdout, stderr=stderr, start_new_session=True,
                                     close_fds=True)
            state.update(status='running', pid=child.pid, pid_birth=ticks(child.pid),
                         started_at=time.time())
            atomic_json(state_path, state)
            terminated_at: float | None = None
            while True:
                if (directory / 'cancel-request').exists() and child.poll() is None:
                    if terminated_at is None:
                        os.killpg(child.pid, signal.SIGTERM)
                        terminated_at = time.monotonic()
                    elif time.monotonic() - terminated_at >= 2.0:
                        os.killpg(child.pid, signal.SIGKILL)
                try:
                    code = child.wait(timeout=0.2)
                    break
                except subprocess.TimeoutExpired:
                    pass
            state.update(status=('cancelled' if (directory / 'cancel-request').exists()
                                 else 'exited'), exit_code=code, ended_at=time.time())
    except Exception as exc:
        state.update(status='failed', exit_code=None, error=f'{type(exc).__name__}: {exc}',
                     ended_at=time.time())
    finally:
        atomic_json(state_path, state)


def cancel(process_id: str) -> dict:
    state = report(process_id, 0)
    if state['status'] in TERMINAL or state['status'] == 'not_found':
        return state
    # Durable cancellation is also honored when the supervisor has not yet
    # published a child PID. The worker sends SIGTERM and escalates to SIGKILL.
    request = job_dir(process_id) / 'cancel-request'
    request.touch(exist_ok=True)
    pid = state.get('pid')
    if pid and same_process(pid, state.get('pid_birth')):
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    # The supervisor will reap the child and record the actual exit status.
    return report(process_id, 0)


def wait(process_id: str, seconds: float, limit: int) -> dict:
    deadline = time.monotonic() + seconds
    while True:
        state = report(process_id, limit)
        if state['status'] in TERMINAL or time.monotonic() >= deadline:
            return state
        time.sleep(min(0.15, max(0, deadline - time.monotonic())))


def read_chunk(process_id: str, stream: str, offset: int, length: int) -> dict:
    if stream not in {'stdout', 'stderr'}:
        raise ValueError('stream must be stdout or stderr')
    if offset < 0 or not 1 <= length <= 4096:
        raise ValueError('invalid output offset or chunk length')
    directory = job_dir(process_id)
    path = directory / (stream + '.log')
    if not path.is_file():
        raise ValueError('process output stream does not exist')
    size = path.stat().st_size
    if offset > size:
        raise ValueError('output offset exceeds stream length')
    with path.open('rb') as file:
        file.seek(offset)
        data = file.read(length)
    return {'id': process_id, 'stream': stream, 'offset': offset, 'size': size,
            'next_offset': offset + len(data), 'data_b64': base64.b64encode(data).decode('ascii')}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='verb', required=True)
    start_p = sub.add_parser('start')
    start_p.add_argument('id')
    start_p.add_argument('--cwd')
    start_p.add_argument('argv', nargs=argparse.REMAINDER)
    status_p = sub.add_parser('status')
    status_p.add_argument('id')
    wait_p = sub.add_parser('wait')
    wait_p.add_argument('id')
    wait_p.add_argument('--seconds', type=float, default=5)
    cancel_p = sub.add_parser('cancel')
    cancel_p.add_argument('id')
    read_p = sub.add_parser('read')
    read_p.add_argument('id')
    read_p.add_argument('--stream', choices=('stdout', 'stderr'), required=True)
    read_p.add_argument('--offset', type=int, required=True)
    read_p.add_argument('--length', type=int, default=4096)
    args = parser.parse_args()
    try:
        if args.verb == 'start':
            argv = args.argv[1:] if args.argv and args.argv[0] == '--' else args.argv
            result = start(args.id, args.cwd, argv)
        elif args.verb == 'status':
            result = report(args.id, 4096)
        elif args.verb == 'wait':
            if not 0 <= args.seconds <= 15:
                raise ValueError('--seconds must be between 0 and 15')
            result = wait(args.id, args.seconds, 4096)
        elif args.verb == 'cancel':
            result = cancel(args.id)
        else:
            result = read_chunk(args.id, args.stream, args.offset, args.length)
    except (ValueError, OSError) as exc:
        print(f'managed-process: {exc}', file=sys.stderr)
        raise SystemExit(2) from exc
    print(MARKER + json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '_worker':
        worker_main(sys.argv[2])
    else:
        main()
