from __future__ import annotations

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
        assert file_id in {"cfile-tex", "cfile-pdf", "cfile-log"}
        assert container_id == "container-1"
        payload = {
            "cfile-tex": b"\\starttext test \\stoptext",
            "cfile-pdf": b"%PDF-1.7\n",
            "cfile-log": b"success",
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
    assert set(downloaded) == {"main.tex", "main.pdf", "context.log"}
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
