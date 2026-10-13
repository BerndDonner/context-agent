"""The ConTeXt instrumented compiler, not Python source heuristics, is the linter."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from context_agent.job import load_job
from context_agent.models import AgentTurn, NogoFinding
from context_agent.nogos import NogoContext, load_checkers, run_checkers
from context_agent.workflow import run_job
from test_workflow import FakeSession


FINDING = NogoFinding(rule_id='context-dollar-math', message='compiled dollar math',
                     file='main.tex', line=2, repair_hint='Use \\m or MP \\math')


def test_mandatory_checker_is_regular_plugin_even_with_custom_directory(tmp_path, job_factory):
    root = job_factory(tmp_path, nogo_directory='custom_nogos')
    (root / 'custom_nogos').mkdir()
    job = load_job(root)
    checkers, failures = load_checkers(job.nogo_directory)
    assert not failures
    assert [x.name for x in checkers] == ['dollar_math']
    main = root / 'result/main.tex'
    main.write_text('\\starttext $x$ \\stoptext')
    requested = []
    findings, failures = run_checkers(checkers, NogoContext(
        job, main, None, None, remote_lint=lambda name:
            (requested.append(name) or [FINDING])))
    assert not failures
    assert requested == ['dollar_math']
    assert findings == [FINDING]


def test_missing_shell_is_checker_failure_not_success(tmp_path, job_factory):
    root = job_factory(tmp_path)
    job = load_job(root)
    checkers, failures = load_checkers(job.nogo_directory)
    assert not failures
    main = root / 'result/main.tex'
    main.write_text('\\starttext hi \\stoptext')
    findings, failures = run_checkers(checkers, NogoContext(job, main, None, None))
    assert not findings
    assert len(failures) == 1
    assert failures[0].checker == 'dollar_math'


class DollarSession(FakeSession):
    def run_initial(self, prompt):
        turn = super().run_initial(prompt)
        (self.remote / 'main.tex').write_text('\\starttext\nThe $N$ variable.\n\\stoptext\n')
        return turn

    def run_dollar_lint(self):
        has_dollars = '$' in (self.remote / 'main.tex').read_text()
        findings = [FINDING.as_dict()] if has_dollars else []
        return {'nonce': 'test', 'findings': findings}, AgentTurn(
            response_id='lint', status='completed', output_text='',
            raw={'id': 'lint'}, usage={'input_tokens': 2, 'output_tokens': 1, 'total_tokens': 3})

    def run_followup(self, prompt, previous_response_id):
        assert 'context-dollar-math' in prompt
        self.followups.append(prompt)
        (self.remote / 'main.tex').write_text('\\starttext\nThe \\m{N} variable.\n\\stoptext\n')
        self._write_pdf_and_log()
        return self._turn('repaired', 'repaired')


def test_lint_failure_repairs_without_custom_checkers(tmp_path, job_factory):
    root = job_factory(tmp_path, nogo_directory='custom_nogos', max_turns=5)
    (root / 'custom_nogos').mkdir()
    report = run_job(root, session_factory=lambda job, *_: DollarSession(job))
    assert report.status == 'success', report.errors
    assert report.nogo_repairs == 1
    assert report.agent_turns == 4  # generate, lint, repair, lint
    assert '\\m{N}' in (root / 'result/main.tex').read_text()


def test_lint_failure_exhausted_budget(tmp_path, job_factory):
    root = job_factory(tmp_path, nogo_directory='custom_nogos', max_repairs=0)
    (root / 'custom_nogos').mkdir()
    report = run_job(root, session_factory=lambda job, *_: DollarSession(job))
    assert report.status == 'failed'
    assert report.nogo_repairs == 0
    assert report.findings[0].rule_id == 'context-dollar-math'


@pytest.mark.parametrize(('name','text','expected'), [
    ('inline', r'\\starttext $x$ and \\m{y} \\stoptext', True),
    ('display', r'\\starttext $$x$$ \\stoptext', True),
    ('mp', r'\\starttext\\startMPcode draw textext("$z$"); \\stopMPcode\\stoptext', True),
    ('mp_ok', r'\\starttext\\startMPcode draw textext("\\math{z}"); \\stopMPcode\\stoptext', False),
    ('unexecuted', r'\\starttext \\def\\unused{$x$} okay \\stoptext', False),
    ('verbatim', r'\\starttext\\type{$x$}\\starttyping $z$ \\stoptyping \\stoptext', False),
    ('lua', r'\\starttext\\startluacode local v = "$x$" \\stopluacode\\stoptext', False),
])
def test_real_lmtx_lint(tmp_path, name, text, expected):
    # Accept either an explicit test LMTX runner or the extracted test runtime.
    runner = os.environ.get('CONTEXT_AGENT_TEST_LMTX_RUNNER')
    if not runner:
        candidate = Path('/mnt/data/context-lint-probe/runtime/context-local.sh')
        if candidate.is_file():
            runner = str(candidate)
    if not runner:
        pytest.skip('ConTeXt LMTX runner not installed')
    file = tmp_path / 'main.tex'
    file.write_text(text.replace('\\\\', '\\'), encoding='utf-8')
    report = tmp_path / 'lint.json'
    script = Path(__file__).resolve().parents[1] / 'src/context_agent/resources/runtime/lint-dollar-math.sh'
    env = os.environ.copy()
    env['CONTEXT_AGENT_LINT_RUNNER'] = runner
    run = subprocess.run(['bash', str(script), str(file), str(report), 'test-nonce'],
                         text=True, capture_output=True, env=env)
    assert run.returncode == 0, run.stderr
    payload = json.loads(report.read_text())
    assert bool(payload['findings']) is expected
    assert payload['nonce'] == 'test-nonce'
    assert not (tmp_path / '.context-agent-dollar-lint.tex').exists()
