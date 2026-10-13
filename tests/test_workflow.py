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

    def run_dollar_lint(self, *, max_api_calls: int):
        # A fake container whose compiled documents contain no dollar math.
        return {'nonce': 'fake', 'findings': []}, AgentTurn(
            response_id='lint-fake', status='completed', output_text='',
            raw={'id': 'lint-fake'},
            usage={'input_tokens': 1, 'output_tokens': 1, 'total_tokens': 2})

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
    assert report.agent_turns == 3  # generation + repair + dynamic lint
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




def configure_reproduction_source(job_root: Path) -> None:
    """Upgrade the standard guidance input into a faithful reproduction source."""
    yaml = job_root / 'job.yaml'
    yaml.write_text(yaml.read_text().replace('policy: guidance', 'policy: verbatim'))

class ReviewSession(FakeSession):
    """Visual review reports a missing printed solution, then accepts the repair."""

    def __init__(self, job: ResolvedJob, *, always_fail: bool = False) -> None:
        super().__init__(job)
        self.review_calls = 0
        self.always_fail = always_fail

    def review_text(self, prompt: str, previous_response_id: str) -> AgentTurn:
        if 'ERSTELLE NUR EIN INHALTSINVENTAR' in prompt:
            return self._turn('inventory', '{"entries":[{"source_page":1,"kind":"text",'
                              '"anchor":"Aufgabe 1","detail":"Lösung 42"}],"uncertainties":[]}')
        if 'ABSCHLIESSENDE INHALTSKONTROLLE' in prompt:
            return self._turn('missing', '{"missing":[],"uncertainties":[]}')
        raise AssertionError(prompt)

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
        if 'UNABHÄNGIGE INHALTSKONTROLLE' in prompt:
            return self._turn('content', '{"present":["s1p1-1"],"mismatches":[],"uncertainties":[]}')
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
    job_root = job_factory(tmp_path, max_turns=15)
    configure_reproduction_source(job_root)
    with (job_root / 'job.yaml').open('a') as f:
        f.write('\nreview:\n  reproduction: true\n  max_content_repairs: 2\n  max_visual_repairs: 2\n')
    captured: dict[str, ReviewSession] = {}

    def factory(job, bundle, direct, system):  # type: ignore[no-untyped-def]
        s = ReviewSession(job)
        captured['session'] = s
        return s

    report = run_job(job_root, session_factory=factory)
    assert report.status == 'success', report.errors
    assert report.review_repairs == 1
    assert report.agent_turns == 9  # includes two dynamic ConTeXt lint calls
    assert captured['session'].review_calls == 2


def test_reproduction_fail_does_not_change_includes(
    tmp_path: Path, job_factory,
) -> None:  # type: ignore[no-untyped-def]
    job_root = job_factory(tmp_path, max_turns=15)
    configure_reproduction_source(job_root)
    (job_root / 'include/plotmod.lua').write_text('original')
    with (job_root / 'job.yaml').open('a') as f:
        f.write('\nreview:\n  reproduction: true\n  max_content_repairs: 1\n  max_visual_repairs: 1\n')

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
    configure_reproduction_source(job_root)
    (job_root / 'include/plotmod.lua').write_text('original')
    with (job_root / 'job.yaml').open('a') as f:
        f.write('\nreview:\n  reproduction: true\n  max_content_repairs: 0\n  max_visual_repairs: 0\n')

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


def test_reproduction_review_and_repair_obey_requested_scope(
    tmp_path: Path, job_factory,
) -> None:  # type: ignore[no-untyped-def]
    job_root = job_factory(tmp_path, max_turns=15)
    configure_reproduction_source(job_root)
    (job_root / 'task.md').write_text(
        'Reproduce chapter B including printed solutions. Omit chapter A explicitly.',
        encoding='utf-8',
    )
    with (job_root / 'job.yaml').open('a') as stream:
        stream.write('\nreview:\n  reproduction: true\n  max_content_repairs: 2\n  max_visual_repairs: 2\n')
    prompts: list[str] = []

    class ScopeSession(ReviewSession):
        def review_pages(self, prompt: str, previous_response_id: str,
                         pages: tuple[Path, ...]) -> AgentTurn:
            prompts.append(prompt)
            assert 'Omit chapter A explicitly' in prompt
            assert 'Reproduce chapter B including printed solutions' in prompt
            return super().review_pages(prompt, previous_response_id, pages)

        def run_followup(self, prompt: str, previous_response_id: str) -> AgentTurn:
            assert 'Omit chapter A explicitly' in prompt
            assert 'Füge keine ausdrücklich ausgeschlossenen Quellbestandteile hinzu' in prompt
            assert 'Bewahre ALLE Originalinhalte' not in prompt
            return super().run_followup(prompt, previous_response_id)

    report = run_job(job_root, session_factory=lambda job, bundle, direct, system:
                     ScopeSession(job))
    assert report.status == 'success', report.errors
    assert report.review_repairs == 1
    assert len(prompts) == 4  # content and visual review, twice


