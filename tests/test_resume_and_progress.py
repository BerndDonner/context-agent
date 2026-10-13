from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pytest

from context_agent.checkpoint import read_checkpoint
from context_agent.errors import ContextAgentError
from context_agent.job import load_job
from context_agent.models import AgentTurn
from context_agent.scan_markers import visible_scan_markers
from context_agent.workflow import run_job
from test_workflow import FakeSession, ReviewSession, configure_reproduction_source


def _reproduce_job(root: Path, *, content: int = 0, visual: int = 0) -> None:
    configure_reproduction_source(root)
    with (root / 'job.yaml').open('a', encoding='utf-8') as stream:
        stream.write(f'\nreview:\n  reproduction: true\n'
                     f'  max_content_repairs: {content}\n'
                     f'  max_visual_repairs: {visual}\n')


def test_independent_content_and_visual_repair_budgets(tmp_path: Path, job_factory):
    root = job_factory(tmp_path, max_turns=16)
    _reproduce_job(root, content=1, visual=1)

    class BothRepairs(ReviewSession):
        def __init__(self, job):
            super().__init__(job)
            self.content_calls = 0
            self.visual_calls = 0

        def review_pages(self, prompt, previous_response_id, pages):
            if 'UNABHÄNGIGE INHALTSKONTROLLE' in prompt:
                self.content_calls += 1
                if self.content_calls == 1:
                    return self._turn('bad-content', '{"present":[],"mismatches":['
                                      '{"id":"s1p1-1","output_page":1,"message":"bad value",'
                                      '"confidence":0.99}],"uncertainties":[]}')
                return self._turn('good-content', '{"present":["s1p1-1"],'
                                  '"mismatches":[],"uncertainties":[]}')
            self.visual_calls += 1
            if self.visual_calls == 1:
                return self._turn('bad-visual', '{"findings":[{"type":"visual",'
                                  '"output_page":1,"source_page":1,'
                                  '"message":"missing line","confidence":0.98}],'
                                  '"uncertainties":[]}')
            return self._turn('good-visual', '{"findings":[],"uncertainties":[]}')

        def run_followup(self, prompt, previous_response_id):
            self.followups.append(prompt)
            self._write_pdf_and_log()
            return self._turn('repair-' + str(len(self.followups)), 'repaired')

    report = run_job(root, session_factory=lambda job, bundle, direct, system: BothRepairs(job))
    assert report.status == 'success', report.errors
    assert (report.content_repairs, report.visual_repairs, report.review_repairs) == (1, 1, 2)
    assert (root / 'result/checkpoint.json').is_file()


def test_resume_uses_saved_files_in_new_container_and_archives_old_result(
    tmp_path: Path, job_factory,
):
    root = job_factory(tmp_path, max_turns=14)
    _reproduce_job(root, visual=1)
    original = run_job(root, session_factory=lambda job, bundle, direct, system:
                       ReviewSession(job, always_fail=True))
    assert original.status == 'failed'
    baseline = (root / 'result/main.tex').read_bytes()
    checkpoint = json.loads((root / 'result/checkpoint.json').read_text())
    assert checkpoint['phase'] == 'finished-failed'

    class Resumed(ReviewSession):
        def __init__(self, job):
            super().__init__(job)
            self.repaired = False

        def run_initial(self, prompt):
            assert 'GESPEICHERTEN ConTeXt-JOB' in prompt
            self.repaired = True
            (self.remote / 'main.tex').write_text('RESTORED-AND-FIXED', encoding='utf-8')
            self._write_pdf_and_log()
            return self._turn('fresh-generation-chain', 'targeted repair')

        def review_pages(self, prompt, previous_response_id, pages):
            assert previous_response_id is None
            if 'UNABHÄNGIGE INHALTSKONTROLLE' in prompt:
                return self._turn('review-content', '{"present":["s1p1-1"],'
                                  '"mismatches":[],"uncertainties":[]}')
            if not self.repaired:
                return self._turn('visual-bad', '{"findings":[{"type":"visual",'
                                  '"output_page":1,"source_page":1,'
                                  '"message":"missing line","confidence":0.99}],'
                                  '"uncertainties":[]}')
            return self._turn('visual-good', '{"findings":[],"uncertainties":[]}')

    def factory(job, bundle, direct, system):
        with tarfile.open(bundle, 'r:gz') as archive:
            files = set(archive.getnames())
            assert 'job/result/main.tex' in files
            assert 'job/result/checkpoint.json' in files
            saved = archive.extractfile('job/result/main.tex')
            assert saved is not None and saved.read() == baseline
        return Resumed(job)

    report = run_job(root, resume=True, session_factory=factory)
    assert report.status == 'success', report.errors
    assert (root / 'result/main.tex').read_text() == 'RESTORED-AND-FIXED'
    history = list((root / '.run-history').glob('*-previous'))
    assert len(history) == 1
    assert (history[0] / 'main.tex').read_bytes() == baseline
    assert not (root / '.resume-work').exists()
    assert '/result/main.tex' in report.artifacts['main.tex']


