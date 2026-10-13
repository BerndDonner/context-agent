from __future__ import annotations

import pytest

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import context_agent.openai_backend as openai_backend
from context_agent.errors import RemoteAgentError
from context_agent.job import load_job
from context_agent.openai_backend import (
    OpenAIHostedSession,
    UploadedFile,
    _write_context_bundle,
)


class FakeResponses:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return SimpleNamespace(
            id=f"response-{len(self.calls)}",
            status="completed",
            output_text="done",
            model_dump=lambda mode: {
                "id": f"response-{len(self.calls)}",
                "usage": {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
            },
        )


class FakeContent:
    def retrieve(self, file_id: str, *, container_id: str) -> Any:
        assert file_id in {"cfile-tex", "cfile-pdf", "cfile-log", "cfile-includes"}
        assert container_id == "container-1"
        payload = {
            "cfile-tex": b"\\starttext test \\stoptext",
            "cfile-pdf": b"%PDF-1.7\n",
            "cfile-log": b"success",
            "cfile-includes": b"placeholder",
        }[file_id]
        return SimpleNamespace(read=lambda: payload)


class FakeContainerFiles:
    def __init__(self) -> None:
        self.content = FakeContent()

    def list(self, container_id: str, **kwargs: Any) -> list[Any]:
        assert container_id == "container-1"
        assert kwargs == {"limit": 100, "order": "desc"}
        return [
            SimpleNamespace(
                id="cfile-tex",
                path="/mnt/data/work/job/result/main.tex",
                created_at=3,
            ),
            SimpleNamespace(
                id="cfile-pdf",
                path="/mnt/data/work/job/result/main.pdf",
                created_at=3,
            ),
            SimpleNamespace(
                id="cfile-includes",
                path="/mnt/data/work/job/result/include-snapshot.tar.gz",
                created_at=3,
            ),
            SimpleNamespace(
                id="cfile-log",
                path="/mnt/data/work/job/result/context.log",
                created_at=3,
            ),
        ]


class FakeClient:
    def __init__(self) -> None:
        self.responses = FakeResponses()
        self.containers = SimpleNamespace(files=FakeContainerFiles())


def test_hosted_response_and_artifact_download(tmp_path: Path, job_factory) -> None:  # type: ignore[no-untyped-def]
    job = load_job(job_factory(tmp_path))
    direct = job.root / "input" / "image.png"
    direct.write_bytes(b"png")

    session = object.__new__(OpenAIHostedSession)
    session.job = job
    session.bundle_path = tmp_path / "bundle.tar.gz"
    session.direct_files = (direct,)
    session.system_prompt = "system"
    session.container_id = "container-1"
    session._uploaded = [UploadedFile(direct, "file-image")]
    session._client = FakeClient()

    first = session.run_initial("initial")
    second = session.run_followup("repair", first.response_id)
    assert second.response_id == "response-2"

    first_call, second_call = session._client.responses.calls
    assert first_call["tools"][0]["environment"] == {
        "type": "container_reference",
        "container_id": "container-1",
    }
    assert first_call["input"][0]["content"][1] == {
        "type": "input_image",
        "file_id": "file-image",
        "detail": "high",
    }
    assert second_call["previous_response_id"] == first.response_id
    assert len(second_call["input"][0]["content"]) == 1

    destination = tmp_path / "download"
    downloaded = session.sync_result(destination)
    assert set(downloaded) == {"main.tex", "main.pdf", "context.log", "include-snapshot.tar.gz"}
    assert (destination / "main.pdf").read_bytes().startswith(b"%PDF-")


def test_context_archive_is_wrapped_as_opaque_bundle(tmp_path: Path) -> None:
    source = tmp_path / "context.tar.xz"
    source.write_bytes(b"\xfd7zXZ\x00payload")
    destination = tmp_path / "context.ctxbundle"

    _write_context_bundle(source, destination)

    data = destination.read_bytes()
    assert data.startswith(b"CONTEXT_AGENT_ARCHIVE_V1\n")
    assert data.endswith(source.read_bytes())
    assert not data.startswith(b"\xfd7zXZ")


def test_create_client_uses_openai_api_key_from_environment(
    monkeypatch,  # type: ignore[no-untyped-def]
) -> None:
    calls: list[dict[str, Any]] = []

    class FakeOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            calls.append(kwargs)

    fake_module = SimpleNamespace(__version__="test", OpenAI=FakeOpenAI)
    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setattr(openai_backend.importlib, "import_module", lambda name: fake_module)

    OpenAIHostedSession._create_client(17)

    assert calls == [
        {
            "api_key": "test-api-key",
            "timeout": 17.0,
            "max_retries": 2,
        }
    ]


def test_create_client_requires_openai_api_key(
    monkeypatch,  # type: ignore[no-untyped-def]
) -> None:
    fake_module = SimpleNamespace(__version__="test", OpenAI=object)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(openai_backend.importlib, "import_module", lambda name: fake_module)

    try:
        OpenAIHostedSession._create_client(17)
    except RemoteAgentError as exc:
        assert "OPENAI_API_KEY is not set" in str(exc)
    else:
        raise AssertionError("missing OPENAI_API_KEY should fail")


def test_hosted_review_sends_images_but_disallows_shell(tmp_path: Path, job_factory) -> None:  # type: ignore[no-untyped-def]
    job = load_job(job_factory(tmp_path))
    session = object.__new__(OpenAIHostedSession)
    session.job = job
    session.bundle_path = tmp_path / 'bundle.tar.gz'
    session.direct_files = ()
    session.system_prompt = 'system'
    session.container_id = 'container-1'
    session._uploaded = []
    session._client = FakeClient()
    image = tmp_path / 'page.jpg'
    image.write_bytes(b'fake-jpeg')
    session._upload = lambda path: UploadedFile(path, 'file-page-1')  # type: ignore[method-assign]
    result = session.review_pages('pure review', None, (image,))
    assert result.response_id == 'response-1'
    request = session._client.responses.calls[0]
    assert request['tool_choice'] == 'none'
    assert 'previous_response_id' not in request
    assert 'tools' not in request
    assert request['instructions'] != 'system'
    assert request['input'][0]['content'][1] == {
        'type': 'input_image', 'file_id': 'file-page-1', 'detail': 'high',
    }


def test_reasoning_and_flex_applied_to_initial_followup_and_review(tmp_path: Path, job_factory) -> None:  # type: ignore[no-untyped-def]
    job_root = job_factory(tmp_path)
    yaml_path = job_root / "job.yaml"
    yaml_path.write_text(
        yaml_path.read_text().replace(
            "model: test-model",
            "model: gpt-6.1-sol\nreasoning:\n  effort: high\nprocessing:\n  mode: flex",
        )
    )
    job = load_job(job_root)
    session = object.__new__(OpenAIHostedSession)
    session.job = job
    session.bundle_path = tmp_path / "bundle.tar.gz"
    session.direct_files = ()
    session.system_prompt = "system"
    session.container_id = "container-1"
    session._uploaded = []
    session._client = FakeClient()
    session._upload = lambda path: UploadedFile(path, "test-page-file")  # type: ignore[method-assign]

    first = session.run_initial("initial")
    second = session.run_followup("repair", first.response_id)
    page = tmp_path / "page.png"
    page.write_bytes(b"mock")
    session.review_pages("review", None, (page,))
    assert len(session._client.responses.calls) == 3
    for request in session._client.responses.calls:
        assert request["model"] == "gpt-6.1-sol"
        assert request["reasoning"] == {"effort": "high"}
        assert request["service_tier"] == "flex"
    assert session._client.responses.calls[-1]["tool_choice"] == "none"


def test_default_request_omits_reasoning_and_tier(tmp_path: Path, job_factory) -> None:  # type: ignore[no-untyped-def]
    job = load_job(job_factory(tmp_path))
    session = object.__new__(OpenAIHostedSession)
    session.job = job
    session.direct_files = ()
    session.system_prompt = "system"
    session.container_id = "container-1"
    session._uploaded = []
    session._client = FakeClient()
    session.run_initial("test")
    request = session._client.responses.calls[0]
    assert "reasoning" not in request
    assert "service_tier" not in request


def test_standard_tier_is_explicit(tmp_path: Path, job_factory) -> None:  # type: ignore[no-untyped-def]
    root = job_factory(tmp_path)
    job_yaml = root / "job.yaml"
    job_yaml.write_text(job_yaml.read_text() + "\nprocessing:\n  mode: standard\n")
    job = load_job(root)
    session = object.__new__(OpenAIHostedSession)
    session.job = job
    session.direct_files = ()
    session.system_prompt = "system"
    session.container_id = "container-1"
    session._uploaded = []
    session._client = FakeClient()
    session.run_initial("test")
    assert session._client.responses.calls[0]["service_tier"] == "default"


def test_content_only_review_has_no_shell_access(tmp_path: Path, job_factory) -> None:  # type: ignore[no-untyped-def]
    job = load_job(job_factory(tmp_path))
    session = object.__new__(OpenAIHostedSession)
    session.job = job
    session.direct_files = ()
    session.system_prompt = 'system'
    session.container_id = 'container-1'
    session._uploaded = []
    session._client = FakeClient()
    session.review_text('check contents', None)
    call = session._client.responses.calls[0]
    assert call['tool_choice'] == 'none'
    assert 'previous_response_id' not in call
    assert 'tools' not in call
    assert call['input'][0]['content'] == [{'type': 'input_text', 'text': 'check contents'}]


def test_review_does_not_inherit_generator_context_or_files(tmp_path: Path, job_factory) -> None:  # type: ignore[no-untyped-def]
    job = load_job(job_factory(tmp_path))
    direct = job.root / 'input' / 'image.png'
    direct.write_bytes(b'image')
    session = object.__new__(OpenAIHostedSession)
    session.job = job
    session.direct_files = (direct,)
    session.system_prompt = 'generation instructions'
    session.container_id = 'container-1'
    session._uploaded = [UploadedFile(direct, 'file-direct')]
    session._client = FakeClient()
    session._upload = lambda path: UploadedFile(path, 'file-original-or-result')  # type: ignore[method-assign]
    generated = session.run_initial('write document')
    session.review_text('inventory', None)
    original = tmp_path / 'original.jpg'
    produced = tmp_path / 'produced.jpg'
    original.write_bytes(b'orig')
    produced.write_bytes(b'generated')
    session.review_pages('compare', None, (original, produced))
    repair = session.run_followup('fix drawing', generated.response_id)
    assert repair.response_id == 'response-4'
    gen, inventory, visual, repair_call = session._client.responses.calls
    assert 'previous_response_id' not in inventory
    assert 'previous_response_id' not in visual
    assert 'tools' not in inventory and 'tools' not in visual
    assert inventory['instructions'] != gen['instructions']
    assert visual['instructions'] != gen['instructions']
    assert len(inventory['input'][0]['content']) == 1
    assert [x['file_id'] for x in visual['input'][0]['content'][1:]] == [
        'file-original-or-result', 'file-original-or-result',
    ]
    assert repair_call['previous_response_id'] == generated.response_id
    assert repair_call['instructions'] == gen['instructions']


def test_reused_original_upload_is_not_repeated(tmp_path: Path, job_factory) -> None:  # type: ignore[no-untyped-def]
    job = load_job(job_factory(tmp_path))
    session = object.__new__(OpenAIHostedSession)
    session.job = job
    session.direct_files = ()
    session.system_prompt = 'generation'
    session.container_id = 'container-1'
    session._uploaded = []
    session._client = FakeClient()
    # Exercise the real _upload method with a fake OpenAI Files API.
    session._client.files = SimpleNamespace(create=lambda **kw: SimpleNamespace(id='source-upload'))
    source = tmp_path / 'source.jpg'
    source.write_bytes(b'source bytes')
    session.review_pages('first', None, (source,))
    session.review_pages('second', None, (source,))
    assert len(session._uploaded) == 1


def test_hosted_container_idle_expiration_is_independent_of_job_timeout(
    tmp_path: Path, job_factory,  # type: ignore[no-untyped-def]
) -> None:
    root = job_factory(tmp_path)
    yaml_path = root / "job.yaml"
    yaml_path.write_text(
        yaml_path.read_text().replace("timeout_seconds: 60", "timeout_seconds: 3600")
    )
    job = load_job(root)
    assert job.config.limits.timeout_seconds == 3600

    requests: list[dict[str, Any]] = []
    session = object.__new__(OpenAIHostedSession)
    session.job = job
    session.bundle_path = tmp_path / "job-bundle.tar.gz"
    session.bundle_path.write_bytes(b"job bundle")
    session.direct_files = ()
    session._uploaded = []

    class MockFiles:
        def create(self, **kwargs: Any) -> Any:
            return SimpleNamespace(id=f"file-{len(session._uploaded) + 1}")

    class MockContainers:
        def create(self, **kwargs: Any) -> Any:
            requests.append(kwargs)
            return SimpleNamespace(id="container-1")

    session._client = SimpleNamespace(files=MockFiles(), containers=MockContainers())
    session._prepare_remote()

    assert session.container_id == "container-1"
    assert requests[0]["expires_after"] == {
        "anchor": "last_active_at",
        "minutes": 20,
    }
    assert len(requests[0]["file_ids"]) == 2


def test_dynamic_lint_shell_bridge_verifies_exact_call_and_fresh_report(
    tmp_path: Path, job_factory,
) -> None:  # type: ignore[no-untyped-def]
    import json
    import re

    job = load_job(job_factory(tmp_path))
    session = object.__new__(OpenAIHostedSession)
    session.job = job
    session.container_id = 'container-1'

    class LintResponses:
        def __init__(self) -> None:
            self.corrupt_command = False
            self.code = 0
            self.command = ''
            self.stdout_override: str | None = None

        def create(self, **kwargs):
            request = kwargs['input'][0]['content'][0]['text']
            self.command = request.split('\n')[-1]
            command = self.command + ' echo invalid' if self.corrupt_command else self.command
            nonce = re.search(r'\b([0-9a-f]{32})$', self.command).group(1)
            payload = json.dumps({'nonce': nonce, 'findings': []})
            stdout = ('CA-DOLLAR-LINT-REPORT-V1 ' + payload + '\n'
                      if self.stdout_override is None else self.stdout_override)
            raw = {
                'output': [
                    {'type': 'shell_call', 'call_id': 'call-1',
                     'action': {'commands': [command]}},
                    {'type': 'shell_call_output', 'call_id': 'call-1',
                     'output': [{'stdout': stdout, 'stderr': '',
                                 'outcome': {'type': 'exit', 'exit_code': self.code}}]},
                ],
                'usage': {'input_tokens': 2, 'output_tokens': 1, 'total_tokens': 3},
            }
            return SimpleNamespace(id='lint-response', status='completed',
                                   model_dump=lambda mode: raw)

    responses = LintResponses()
    # No containers.files API at all: report travels through the verified
    # shell_call_output.stdout, even when hidden container files are unlisted.
    session._client = SimpleNamespace(responses=responses)
    payload, turn = session.run_dollar_lint()
    assert payload['findings'] == []
    assert turn.response_id == 'lint-response'
    assert 'lint-dollar-math.sh' in responses.command
    assert turn.usage['total_tokens'] == 3

    responses.corrupt_command = True
    with pytest.raises(RemoteAgentError, match='exact approved command'):
        session.run_dollar_lint()

    responses.corrupt_command = False
    responses.code = 1
    with pytest.raises(RemoteAgentError, match='lint compilation failed'):
        session.run_dollar_lint()

    responses.code = 0
    responses.stdout_override = 'CA-DOLLAR-LINT-REPORT-V1 {"nonce":"outdated", "findings":[]}\n'
    with pytest.raises(RemoteAgentError, match='stale'):
        session.run_dollar_lint()

    responses.stdout_override = ''
    with pytest.raises(RemoteAgentError, match='exactly one lint report'):
        session.run_dollar_lint()

    responses.stdout_override = ('CA-DOLLAR-LINT-REPORT-V1 {"nonce":"outdated","findings":[]}\n'
                                 'CA-DOLLAR-LINT-REPORT-V1 {"nonce":"outdated","findings":[]}\n')
    with pytest.raises(RemoteAgentError, match='exactly one lint report'):
        session.run_dollar_lint()

    responses.stdout_override = 'CA-DOLLAR-LINT-REPORT-V1 not-json\n'
    with pytest.raises(RemoteAgentError, match='dynamic ConTeXt lint failed'):
        session.run_dollar_lint()