def test_multibatch_review_defers_global_omission_check(
    tmp_path: Path, job_factory,
) -> None:  # type: ignore[no-untyped-def]
    """Multi-page scans must not prompt a false omission before all pages are seen."""
    job_root = job_factory(tmp_path, max_turns=15)
    configure_reproduction_source(job_root)
    (job_root / 'task.md').write_text('Reproduce all tasks and solutions from scan.')
    with (job_root / 'job.yaml').open('a') as stream:
        stream.write('\nreview:\n  reproduction: true\n  pages_per_batch: 2\n  max_content_repairs: 0\n  max_visual_repairs: 0\n')
    review_prompts: list[str] = []

    class MultiPageSession(FakeSession):
        def review_text(self, prompt: str, previous_response_id: str) -> AgentTurn:
            return self._turn('source', '{"entries":[{"source_page":1,"kind":"text",'
                              '"anchor":"Exercise 1","detail":"Exercise 1"}],"uncertainties":[]}')

        def _write_pdf_and_log(self) -> None:
            import fitz
            doc = fitz.open()
            for index in range(5):
                doc.new_page().insert_text((70, 70), f'Exercise {index + 1}')
            doc.save(self.remote / 'main.pdf')
            doc.close()
            (self.remote / 'context.log').write_text('ok')
            make_snapshot(self.job.include_dir, self.remote / 'include-snapshot.tar.gz')

        def review_pages(self, prompt: str, previous_response_id: str,
                         pages: tuple[Path, ...]) -> AgentTurn:
            if 'UNABHÄNGIGE INHALTSKONTROLLE' in prompt:
                return self._turn('content', '{"present":["s1p1-1"],"mismatches":[],"uncertainties":[]}')
            review_prompts.append(prompt)
            assert len(pages) <= 2
            if len(review_prompts) == 3:
                # Each stateless visual batch can only report its own page.
                return self._turn('v3', '{"findings":[{"type":"visual",'
                                  '"output_page":5,"source_page":1,"message":"clipped",'
                                  '"confidence":0.99}],"uncertainties":[]}')
            return self._turn(f'v{len(review_prompts)}',
                              '{"findings":[],"uncertainties":[]}')

    report = run_job(job_root, session_factory=lambda job, bundle, direct, system:
                     MultiPageSession(job))
    assert report.status == 'failed'  # Reproduction repair deliberately disabled
    assert report.review_findings
    assert 'PDF-Seite 5' in report.review_findings[0].message
    assert len(review_prompts) == 3
    assert all('SEPARATEN Inhaltsprüfung' in prompt for prompt in review_prompts)
    assert all('unabhängig' in prompt.lower() or 'EIGENSTÄNDIGE' in prompt for prompt in review_prompts)