def test_failed_resume_preserves_previous_result_and_staged_work(tmp_path: Path, job_factory):
    root = job_factory(tmp_path, max_turns=12)
    _reproduce_job(root, visual=0)
    run_job(root, session_factory=lambda job, bundle, direct, system:
            ReviewSession(job, always_fail=True))
    previous = (root / 'result/main.tex').read_bytes()
    result = run_job(root, resume=True, session_factory=lambda job, bundle, direct, system:
                     ReviewSession(job, always_fail=True))
    assert result.status == 'failed'
    assert (root / 'result/main.tex').read_bytes() == previous
    assert (root / '.resume-work/checkpoint.json').exists()


def test_resume_rejects_old_runs_and_input_modifications(tmp_path: Path, job_factory):
    root = job_factory(tmp_path)
    with pytest.raises(ContextAgentError, match='old runs'):
        run_job(root, resume=True, session_factory=lambda *args: None)
    # Produce a failed checkpoint, not a finished-success one.
    root_config = root / 'job.yaml'
    root_config.write_text(root_config.read_text().replace('max_agent_turns: 6',
                                                           'max_agent_turns: 1'))
    run_job(root, session_factory=lambda job, bundle, direct, system:
            FakeSession(job, missing_first=True))
    (root / 'task.md').write_text('Modified task', encoding='utf-8')
    with pytest.raises(ContextAgentError, match='changed'):
        run_job(root, resume=True, session_factory=lambda *args: None)


def test_scan_markers_only_flag_visible_placeholders(tmp_path: Path):
    file = tmp_path / 'main.tex'
    file.write_text(r'''\starttext
% [Scan unklar: 13b, original hidden]
\m{R = +5,02\Omega}
[Scan unklar: Vorzeichen] 5,02
[Index unklar]
\starttyping
[Scan unklar: literal example]
\stoptyping
\stoptext
''', encoding='utf-8')
    findings = visible_scan_markers(file)
    assert [f.line for f in findings] == [4, 5]


def test_progress_and_uncertainties_file(tmp_path: Path, job_factory, capsys):
    root = job_factory(tmp_path, max_turns=12)
    _reproduce_job(root)

    class Uncertain(ReviewSession):
        def review_text(self, prompt, previous_response_id):
            if 'ERSTELLE NUR EIN INHALTSINVENTAR' in prompt:
                return self._turn('source', '{"entries":[{"source_page":1,"kind":"text",'
                                  '"anchor":"a","detail":"b"}],'
                                  '"uncertainties":["scan ambiguous"]}')
            return super().review_text(prompt, previous_response_id)

        def review_pages(self, prompt, previous_response_id, pages):
            if 'UNABHÄNGIGE INHALTSKONTROLLE' in prompt:
                return self._turn('content', '{"present":["s1p1-1"],'
                                  '"mismatches":[],"uncertainties":[]}')
            return self._turn('visual', '{"findings":[],"uncertainties":[]}')

    report = run_job(root, session_factory=lambda job, bundle, direct, system: Uncertain(job))
    assert report.status == 'needs_review'
    assert 'scan ambiguous' in (root / 'result/uncertainties.md').read_text()
    stderr = capsys.readouterr().err
    assert 'Quelleninventar' in stderr and 'Sichtprüfung' in stderr
