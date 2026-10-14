"""The ConTeXt instrumented compiler, not Python source heuristics, is the linter."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from context_agent.job import load_job
from context_agent.models import AgentTurn, QualityFinding
from context_agent.quality_rules import QualityContext, load_rules, run_checkers
from context_agent.workflow import run_job
from test_workflow import FakeSession


FINDING = QualityFinding(rule_id='dollar_math', message='compiled dollar math',
                     file='main.tex', line=2, repair_hint='Use \\m or MP \\math')


def test_explicit_dollar_checker_uses_dynamic_context(tmp_path, job_factory):
    root = job_factory(tmp_path)
    p=root/'job.yaml'
    p.write_text(p.read_text().replace('quality: []','quality:\n  - dollar_math'))
    job=load_job(root)
    rules=load_rules(job)
    main=root/'result/main.tex'
    main.write_text(r'\starttext $x$ \stoptext')
    requested=[]
    findings,failures=run_checkers(rules,QualityContext(job,main,None,None,
          remote_lint=lambda name: requested.append(name) or [FINDING]))
    assert not failures and requested==['dollar_math'] and findings==[FINDING]
    empty,failures=run_checkers(rules,QualityContext(job,main,None,None))
    assert not empty and len(failures)==1

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
    lines = [line for line in run.stdout.splitlines()
             if line.startswith('CA-DOLLAR-LINT-REPORT-V1 ')]
    assert len(lines) == 1, run.stdout
    assert json.loads(lines[0].split(' ', 1)[1]) == payload
    assert bool(payload['findings']) is expected
    assert payload['nonce'] == 'test-nonce'
    assert not (tmp_path / '.context-agent-dollar-lint.tex').exists()