def test_unresolved_source_uncertainty_blocks_success_and_include_sync(
    tmp_path: Path, job_factory,
) -> None:  # type: ignore[no-untyped-def]
    job_root = job_factory(tmp_path, max_turns=12)
    configure_reproduction_source(job_root)
    (job_root / 'include/plotmod.lua').write_text('original')
    with (job_root / 'job.yaml').open('a') as stream:
        stream.write('\nreview:\n  reproduction: true\n')

    class UncertainSession(ReviewSession):
        def review_text(self, prompt: str, previous_response_id: str) -> AgentTurn:
            result = super().review_text(prompt, previous_response_id)
            if 'ERSTELLE NUR EIN INHALTSINVENTAR' in prompt:
                return self._turn('inventory',
                                  '{"entries":[{"source_page":1,"kind":"text",'
                                  '"anchor":"Aufgabe 1","detail":"Lösung 42"}],'
                                  '"uncertainties":["Quelle teilweise unleserlich"]}')
            return result

        def review_pages(self, prompt: str, previous_response_id: str,
                         pages: tuple[Path, ...]) -> AgentTurn:
            if 'UNABHÄNGIGE INHALTSKONTROLLE' in prompt:
                return super().review_pages(prompt, previous_response_id, pages)
            self.review_calls += 1
            return self._turn('visual', '{"findings":[],"uncertainties":[]}')

        def _write_pdf_and_log(self) -> None:
            super()._write_pdf_and_log()
            added = self.remote / 'sandbox-include'
            added.mkdir(exist_ok=True)
            (added / 'plotmod.lua').write_text('must not replace original')
            make_snapshot(added, self.remote / 'include-snapshot.tar.gz')

    report = run_job(job_root, session_factory=lambda job, bundle, direct, system:
                     UncertainSession(job))
    assert report.status == 'needs_review', report.errors
    assert report.content_uncertainties == ['Quelle teilweise unleserlich']
    assert not report.include_changes
    assert (job_root / 'include/plotmod.lua').read_text() == 'original'
    assert report.review_history


def test_content_mismatch_triggers_repair_then_visual_audit(
    tmp_path: Path, job_factory,
) -> None:  # type: ignore[no-untyped-def]
    root = job_factory(tmp_path, max_turns=12)
    configure_reproduction_source(root)
    (root / 'job.yaml').open('a').write('\nreview:\n  reproduction: true\n  max_content_repairs: 2\n  max_visual_repairs: 2\n')

    class ContentRepairSession(ReviewSession):
        def __init__(self, job):  # type: ignore[no-untyped-def]
            super().__init__(job)
            self.content_calls = 0

        def review_pages(self, prompt: str, previous_response_id: str,
                         pages: tuple[Path, ...]) -> AgentTurn:
            if 'UNABHÄNGIGE INHALTSKONTROLLE' in prompt:
                self.content_calls += 1
                if self.content_calls == 1:
                    return self._turn('incorrect',
                                      '{"present":[],"mismatches":[{"id":"s1p1-1",'
                                      '"output_page":1,"message":"42 wurde zu 43",'
                                      '"confidence":0.99}],"uncertainties":[]}')
                return self._turn('correct',
                                  '{"present":["s1p1-1"],"mismatches":[],"uncertainties":[]}')
            self.review_calls += 1
            return self._turn('visual-ok', '{"findings":[],"uncertainties":[]}')

        def run_followup(self, prompt: str, previous_response_id: str) -> AgentTurn:
            assert '42 wurde zu 43' in prompt
            return super().run_followup(prompt, previous_response_id)

    report = run_job(root, session_factory=lambda job, bundle, direct, system:
                     ContentRepairSession(job))
    assert report.status == 'success', report.errors
    assert report.review_repairs == 1
    assert report.content_findings == []
    assert any(item['phase'] == 'content' and item['findings']
               for item in report.review_history)
    assert report.usage_by_phase[-1]['phase'] == 'review-reproduction'


