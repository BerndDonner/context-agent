from __future__ import annotations

import shutil
from pathlib import Path

from context_agent.models import AgentTurn, ResolvedJob
from context_agent.include_sync import make_snapshot
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
            if not source.is_file():
                continue
            target = destination / source.name
            shutil.copy2(source, target)
            copied[source.name] = target
        return copied

    def close(self) -> None:
        self.closed = True

    def _write_pdf_and_log(self) -> None:
        (self.remote / "main.pdf").write_bytes(b"%PDF-1.7\n%%EOF\n")
        (self.remote / "context.log").write_text("successful run", encoding="utf-8")
        make_snapshot(self.job.include_dir, self.remote / "include-snapshot.tar.gz")

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


class ReviewSession(FakeSession):
    """Visual review reports a missing printed solution, then accepts the repair."""

    def __init__(self, job: ResolvedJob, *, always_fail: bool = False) -> None:
        super().__init__(job)
        self.review_calls = 0
        self.always_fail = always_fail

    def _write_pdf_and_log(self) -> None:
        import fitz
        doc = fitz.open()
        doc.new_page().insert_text((72, 72), 'Aufgabe 1: Lösung 42')
        doc.save(self.remote / 'main.pdf')
        doc.close()
        (self.remote / 'context.log').write_text('successful run')
        make_snapshot(self.job.include_dir, self.remote / 'include-snapshot.tar.gz')

    def review_pages(self, prompt: str, previous_response_id: str,
                     pages: tuple[Path, ...]) -> AgentTurn:
        assert 'Original' in prompt
        assert pages and pages[0].read_bytes().startswith(b'\xff\xd8')
        self.review_calls += 1
        if self.review_calls == 1 or self.always_fail:
            text = ('{"findings":[{"type":"content","output_page":1,'
                    '"source_page":1,"message":"Originale Lösung fehlt",'
                    '"confidence":0.99}],"uncertainties":[]}')
        else:
            text = '{"findings":[],"uncertainties":[]}'
        return self._turn(f'v{self.review_calls}', text)

    def run_followup(self, prompt: str, previous_response_id: str) -> AgentTurn:
        self.followups.append(prompt)
        (self.remote / 'main.tex').write_text('reproduced solution')
        self._write_pdf_and_log()
        return self._turn(f'r{len(self.followups)+1}', 'repaired')


def test_reproduction_review_repairs_and_commits_includes(
    tmp_path: Path, job_factory,
) -> None:  # type: ignore[no-untyped-def]
    job_root = job_factory(tmp_path, max_turns=8)
    with (job_root / 'job.yaml').open('a') as f:
        f.write('\nreview:\n  reproduction: true\n  max_repairs: 2\n')
    captured: dict[str, ReviewSession] = {}

    def factory(job, bundle, direct, system):  # type: ignore[no-untyped-def]
        s = ReviewSession(job)
        captured['session'] = s
        return s

    report = run_job(job_root, session_factory=factory)
    assert report.status == 'success', report.errors
    assert report.review_repairs == 1
    assert report.agent_turns == 4
    assert captured['session'].review_calls == 2


def test_reproduction_fail_does_not_change_includes(
    tmp_path: Path, job_factory,
) -> None:  # type: ignore[no-untyped-def]
    job_root = job_factory(tmp_path, max_turns=8)
    (job_root / 'include/plotmod.lua').write_text('original')
    with (job_root / 'job.yaml').open('a') as f:
        f.write('\nreview:\n  reproduction: true\n  max_repairs: 1\n')

    class FailingSession(ReviewSession):
        def _write_pdf_and_log(self) -> None:
            (self.job.include_dir / 'plotmod.lua').write_text('original')
            super()._write_pdf_and_log()

    def factory(job, bundle, direct, system):  # type: ignore[no-untyped-def]
        return FailingSession(job, always_fail=True)

    report = run_job(job_root, session_factory=factory)
    assert report.status == 'failed'
    assert report.review_findings
    assert (job_root / 'include/plotmod.lua').read_text() == 'original'


def test_remote_include_is_applied_only_after_success(
    tmp_path: Path, job_factory,
) -> None:  # type: ignore[no-untyped-def]
    job_root = job_factory(tmp_path)
    (job_root / 'include/plotmod.lua').write_text('original')

    class IncludeSession(FakeSession):
        def _write_pdf_and_log(self) -> None:
            super()._write_pdf_and_log()
            remote_includes = self.remote / 'sandbox-include'
            remote_includes.mkdir(exist_ok=True)
            (remote_includes / 'plotmod.lua').write_text('new content')
            (remote_includes / 'extra.lua').write_text('additional helper')
            make_snapshot(remote_includes, self.remote / 'include-snapshot.tar.gz')

    report = run_job(job_root, session_factory=lambda job, bundle, direct, system: IncludeSession(job))
    assert report.status == 'success', report.errors
    assert report.include_changes == ['extra.lua', 'plotmod.lua']
    assert (job_root / 'include/plotmod.lua').read_text() == 'new content'
    assert (job_root / 'include/extra.lua').read_text() == 'additional helper'


def test_remote_includes_not_applied_when_review_fails(
    tmp_path: Path, job_factory,
) -> None:  # type: ignore[no-untyped-def]
    job_root = job_factory(tmp_path, max_turns=6)
    (job_root / 'include/plotmod.lua').write_text('original')
    with (job_root / 'job.yaml').open('a') as f:
        f.write('\nreview:\n  reproduction: true\n  max_repairs: 0\n')

    class FailedIncludeSession(ReviewSession):
        def _write_pdf_and_log(self) -> None:
            super()._write_pdf_and_log()
            remote_includes = self.remote / 'sandbox-include'
            remote_includes.mkdir(exist_ok=True)
            (remote_includes / 'plotmod.lua').write_text('unaudited change')
            make_snapshot(remote_includes, self.remote / 'include-snapshot.tar.gz')

    report = run_job(job_root, session_factory=lambda job, bundle, direct, system:
                     FailedIncludeSession(job, always_fail=True))
    assert report.status == 'failed'
    assert (job_root / 'include/plotmod.lua').read_text() == 'original'
