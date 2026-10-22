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
    'rejected_candidate_saved', 'selected_rule_count', 'plan_type', 'plan_batch_count', 'plan_item_count',
    'preflight_status', 'output_bytes', 'output_sha256',
    'plan_unknown_count', 'plan_duplicate_count', 'plan_missing_count',
    'call_id_sha256', 'command_count', 'numeric_difference_count', 'finding_count',
    'worsened_rule_count', 'snapshot_sha256', 'guard_type', 'runtime_resolution_count', 'batch_start_page', 'batch_end_page',
    'review_attempt', 'review_max_attempts', 'review_error_code', 'review_batch_status',
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


def shell_output_events(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Safe metadata for generator shell actions; never expose command contents.

    A response may include multiple commands and outputs. Return one event per
    command/output, preserving only hashes, lengths and execution status.
    """
    import hashlib
    events: list[dict[str, Any]] = []
    for item in raw.get('output', []):
        if not isinstance(item, dict):
            continue
        kind = item.get('type')
        if kind not in ('shell_call', 'shell_call_output'):
            continue
        call_id = item.get('call_id')
        metadata: dict[str, Any] = {
            'call_id_sha256': (hashlib.sha256(call_id.encode()).hexdigest()
                               if isinstance(call_id, str) else None),
            'shell_call_status': item.get('status'),
        }
        if kind == 'shell_call':
            action = item.get('action')
            commands = action.get('commands') if isinstance(action, dict) else None
            metadata['command_count'] = len(commands) if isinstance(commands, list) else 0
            events.append({'event': 'generator_shell_call', **metadata})
            if isinstance(commands, list):
                for command in commands:
                    if not isinstance(command, str):
                        continue
                    raw_command = command.encode('utf-8')
                    events.append({'event': 'generator_shell_command',
                                   'call_id_sha256': metadata['call_id_sha256'],
                                   'command_sha256': hashlib.sha256(raw_command).hexdigest(),
                                   'command_bytes': len(raw_command)})
        else:
            # Never log output text. Record per-command exit status and lengths
            # only; useful when generator compilation fails despite a completed
            # Responses API call.
            outputs = item.get('output')
            if isinstance(outputs, list):
                for output in outputs:
                    if not isinstance(output, dict):
                        continue
                    outcome = output.get('outcome')
                    result = {'event': 'generator_shell_result',
                              'call_id_sha256': metadata['call_id_sha256']}
                    if isinstance(outcome, dict):
                        exit_code = outcome.get('exit_code')
                        if type(exit_code) is int:
                            result['exit_code'] = exit_code
                    for stream in ('stdout', 'stderr'):
                        value = output.get(stream)
                        if isinstance(value, str):
                            result[stream + '_bytes'] = len(value.encode('utf-8'))
                    events.append(result)
            events.append({'event': 'generator_shell_output', **metadata})
    return events
