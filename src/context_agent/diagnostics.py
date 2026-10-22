"""Append-only, low-sensitivity execution telemetry for failure investigation.

Diagnostic records deliberately omit prompts, edit contents, command strings,
model tool output, environment variables and exception messages: these may
contain student content or credentials. The transcript remains a separate artifact.
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


_SAFE_KEYS = frozenset({
    'phase', 'process_id', 'attempt', 'operation', 'command_sha256', 'command_bytes',
    'argv_count', 'response_id', 'request_id', 'response_status', 'incomplete_reason',
    'shell_call_status', 'shell_output_status', 'shell_calls', 'shell_outputs',
    'elapsed_ms', 'exception_type', 'status_code', 'error_code', 'container_id',
    'file_id', 'remote_path', 'payload_sha256', 'payload_bytes', 'edit_count',
    'file_count', 'stdout_bytes', 'stderr_bytes', 'exit_code', 'process_status',
    'retry', 'api_calls', 'reason_code', 'total_tokens', 'input_tokens',
    'output_tokens', 'max_output_tokens', 'source_sha256', 'stage',
})


def record_event(path: Path, event: str, **metadata: Any) -> None:
    """Durably append one filtered JSONL record; logging must not break a job."""
    try:
        record: dict[str, Any] = {
            'timestamp': datetime.now(UTC).isoformat(timespec='milliseconds'),
            'event': event,
        }
        for key, value in metadata.items():
            if key in _SAFE_KEYS and (value is None or type(value) in (str, int, bool, float)):
                record[key] = value if not isinstance(value, str) else value[:256]
        data = (json.dumps(record, ensure_ascii=False, separators=(',', ':')) + '\n').encode()
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        # Observability must never interfere with compilation or rollback.
        pass


def exception_metadata(exc: Exception) -> dict[str, Any]:
    """Only structured transport metadata; never log str(exc)."""
    status = getattr(exc, 'status_code', None)
    request_id = getattr(exc, 'request_id', None)
    code = getattr(exc, 'code', None)
    return {
        'exception_type': type(exc).__name__,
        'status_code': status if type(status) is int else None,
        'request_id': request_id if isinstance(request_id, str) else None,
        'error_code': code if isinstance(code, str) else None,
    }
