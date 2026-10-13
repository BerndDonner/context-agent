from __future__ import annotations

from pathlib import Path

from context_agent.job import load_job
from context_agent.nogos import NogoContext, run_checkers
from context_agent.workflow import run_job
from test_workflow import FakeSession


def inspect(tmp_path: Path, job_factory, source: str):  # type: ignore[no-untyped-def]
    root = job_factory(tmp_path, nogo_directory="custom_nogos")
    (root / "custom_nogos").mkdir()
    main_tex = root / "result/main.tex"
    main_tex.write_text(source, encoding="utf-8")
    job = load_job(root)
    return run_checkers([], NogoContext(job, main_tex, None, None))


def test_detects_real_ctc_math_and_reports_lines(tmp_path: Path, job_factory) -> None:  # type: ignore[no-untyped-def]
    # Use a representative fragment of the uploaded CTC file.
    text = r'''\starttext
The $N$ variable, with $f_{\rm OC0}=f_{\rm clk\_I/O}/2$.
\stoptext
'''
    findings, failures = inspect(tmp_path, job_factory, text)
    assert not failures
    assert len(findings) == 2
    assert {f.rule_id for f in findings} == {"context-dollar-math"}
    assert all(f.line == 2 for f in findings)
    assert all('\\m{' in (f.repair_hint or '') for f in findings)


def test_comments_literals_and_code_are_ignored(tmp_path: Path, job_factory) -> None:  # type: ignore[no-untyped-def]
    text = r'''\starttext
% $comment$
\starttyping
$code$ and $$code$$
\stoptyping
\type{$literal$} \typ[option]{$another$}
\startMPcode
label("$not_conTexT_math$", origin);
\stopMPcode
\startluacode
local price = "$5"
\stopluacode
A price of \$5, and literal \% $comment is not commented but math$.
Correct inline \m{N} and \startformula N=5 \stopformula.
\stoptext
'''
    findings, failures = inspect(tmp_path, job_factory, text)
    assert not failures
    assert len(findings) == 1
    assert findings[0].line == 13


def test_display_dollars_and_unclosed_are_rejected(tmp_path: Path, job_factory) -> None:  # type: ignore[no-untyped-def]
    findings, failures = inspect(tmp_path, job_factory, '$$a+b$$ and $unfinished')
    assert not failures
    assert len(findings) == 2
    assert all(f.rule_id == 'context-dollar-math' for f in findings)


class DollarSession(FakeSession):
    def run_initial(self, prompt: str):
        turn = super().run_initial(prompt)
        (self.remote / 'main.tex').write_text('\\starttext\nThe $N$ variable.\n\\stoptext\n')
        return turn

    def run_followup(self, prompt: str, previous_response_id: str):
        assert 'context-dollar-math' in prompt
        self.followups.append(prompt)
        (self.remote / 'main.tex').write_text('\\starttext\nThe \\m{N} variable.\n\\stoptext\n')
        self._write_pdf_and_log()
        return self._turn('repaired', 'repaired')


def test_builtin_nogo_triggers_repair_without_custom_checkers(tmp_path: Path, job_factory) -> None:  # type: ignore[no-untyped-def]
    root = job_factory(tmp_path, nogo_directory='custom_nogos')
    (root / 'custom_nogos').mkdir()
    sessions: list[DollarSession] = []

    def factory(job, bundle, direct, system):  # type: ignore[no-untyped-def]
        assert "\\m{...}" in system
        sessions.append(DollarSession(job))
        return sessions[-1]

    report = run_job(root, session_factory=factory)
    assert report.status == 'success', report.errors
    assert report.nogo_repairs == 1
    assert report.agent_turns == 2
    assert not report.findings
    assert '\\m{N}' in (root / 'result/main.tex').read_text()
    assert sessions[0].followups


def test_builtin_nogo_exhausted_repair_budget_fails(tmp_path: Path, job_factory) -> None:  # type: ignore[no-untyped-def]
    root = job_factory(tmp_path, nogo_directory='custom_nogos', max_repairs=0)
    (root / 'custom_nogos').mkdir()

    def factory(job, bundle, direct, system):  # type: ignore[no-untyped-def]
        return DollarSession(job)

    report = run_job(root, session_factory=factory)
    assert report.status == 'failed'
    assert report.nogo_repairs == 0
    assert report.findings[0].rule_id == 'context-dollar-math'
