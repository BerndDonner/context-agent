from __future__ import annotations

from pathlib import Path

import pytest


def create_job(
    root: Path,
    *,
    quality_directory: str | None = None,
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

    quality_dir = (f"\nquality_directory: {quality_directory}\n"
                   if quality_directory is not None else "")
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
  max_quality_repairs: {max_repairs}
  timeout_seconds: 60
  max_output_tokens: 1000
quality: []
{quality_dir}""",
        encoding="utf-8",
    )
    return job


@pytest.fixture
def job_factory():  # type: ignore[no-untyped-def]
    return create_job


@pytest.fixture(autouse=True)
def fake_preflight_for_offline_tests(monkeypatch):
    """No network in tests; production always uses real stateless LLM preflight."""
    import context_agent.workflow as workflow
    def preflight(job, rules):
        return {'status':'passed','conflicts':[],'uncertainties':[],
                'plan':[[r.id] for r in rules]}
    # run_job looks up llm_preflight only at invocation time.
    monkeypatch.setattr(workflow, 'llm_preflight', preflight)
