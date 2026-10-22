"""Regression tests for the large-payload failure from the Messtechnik improve job."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from context_agent.diagnostics import exception_metadata, record_event
from context_agent.errors import RemoteAgentError
from context_agent.job import load_job
from context_agent.models import AgentTurn
from context_agent.openai_backend import OpenAIHostedSession

SCRIPT = Path(__file__).resolve().parents[1] / 'src/context_agent/resources/runtime/apply-quality-edits.py'


def _edits(count: int, original: str) -> list[dict]:
    digest = hashlib.sha256(original.encode()).hexdigest()
    return [dict(path='main.tex', expected_sha256=digest, offset=i * 6,
                 old='1{,}5', new='\\dn{1.5}') for i in range(count)]


def test_quality_edits_uploaded_to_container_not_embedded_in_shell(tmp_path, job_factory):
    job = load_job(job_factory(tmp_path))
    session = object.__new__(OpenAIHostedSession)
    session.job = job
    session.container_id = 'container-test'
    commands: list[list[str]] = []
    requests: list[tuple[str, dict]] = []
    original = '1{,}5\n' * 40
    edits = _edits(40, original)

    def create(container_id, **kwargs):
        requests.append((container_id, kwargs))
        payload = kwargs['file'][1]
        return SimpleNamespace(id='cfile-1', path='/mnt/data/cfile-1-quality-edits.json',
                               bytes=len(payload))

    def run_command(argv, **kwargs):
        commands.append(argv)
        n = len(commands)
        return dict(status='exited', exit_code=0), AgentTurn(
            f'response-{n}', 'completed', '', {'response_ids':[f'response-{n}']},
            {'total_tokens': 1}, 1)

    session._client = SimpleNamespace(containers=SimpleNamespace(files=SimpleNamespace(create=create)))
    session.run_managed_command = run_command
    turn = session.apply_quality_edits(edits, max_api_calls=10)

    assert len(requests) == 1
    assert requests[0][0] == 'container-test'
    assert len(requests[0][1]['file'][1]) > 5000
    digest = hashlib.sha256(requests[0][1]['file'][1]).hexdigest()
    assert commands[0][-4:] == ['--edits-file', '/mnt/data/cfile-1-quality-edits.json',
                                '--sha256', digest]
    assert '--payload' not in commands[0]
    assert all(len(' '.join(cmd)) < 350 for cmd in commands)
    assert len(commands) == 3
    assert turn.api_calls == 3
    events = [json.loads(s) for s in (job.result_dir / 'execution-events.jsonl').read_text().splitlines()]
    assert any(e['event'] == 'quality_payload_uploaded' and e['payload_sha256'] == digest
               for e in events)
    assert len(''.join(json.dumps(e) for e in events)) > 0
    assert '\\dn{1.5}' not in str(events)


def test_invalid_upload_confirmation_stops_before_running_anything(tmp_path, job_factory):
    job = load_job(job_factory(tmp_path))
    session = object.__new__(OpenAIHostedSession)
    session.job = job
    session.container_id = 'container-test'
    session._client = SimpleNamespace(containers=SimpleNamespace(files=SimpleNamespace(
        create=lambda *a, **k: SimpleNamespace(path='/tmp/forged.json', bytes=5))))
    session.run_managed_command = lambda *args, **kwargs: pytest.fail('must not run')
    with pytest.raises(RemoteAgentError, match='path is invalid'):
        session.apply_quality_edits([], max_api_calls=10)


def test_guarded_edits_real_script_with_large_file_and_bad_hash():
    with tempfile.TemporaryDirectory(dir='/mnt/data') as work:
        root = Path(work)
        target = root / 'main.tex'
        original = '1{,}5\n' * 40
        target.write_text(original)
        edits = _edits(40, original)
        content = json.dumps(edits).encode()
        payload = root / 'quality-edits.json'
        payload.write_bytes(content)
        checksum = hashlib.sha256(content).hexdigest()
        wrong = subprocess.run([sys.executable, str(SCRIPT), '--edits-file', str(payload),
                                '--sha256', '0' * 64], capture_output=True, text=True)
        assert wrong.returncode != 0
        assert target.read_text() == original
        # The executable's target is fixed to the Hosted work tree, but its
        # pure guarded-apply function allows an isolated real-file test.
        import importlib.util
        spec = importlib.util.spec_from_file_location('apply_quality_edits_runtime', SCRIPT)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert module.apply(payload, checksum, target) == 40
        assert target.read_text() == '\\dn{1.5}\n' * 40
        # Replaying the same edit payload must fail instead of double-applying.
        with pytest.raises(ValueError, match='stale hash'):
            module.apply(payload, checksum, target)


def test_diagnostics_never_log_command_payload_or_exception_message(tmp_path):
    path = tmp_path / 'events.jsonl'
    secret = 'sk-top-secret-not-for-log'
    record_event(path, 'bridge_transport_error', phase='bridge',
                 exception_type='Timeout', secret_token=secret, command=secret,
                 response_status='incomplete')
    exc = RuntimeError(secret)
    record_event(path, 'bridge_error', **exception_metadata(exc))
    data = path.read_text()
    assert secret not in data
    assert 'bridge_transport_error' in data
    assert json.loads(data.splitlines()[0])['response_status'] == 'incomplete'


def test_bridge_incomplete_persists_diagnostics_for_failed_attempt(tmp_path, job_factory):
    job = load_job(job_factory(tmp_path))
    session = object.__new__(OpenAIHostedSession)
    session.job = job
    session.container_id = 'container-test'
    session._client = SimpleNamespace(responses=SimpleNamespace(create=lambda **kw:
        SimpleNamespace(id='resp-incomplete', status='incomplete', _request_id='req-42',
                        model_dump=lambda mode: {
                            'output': [], 'incomplete_details': {'reason': 'max_output_tokens'},
                            'usage': {'total_tokens': 1200},
                        })))
    from context_agent.openai_backend import BridgeOutcomeUnknown
    with pytest.raises(BridgeOutcomeUnknown):
        session._managed_shell('python3 -c "print(42)"')
    logs = [json.loads(line) for line in
            (job.result_dir / 'execution-events.jsonl').read_text().splitlines()]
    assert logs[-1]['event'] == 'bridge_response'
    assert logs[-1]['response_id'] == 'resp-incomplete'
    assert logs[-1]['request_id'] == 'req-42'
    assert logs[-1]['incomplete_reason'] == 'max_output_tokens'
    assert logs[-1]['total_tokens'] == 1200
    assert 'python3 -c' not in json.dumps(logs)
