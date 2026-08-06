from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from context_agent.models import AgentTurn, RunReport


def write_report(report: RunReport, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(destination, report.as_dict())


def append_transcript(destination: Path, *, turn_number: int, phase: str, turn: AgentTurn) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "turn": turn_number,
        "phase": phase,
        "response_id": turn.response_id,
        "status": turn.status,
        "output_text": turn.output_text,
        "usage": turn.usage,
        "raw": turn.raw,
    }
    with destination.open("a", encoding="utf-8") as stream:
        json.dump(record, stream, ensure_ascii=False, default=str)
        stream.write("\n")


def _atomic_write_json(destination: Path, value: dict[str, Any]) -> None:
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)
