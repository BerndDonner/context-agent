"""Guard against the Messtechnik 0.9.4 quality-group scheduling regression."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from context_agent.models import AgentTurn
from context_agent.workflow import _quality_semantic_findings, run_job
from test_workflow import FakeSession, configure_bad_word_rule


def test_semantic_uncertainties_cannot_become_first_rule_findings():
    source = '\\starttext\n200\\unit{Ohm} und 1{,}5\n\\stoptext\n'
    payload = json.dumps({
        'findings': [
            {'rule_id': 'dollar_math', 'message': 'Das rote k ist unsicher.',
             'certainty': 'confirmed', 'severity': 'error', 'line': 2,
             'evidence': '200\\unit{Ohm}'},
            {'rule_id': 'semantic_numbers', 'message': 'Zahl nicht mit dn gesetzt',
             'certainty': 'confirmed', 'severity': 'error', 'line': 2,
             'evidence': '1{,}5'},
        ],
        'uncertainties': ['Der Originalscan ist unleserlich.'],
    })
    findings, dismissed, uncertainties = _quality_semantic_findings(
        payload, ('dollar_math', 'semantic_numbers'), 0, source,
        dollar_lint_executed=True)
    assert dismissed == set()
    assert [f.rule_id for f in findings] == ['semantic_numbers']
    assert len(uncertainties) == 2
    assert 'Originalscan' in uncertainties[0]
    assert 'dollar_math' in uncertainties[1]


def test_semantic_findings_must_be_anchored_in_the_declared_source_line():
    source = '\\starttext\nDie Spannung ist 1{,}5 V.\n\\stoptext\n'
    response = json.dumps({'findings': [
        {'rule_id': 'semantic_numbers', 'message': 'Unbelegte Zahl',
         'certainty': 'confirmed', 'severity': 'error', 'line': 2,
         'evidence': '9{,}9'},
        {'rule_id': 'semantic_numbers', 'message': 'Fehlende Zeile',
         'certainty': 'confirmed', 'severity': 'error'},
        {'rule_id': 'semantic_numbers', 'message': 'Bestätigte Zahl',
         'certainty': 'confirmed', 'severity': 'error', 'line': 2,
         'evidence': '1{,}5'},
        {'rule_id': 'semantic_numbers', 'message': 'Unklar',
         'certainty': 'warning', 'severity': 'warning', 'line': 2,
         'evidence': '1{,}5'},
    ], 'uncertainties': []})
    findings, _, uncertainties = _quality_semantic_findings(
        response, ('semantic_numbers',), 0, source)
    assert [f.message for f in findings] == ['Bestätigte Zahl']
    assert len(uncertainties) == 3


def _job_with_dollar_and_bad_word(tmp_path, job_factory, *, max_repairs=3):
    root = job_factory(tmp_path, max_turns=18, max_repairs=max_repairs)
    configure_bad_word_rule(root)
    config = yaml.safe_load((root / 'job.yaml').read_text())
    config['quality'] = ['dollar_math', 'bad_word']
    (root / 'job.yaml').write_text(yaml.safe_dump(config), encoding='utf-8')
    return root


def _preflight(job, rules):
    return {'status':'passed', 'conflicts':[], 'uncertainties':[],
            'plan':[['dollar_math'], ['bad_word']]}


def test_clean_first_group_skipped_and_second_group_repaired(tmp_path, job_factory):
    root = _job_with_dollar_and_bad_word(tmp_path, job_factory)
    session_holder = []

    def factory(job, *_):
        session = FakeSession(job)
        session_holder.append(session)
        return session

    report = run_job(root, session_factory=factory, preflight_factory=_preflight)
    assert report.status == 'success', report.errors
    assert report.quality_repairs == 1
    assert 'GOOD' in (root / 'result/main.tex').read_text()
    assert len(session_holder[0].followups) == 1
    assert 'bad_word' in session_holder[0].followups[0]
    assert any(entry['event'] == 'quality_group_satisfied' and
               entry['batch'] == ['dollar_math'] for entry in report.quality_journal)


def test_misclassified_semantic_warning_is_not_a_repair(tmp_path, job_factory):
    root = _job_with_dollar_and_bad_word(tmp_path, job_factory)

    class SemanticWarning(FakeSession):
        def review_text(self, prompt, previous_response_id):
            if 'QUALITÄTSPRÜFUNG' in prompt:
                return self._turn('quality', json.dumps({
                    'findings': [{'rule_id':'dollar_math',
                                  'message':'Rotes k aus dem Scan ist unklar',
                                  'certainty':'warning', 'severity':'warning',
                                  'line':2, 'evidence':'BAD'}],
                    'uncertainties': [],
                }))
            return super().review_text(prompt, previous_response_id)

    report = run_job(root, session_factory=lambda job, *_: SemanticWarning(job),
                     preflight_factory=_preflight)
    assert report.status == 'needs_review'
    assert 'GOOD' in (root / 'result/main.tex').read_text()
    assert report.quality_repairs == 1
    assert report.quality_uncertainties
    assert 'Rotes k' in (root / 'result/uncertainties.md').read_text()
    assert not any(item.get('reason_code') == 'no_effective_change'
                   for item in report.quality_journal)


def test_noop_first_batch_allows_later_batch(tmp_path, job_factory):
    root = _job_with_dollar_and_bad_word(tmp_path, job_factory)
    other = root / 'quality_rules/second_bad'
    other.mkdir(parents=True)
    metadata = {'id':'second_bad', **{key:'Replace BAD.' for key in
               ('description','scope','exceptions','generation','refinement','verification')}}
    (other / 'rule.yaml').write_text(yaml.safe_dump(metadata), encoding='utf-8')
    (other / 'checker.py').write_text('''from context_agent.models import QualityFinding

def check(context):
    if 'BAD' in context.main_tex.read_text(encoding='utf-8'):
        return [QualityFinding(rule_id='second_bad', message='BAD still present', file='main.tex')]
    return []
''', encoding='utf-8')
    config = yaml.safe_load((root/'job.yaml').read_text())
    config['quality'] = ['bad_word', 'second_bad']
    (root/'job.yaml').write_text(yaml.safe_dump(config), encoding='utf-8')

    class NoopThenFix(FakeSession):
        def run_followup(self, prompt, previous_response_id):
            self.followups.append(prompt)
            if 'second_bad' in prompt:
                (self.remote/'main.tex').write_text('\\starttext\nGOOD\n\\stoptext\n')
                self._write_pdf_and_log()
            return self._turn('fix', 'done')

    def plan(job, rules):
        return {'status':'passed','conflicts':[],'uncertainties':[],
                'plan':[['bad_word'], ['second_bad']]}

    sessions = []
    def factory(job, *_):
        session = NoopThenFix(job)
        sessions.append(session)
        return session

    report = run_job(root, session_factory=factory, preflight_factory=plan)
    assert report.status == 'success', report.errors
    assert report.quality_repairs == 2
    assert len(sessions[0].followups) == 2
    assert 'GOOD' in (root/'result/main.tex').read_text()
    assert any(x['event'] == 'quality_group_no_progress' and x['batch'] == ['bad_word']
               for x in report.quality_journal)
    assert any(x['event'] == 'regression_gate_passed' for x in report.quality_journal)


def test_improve_real_number_and_unit_group_after_clean_dollar_math(tmp_path, job_factory):
    """Compiles an improve baseline and accepts both fix types in plan order."""
    from context_agent.quality_rules import check_edits, Edit
    from test_improve import improve_job, ImproveSession

    root = improve_job(tmp_path, job_factory,
                       source='\\starttext\nMessung 1{,}5; Bereich 20V\n\\stoptext\n')
    config = yaml.safe_load((root/'job.yaml').read_text())
    config['quality'] = ['dollar_math', 'semantic_numbers', 'number_with_unit']
    config['limits']['max_agent_turns'] = 25
    config['limits']['max_quality_repairs'] = 4
    (root/'job.yaml').write_text(yaml.safe_dump(config), encoding='utf-8')

    class NumberAndUnitSession(ImproveSession):
        def apply_quality_edits(self, edits, *, max_api_calls):
            before = (self.remote/'main.tex').read_text(encoding='utf-8')
            validated = check_edits(before, [Edit(**entry) for entry in edits])
            (self.remote/'main.tex').write_text(validated, encoding='utf-8')
            self._write_pdf_and_log()
            return self._turn('autofix', 'applied safe edits')

        def run_followup(self, prompt, previous_response_id):
            self.followups.append(prompt)
            if 'number_with_unit' in prompt:
                source = (self.remote/'main.tex').read_text(encoding='utf-8')
                assert '20V' in source
                (self.remote/'main.tex').write_text(
                    source.replace('20V', '20\\unit{Volt}'), encoding='utf-8')
                self._write_pdf_and_log()
            return self._turn('unitfix', 'unit normalized')

    def plan(job, rules):
        return {'status':'passed','conflicts':[],'uncertainties':[],
                'plan':[['dollar_math'],['semantic_numbers','number_with_unit']]}

    report = run_job(root, session_factory=lambda job, *_: NumberAndUnitSession(job),
                     preflight_factory=plan)
    assert report.status == 'success', report.errors
    assert report.quality_repairs == 2
    final = (root/'result/main.tex').read_text()
    assert r'\dn{1.5}' in final and r'20\unit{Volt}' in final
    assert '1{,}5; Bereich 20V' in (root/'input/main.tex').read_text()
    assert any(entry['event'] == 'regression_gate_passed'
               for entry in report.quality_journal)
