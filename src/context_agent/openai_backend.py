from __future__ import annotations

import importlib
import json
import os
import shutil
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Protocol, cast

from context_agent.errors import ArtifactError, RemoteAgentError
from context_agent.models import AgentTurn, ResolvedJob


_CONTEXT_BUNDLE_HEADER = b"CONTEXT_AGENT_ARCHIVE_V1\n"


class AgentSession(Protocol):
    container_id: str | None

    def run_initial(self, prompt: str) -> AgentTurn: ...

    def run_followup(self, prompt: str, previous_response_id: str) -> AgentTurn: ...

    def sync_result(self, destination: Path) -> dict[str, Path]: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class UploadedFile:
    path: Path
    file_id: str


class OpenAIHostedSession:
    """One OpenAI Responses API session backed by a hosted shell container."""

    REMOTE_RESULT_PATHS: ClassVar[dict[str, str]] = {
        "main.tex": "/mnt/data/work/job/result/main.tex",
        "main.pdf": "/mnt/data/work/job/result/main.pdf",
        "context.log": "/mnt/data/work/job/result/context.log",
    }

    def __init__(
        self,
        job: ResolvedJob,
        bundle_path: Path,
        direct_files: tuple[Path, ...],
        system_prompt: str,
    ) -> None:
        self.job = job
        self.bundle_path = bundle_path
        self.direct_files = direct_files
        self.system_prompt = system_prompt
        self.container_id: str | None = None
        self._uploaded: list[UploadedFile] = []
        self._client = self._create_client(job.config.limits.timeout_seconds)
        self._prepare_remote()

    @staticmethod
    def _create_client(timeout_seconds: int) -> Any:
        try:
            module = importlib.import_module("openai")
        except ImportError as exc:
            raise RemoteAgentError(
                "The 'openai' package is not installed. "
                "Install context-agent with its runtime dependencies."
            ) from exc
        version = getattr(module, "__version__", "unknown")
        client_type = getattr(module, "OpenAI", None)
        if client_type is None:
            raise RemoteAgentError(f"unsupported openai package ({version}): OpenAI client missing")

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RemoteAgentError(
                "OPENAI_API_KEY is not set. Configure it in the environment "
                "before starting context-agent."
            )

        return client_type(
            api_key=api_key,
            timeout=float(timeout_seconds),
            max_retries=2,
        )

    def _upload(self, path: Path) -> UploadedFile:
        try:
            with path.open("rb") as stream:
                remote = self._client.files.create(
                    file=stream,
                    purpose="user_data",
                    expires_after={"anchor": "created_at", "seconds": 86400},
                )
        except Exception as exc:
            raise RemoteAgentError(f"failed to upload {path}: {exc}") from exc
        uploaded = UploadedFile(path=path, file_id=str(remote.id))
        self._uploaded.append(uploaded)
        return uploaded

    def _prepare_remote(self) -> None:
        bundle = self._upload(self.bundle_path)

        # Hosted containers automatically expand recognized archives. A complete
        # ConTeXt tree contains several thousand files and would exceed the container
        # attachment limit before the first model turn. Prefixing the XZ stream with a
        # private header keeps it as one opaque file. The runtime helper removes the
        # header and extracts ConTeXt only for one compilation.
        with tempfile.TemporaryDirectory(prefix="context-agent-upload-") as temporary:
            context_bundle_path = Path(temporary) / "context-lmtx.ctxbundle"
            _write_context_bundle(self.job.context_archive, context_bundle_path)
            context_bundle = self._upload(context_bundle_path)

            for path in self.direct_files:
                self._upload(path)

            expires_minutes = min(
                60, max(20, self.job.config.limits.timeout_seconds // 60 + 5)
            )
            try:
                container = self._client.containers.create(
                    name=f"context-agent-{self.job.root.name}",
                    file_ids=[item.file_id for item in self._uploaded],
                    memory_limit=self.job.config.runtime.memory_limit,
                    expires_after={"anchor": "last_active_at", "minutes": expires_minutes},
                )
            except Exception as exc:
                raise RemoteAgentError(f"failed to create hosted container: {exc}") from exc
            self.container_id = str(container.id)

        if bundle.file_id == context_bundle.file_id:  # defensive; should never happen
            raise RemoteAgentError("job bundle and ConTeXt bundle received identical file IDs")

    def _direct_content(self, prompt: str) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = [{"type": "input_text", "text": prompt}]
        direct_by_path = {item.path: item.file_id for item in self._uploaded}
        for path in self.direct_files:
            file_id = direct_by_path[path]
            suffix = path.suffix.lower()
            if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
                content.append({"type": "input_image", "file_id": file_id, "detail": "high"})
            else:
                content.append({"type": "input_file", "file_id": file_id})
        return content

    def _response(self, *, prompt: str, previous_response_id: str | None) -> AgentTurn:
        if self.container_id is None:
            raise RemoteAgentError("hosted container is not available")

        kwargs: dict[str, Any] = {
            "model": self.job.config.model,
            "instructions": self.system_prompt,
            "input": [
                {
                    "role": "user",
                    "content": self._direct_content(prompt)
                    if previous_response_id is None
                    else [{"type": "input_text", "text": prompt}],
                }
            ],
            "tools": [
                {
                    "type": "shell",
                    "environment": {
                        "type": "container_reference",
                        "container_id": self.container_id,
                    },
                }
            ],
            "tool_choice": "auto",
            "parallel_tool_calls": False,
            "max_output_tokens": self.job.config.limits.max_output_tokens,
            "store": True,
        }
        if previous_response_id is not None:
            kwargs["previous_response_id"] = previous_response_id

        try:
            response = self._client.responses.create(**kwargs)
        except Exception as exc:
            raise RemoteAgentError(f"Responses API call failed: {exc}") from exc

        raw = _model_dump(response)
        raw_usage: object = raw.get("usage")
        usage = cast(dict[str, Any], raw_usage) if isinstance(raw_usage, dict) else {}
        return AgentTurn(
            response_id=str(response.id),
            status=str(getattr(response, "status", "unknown")),
            output_text=_extract_output_text(response, raw),
            raw=raw,
            usage=usage,
        )

    def run_initial(self, prompt: str) -> AgentTurn:
        return self._response(prompt=prompt, previous_response_id=None)

    def run_followup(self, prompt: str, previous_response_id: str) -> AgentTurn:
        return self._response(prompt=prompt, previous_response_id=previous_response_id)

    def sync_result(self, destination: Path) -> dict[str, Path]:
        if self.container_id is None:
            raise ArtifactError("cannot sync artifacts without a container")
        destination.mkdir(parents=True, exist_ok=True)
        try:
            page = self._client.containers.files.list(
                self.container_id, limit=100, order="desc"
            )
            remote_files = list(page)
        except Exception as exc:
            raise ArtifactError(f"failed to list container files: {exc}") from exc

        selected: dict[str, Any] = {}
        for local_name, remote_path in self.REMOTE_RESULT_PATHS.items():
            matches = [
                item
                for item in remote_files
                if str(getattr(item, "path", "")) == remote_path
                or str(getattr(item, "path", "")).endswith(f"/job/result/{local_name}")
            ]
            if matches:
                selected[local_name] = max(
                    matches, key=lambda item: int(getattr(item, "created_at", 0))
                )

        downloaded: dict[str, Path] = {}
        for local_name, item in selected.items():
            try:
                content = self._client.containers.files.content.retrieve(
                    str(item.id), container_id=self.container_id
                )
                data = _binary_content(content)
            except Exception as exc:
                raise ArtifactError(f"failed to download {local_name}: {exc}") from exc
            target = destination / local_name
            target.write_bytes(data)
            downloaded[local_name] = target
        return downloaded

    def close(self) -> None:
        if self.job.config.runtime.keep_remote:
            return
        if self.container_id is not None:
            with suppress(Exception):
                self._client.containers.delete(self.container_id)
        for item in self._uploaded:
            with suppress(Exception):
                self._client.files.delete(item.file_id)



def _write_context_bundle(source: Path, destination: Path) -> None:
    """Wrap an XZ archive so hosted containers do not auto-expand it on attachment."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as input_stream, destination.open("wb") as output_stream:
        output_stream.write(_CONTEXT_BUNDLE_HEADER)
        shutil.copyfileobj(input_stream, output_stream, length=1024 * 1024)

def _extract_output_text(response: Any, raw: dict[str, Any]) -> str:
    direct = getattr(response, "output_text", None)
    if isinstance(direct, str):
        return direct

    texts: list[str] = []
    output = raw.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, dict):
                    continue
                text = part.get("text")
                if isinstance(text, str):
                    texts.append(text)
    return "\n".join(texts)


def _model_dump(value: Any) -> dict[str, Any]:
    method = getattr(value, "model_dump", None)
    if callable(method):
        dumped = method(mode="json")
        if isinstance(dumped, dict):
            return dumped
    try:
        serialized = json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return {"repr": repr(value)}
    return serialized if isinstance(serialized, dict) else {"value": serialized}


def _binary_content(value: Any) -> bytes:
    read = getattr(value, "read", None)
    if callable(read):
        data = read()
        if isinstance(data, bytes):
            return data
    content = getattr(value, "content", None)
    if isinstance(content, bytes):
        return content
    iter_bytes = getattr(value, "iter_bytes", None)
    if callable(iter_bytes):
        return b"".join(iter_bytes())
    raise TypeError("OpenAI binary response exposes no supported byte reader")