def test_scanned_pdf_is_inventoried_from_images_without_ocr(
    tmp_path: Path, job_factory,
) -> None:  # type: ignore[no-untyped-def]
    import fitz

    root = job_factory(tmp_path, max_turns=12)
    # An image-only PDF simulates a scanned worksheet including printed solutions.
    scan = root / 'input/scan.pdf'
    document = fitz.open()
    page = document.new_page()
    pixel_map = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 80, 40), 0)
    pixel_map.clear_with(255)
    page.insert_image(fitz.Rect(40, 40, 120, 80), pixmap=pixel_map)
    document.save(scan)
    document.close()
    config = root / 'job.yaml'
    config.write_text(config.read_text().replace(
        'input/notes.md\n    role: content\n    policy: guidance',
        'input/scan.pdf\n    role: recreate\n    policy: verbatim',
    ) + '\nreview:\n  reproduction: true\n')

    class ScanSession(ReviewSession):
        def review_pages(self, prompt: str, previous_response_id: str,
                         pages: tuple[Path, ...]) -> AgentTurn:
            if 'ERSTELLE NUR EIN INHALTSINVENTAR' in prompt:
                assert pages[0].read_bytes().startswith(b'\xff\xd8')
                assert 'input/scan.pdf' in prompt
                return self._turn('source',
                                  '{"entries":[{"source_page":1,"kind":"solution",'
                                  '"anchor":"Aufgabe 1","detail":"Lösung: 42"}],'
                                  '"uncertainties":[]}')
            if 'UNABHÄNGIGE INHALTSKONTROLLE' in prompt:
                return self._turn('present',
                                  '{"present":["s1p1-1"],"mismatches":[],"uncertainties":[]}')
            self.review_calls += 1
            return self._turn('visual', '{"findings":[],"uncertainties":[]}')

    report = run_job(root, session_factory=lambda job, bundle, direct, system:
                     ScanSession(job))
    assert report.status == 'success', report.errors
    assert report.source_inventory[0]['kind'] == 'solution'
    assert len(report.usage_by_phase) == 5
    assert [phase['phase'] for phase in report.usage_by_phase] == [
        'inventory-source', 'initial', 'nogo-dollar-lint', 'review-content', 'review-reproduction',
    ]


def test_preinventory_and_reviews_are_stateless_but_repairs_keep_generation_chain(
    tmp_path: Path, job_factory,
) -> None:  # type: ignore[no-untyped-def]
    root = job_factory(tmp_path, max_turns=12)
    configure_reproduction_source(root)
    (root / 'job.yaml').open('a').write('\nreview:\n  reproduction: true\n')

    class ChainSession(ReviewSession):
        def __init__(self, job):  # type: ignore[no-untyped-def]
            super().__init__(job)
            self.generation_id = None
            self.inventory_complete = False
            self.seen_visual = False

        def review_text(self, prompt: str, previous_response_id: str | None) -> AgentTurn:
            assert previous_response_id is None
            assert self.generation_id is None, 'Inventory must precede generation'
            self.inventory_complete = True
            return super().review_text(prompt, previous_response_id)

        def run_initial(self, prompt: str) -> AgentTurn:
            assert self.inventory_complete
            assert 'VORAB ERSTELLTES QUELLENINVENTAR' in prompt
            result = super().run_initial(prompt)
            self.generation_id = result.response_id
            return result

        def review_pages(self, prompt: str, previous_response_id: str | None,
                         pages: tuple[Path, ...]) -> AgentTurn:
            assert previous_response_id is None
            result = super().review_pages(prompt, previous_response_id, pages)
            if 'Prüfe AUSSCHLIESSLICH' in prompt:
                self.seen_visual = True
            return result

        def run_followup(self, prompt: str, previous_response_id: str) -> AgentTurn:
            assert previous_response_id == self.generation_id
            return super().run_followup(prompt, previous_response_id)

    captured: list[ChainSession] = []
    def factory(job, bundle, direct, system):  # type: ignore[no-untyped-def]
        session = ChainSession(job)
        captured.append(session)
        return session

    report = run_job(root, session_factory=factory)
    assert report.status == 'success', report.errors
    assert captured[0].seen_visual
    assert report.review_repairs == 1
    assert report.usage_by_phase[0]['phase'] == 'inventory-source'


