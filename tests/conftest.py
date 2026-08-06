from __future__ import annotations

from pathlib import Path

import pytest


def create_job(
    root: Path,
    *,
    nogo_directory: str | None = None,
    max_turns: int = 6,
    max_repairs: int = 3,
) -> Path:
    job = root / "job"
    for directory in ("template", "input", "include", "references", "result"):
        (job / directory).mkdir(parents=True, exist_ok=True)

    archive = root / "context-lmtx-ready.tar.xz"
    archive.write_bytes(b"not needed by fake backend")
    (job / "task.md").write_text("Erstelle ein Dokument.", encoding="utf-8")
    (job / "template" / "template.tex").write_text(
        "\\setupbodyfont[modern]\\n"
        "\\starttext\\nALT\\n\\stoptext\\n"
        "% ignored\\n\\stoptext\\n",
        encoding="utf-8",
    )
    (job / "input" / "notes.md").write_text("Hinweise", encoding="utf-8")

    nogo = f"\nnogo_directory: {nogo_directory}\n" if nogo_directory is not None else ""
    (job / "job.yaml").write_text(
        f"""model: test-model
task: task.md
template:
  path: template/template.tex
inputs:
  - path: input/notes.md
    role: content
    policy: guidance
references: []
runtime:
  context_archive: {archive.as_posix()}
  memory_limit: 1g
  keep_remote: false
limits:
  max_agent_turns: {max_turns}
  max_nogo_repairs: {max_repairs}
  timeout_seconds: 60
  max_output_tokens: 1000
{nogo}""",
        encoding="utf-8",
    )
    return job


@pytest.fixture
def job_factory():  # type: ignore[no-untyped-def]
    return create_job
