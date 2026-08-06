from __future__ import annotations

import shutil
from pathlib import Path

from context_agent.models import AgentTurn, ResolvedJob
from context_agent.openai_backend import AgentSession
from context_agent.workflow import run_job


class FakeSession(AgentSession):
    container_id = "fake-container"

    def __init__(self, job: ResolvedJob, *, missing_first: bool = False) -> None:
        self.job = job
        self.remote = job.root.parent / "remote-result"
        self.remote.mkdir(exist_ok=True)
        self.missing_first = missing_first
        self.followups: list[str] = []
        self.closed = False

    def run_initial(self, prompt: str) -> AgentTurn:
        assert "bootstrap-context.sh" in prompt
        (self.remote / "main.tex").write_text("\\starttext\nBAD\n\\stoptext\n")
        if not self.missing_first:
            self._write_pdf_and_log()
        return self._turn("r1", "initial complete")

    def run_followup(self, prompt: str, previous_response_id: str) -> AgentTurn:
        self.followups.append(prompt)
        if "main.pdf" in prompt or "context.log" in prompt:
            self._write_pdf_and_log()
        if "bad-word" in prompt:
            (self.remote / "main.tex").write_text("\\starttext\nGOOD\n\\stoptext\n")
            self._write_pdf_and_log()
        return self._turn(f"r{len(self.followups) + 1}", "repair complete")

    def sync_result(self, destination: Path) -> dict[str, Path]:
        copied: dict[str, Path] = {}
        destination.mkdir(exist_ok=True)
        for source in self.remote.iterdir():
            target = destination / source.name
            shutil.copy2(source, target)
            copied[source.name] = target
        return copied

    def close(self) -> None:
        self.closed = True

    def _write_pdf_and_log(self) -> None:
        (self.remote / "main.pdf").write_bytes(b"%PDF-1.7\n%%EOF\n")
        (self.remote / "context.log").write_text("successful run", encoding="utf-8")

    @staticmethod
    def _turn(response_id: str, text: str) -> AgentTurn:
        return AgentTurn(
            response_id=response_id,
            status="completed",
            output_text=text,
            raw={"id": response_id},
            usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        )


def test_workflow_repairs_missing_artifacts(tmp_path: Path, job_factory) -> None:  # type: ignore[no-untyped-def]
    job_root = job_factory(tmp_path)
    captured: dict[str, FakeSession] = {}

    def factory(job, bundle, direct, system):  # type: ignore[no-untyped-def]
        assert bundle.is_file()
        session = FakeSession(job, missing_first=True)
        captured["session"] = session
        return session

    report = run_job(job_root, session_factory=factory)
    assert report.status == "success"
    assert report.agent_turns == 2
    assert report.compile_success
    assert captured["session"].closed


def test_workflow_repairs_nogo_findings(tmp_path: Path, job_factory) -> None:  # type: ignore[no-untyped-def]
    job_root = job_factory(tmp_path, nogo_directory="nogos")
    nogos = job_root / "nogos"
    nogos.mkdir()
    (nogos / "bad_word.py").write_text(
        """
from context_agent.models import NogoFinding

def check(context):
    if 'BAD' in context.main_tex.read_text(encoding='utf-8'):
        return [NogoFinding(rule_id='bad-word', message='BAD ist verboten', file='main.tex')]
    return []
""",
        encoding="utf-8",
    )

    def factory(job, bundle, direct, system):  # type: ignore[no-untyped-def]
        return FakeSession(job)

    report = run_job(job_root, session_factory=factory)
    assert report.status == "success"
    assert report.nogo_repairs == 1
    assert report.findings == []
    assert "GOOD" in (job_root / "result" / "main.tex").read_text()


class BrokenRepairSession(FakeSession):
    def run_followup(self, prompt: str, previous_response_id: str) -> AgentTurn:
        self.followups.append(prompt)
        if "bad-word" in prompt:
            (self.remote / "main.tex").write_text("BROKEN", encoding="utf-8")
            (self.remote / "main.pdf").write_bytes(b"not a pdf")
            (self.remote / "context.log").write_text("compile failed", encoding="utf-8")
        return self._turn(f"r{len(self.followups) + 1}", "broken repair")


def test_workflow_preserves_last_complete_result(tmp_path: Path, job_factory) -> None:  # type: ignore[no-untyped-def]
    job_root = job_factory(tmp_path, nogo_directory="nogos", max_turns=2, max_repairs=1)
    nogos = job_root / "nogos"
    nogos.mkdir()
    (nogos / "bad_word.py").write_text(
        """
from context_agent.models import NogoFinding

def check(context):
    if 'BAD' in context.main_tex.read_text(encoding='utf-8'):
        return [NogoFinding(rule_id='bad-word', message='BAD ist verboten')]
    return []
""",
        encoding="utf-8",
    )

    def factory(job, bundle, direct, system):  # type: ignore[no-untyped-def]
        return BrokenRepairSession(job)

    report = run_job(job_root, session_factory=factory)
    assert report.status == "failed"
    assert (job_root / "result" / "main.pdf").read_bytes().startswith(b"%PDF-")
    assert "BAD" in (job_root / "result" / "main.tex").read_text()