def test_visual_comparison_gets_original_scan_again_in_every_batch(
    tmp_path: Path, job_factory,
) -> None:  # type: ignore[no-untyped-def]
    import fitz
    root = job_factory(tmp_path, max_turns=15)
    scan = root / 'input/scan.pdf'
    source_doc = fitz.open()
    for i in range(2):
        source_doc.new_page().insert_text((70, 70), f'Scan original {i + 1}')
    source_doc.save(scan)
    source_doc.close()
    config = root / 'job.yaml'
    config.write_text(config.read_text().replace(
        'input/notes.md\n    role: content\n    policy: guidance',
        'input/scan.pdf\n    role: recreate\n    policy: verbatim',
    ) + '\nreview:\n  reproduction: true\n  pages_per_batch: 1\n  max_content_repairs: 0\n  max_visual_repairs: 0\n')

    class SourceAgainSession(ReviewSession):
        def __init__(self, job):  # type: ignore[no-untyped-def]
            super().__init__(job)
            self.visual_calls = 0

        def _write_pdf_and_log(self) -> None:
            doc = fitz.open()
            for i in range(2):
                doc.new_page().insert_text((70, 70), f'Scan original {i + 1}')
            doc.save(self.remote / 'main.pdf')
            doc.close()
            (self.remote / 'context.log').write_text('OK')
            make_snapshot(self.job.include_dir, self.remote / 'include-snapshot.tar.gz')

        def review_pages(self, prompt: str, previous_response_id: str | None,
                         pages: tuple[Path, ...]) -> AgentTurn:
            assert previous_response_id is None
            if 'ERSTELLE NUR EIN INHALTSINVENTAR' in prompt:
                page = 2 if 'Quelle-Seiten 2 bis 2' in prompt else 1
                return self._turn('source', '{"entries":[{"source_page":' + str(page) +
                                  ',"kind":"text","anchor":"Original",'
                                  '"detail":"Scan original"}],"uncertainties":[]}')
            if 'UNABHÄNGIGE INHALTSKONTROLLE' in prompt:
                return self._turn('content', '{"present":["s1p1-1","s1p2-1"],'
                                  '"mismatches":[],"uncertainties":[]}')
            self.visual_calls += 1
            assert len(pages) == 3  # Original pages 1, 2 + one output page
            assert 'input/scan.pdf, Originalseite 1' in prompt
            assert 'input/scan.pdf, Originalseite 2' in prompt
            assert all(p.is_file() for p in pages)
            return self._turn('visual', '{"findings":[],"uncertainties":[]}')

    captured: list[SourceAgainSession] = []
    def factory(job, bundle, direct, system):  # type: ignore[no-untyped-def]
        session = SourceAgainSession(job)
        captured.append(session)
        return session
    report = run_job(root, session_factory=factory)
    assert report.status == 'success', report.errors
    assert captured[0].visual_calls == 2


def test_missing_content_check_sees_all_output_pages_without_previous_context(
    tmp_path: Path, job_factory,
) -> None:  # type: ignore[no-untyped-def]
    import fitz
    root = job_factory(tmp_path, max_turns=12)
    configure_reproduction_source(root)
    (root / 'job.yaml').open('a').write(
        '\nreview:\n  reproduction: true\n  pages_per_batch: 1\n  max_content_repairs: 0\n  max_visual_repairs: 0\n')

    class MissingSession(FakeSession):
        def __init__(self, job):  # type: ignore[no-untyped-def]
            super().__init__(job)
            self.missing_images = 0

        def _write_pdf_and_log(self) -> None:
            doc = fitz.open()
            for index in range(3):
                doc.new_page().insert_text((70, 70), f'Output {index + 1}')
            doc.save(self.remote / 'main.pdf')
            doc.close()
            (self.remote / 'context.log').write_text('OK')
            make_snapshot(self.job.include_dir, self.remote / 'include-snapshot.tar.gz')

        def review_text(self, prompt: str, previous_response_id: str | None) -> AgentTurn:
            assert previous_response_id is None
            return self._turn('inventory', '{"entries":[{"source_page":1,"kind":"solution",'
                              '"anchor":"Lösung","detail":"42"}],"uncertainties":[]}')

        def review_pages(self, prompt: str, previous_response_id: str | None,
                         pages: tuple[Path, ...]) -> AgentTurn:
            assert previous_response_id is None
            if 'UNABHÄNGIGE INHALTSKONTROLLE' in prompt:
                assert len(pages) == 1
                return self._turn('not-found-here', '{"present":[],"mismatches":[],"uncertainties":[]}')
            if 'ABSCHLIESSENDE INHALTSKONTROLLE' in prompt:
                self.missing_images = len(pages)
                assert len(pages) == 3, 'Full document must be attached for missing review'
                return self._turn('missing', '{"missing":[],"uncertainties":[]}')
            return self._turn('visual', '{"findings":[],"uncertainties":[]}')

    sessions: list[MissingSession] = []
    def factory(job, bundle, direct, system):  # type: ignore[no-untyped-def]
        session = MissingSession(job)
        sessions.append(session)
        return session

    report = run_job(root, session_factory=factory)
    assert report.status == 'needs_review', report.errors
    assert sessions[0].missing_images == 3
    assert any('weder sicher gefunden' in detail for detail in report.content_uncertainties)
