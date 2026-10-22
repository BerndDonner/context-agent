"""Regressions from the 87 actually attempted Messtechnik unit edits (0.9.7)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from context_agent.improvement import (guarded_source_replacement,
                                       improvement_guard, isolate_safe_changes)
from context_agent.quality_rules import Edit, check_edits
from context_agent.requirements import prompt as requirements_prompt
from context_agent.job import load_job
from context_agent.workflow import run_job
from test_improve import ImproveSession, improve_job
from test_workflow import configure_bad_word_rule

FIXTURES = Path(__file__).parent / 'fixtures'


def test_87_real_edits_are_partially_accepted_without_authorizing_ocr():
    edits = json.loads((FIXTURES / 'messtechnik_097_edits.json').read_text())
    assert len(edits) == 71
    assert sum(map(len, edits.values())) == 87
    accepted = (FIXTURES / 'messtechnik_097_accepted.tex').read_text()
    candidate = (FIXTURES / 'messtechnik_097_candidate.tex').read_text()
    original = (Path(__file__).parents[1] / 'examples/ca-messtechnik-improve/input/main.tex').read_text()
    problems = improvement_guard(original, candidate)
    assert len(problems) == 1 and 'ambiguous:1,6' in problems[0]
    partial = isolate_safe_changes(original, accepted, candidate)
    assert partial.included_regions == 70
    assert partial.excluded_regions == 1
    assert improvement_guard(original, partial.source) == []
    assert r'1,\ 6\ \%' in partial.source
    assert r'2\unit{kiloohm}' in partial.source
    assert r'\dn{5.6}\unit{kiloohm}' in partial.source
    assert r'\dn{1.6}\unit{Percent}' in partial.source  # unambiguous other use
    assert partial.source != candidate
    assert partial.source != accepted
    replacements = guarded_source_replacement(candidate, partial.source)
    assert check_edits(candidate, [Edit(**entry) for entry in replacements]) == partial.source
    assert improvement_guard(original, partial.source.replace('110\\unit{Ohm}', '120\\unit{Ohm}'))


@pytest.mark.parametrize('unit', ['kOhm', 'KiloOhm', 'Kiloohm', 'kiloohm'])
def test_kiloohm_spellings_are_aliases_not_new_units(unit):
    assert improvement_guard(r'2\mathrm{k}\Omega', rf'2\unit{{{unit}}}') == []
    assert improvement_guard(r'2\mathrm{k}\Omega', r'2\unit{Ohm}')


def test_independent_source_edits_keep_safe_neighbor_and_reject_value_and_sign():
    baseline = '\\starttext\n20V und 2kΩ\n-0,152Ω\n\\stoptext\n'
    candidate = '\\starttext\n20\\unit{V} und 2\\unit{kOhm}\n+0,152\\unit{Ohm}\n\\stoptext\n'
    saved = isolate_safe_changes(baseline, baseline, candidate)
    assert (saved.included_regions, saved.excluded_regions) == (1, 1)
    assert '20\\unit{V} und 2\\unit{kOhm}' in saved.source
    assert '-0,152Ω' in saved.source
    assert improvement_guard(baseline, saved.source) == []


def test_requirements_prompt_scopes_page_batches_without_false_missing_pages(tmp_path, job_factory):
    root = improve_job(tmp_path, job_factory)
    job = load_job(root)
    output = root / 'result/main.tex'
    output.parent.mkdir(exist_ok=True)
    output.write_text((root / 'input/main.tex').read_text().replace('1{,}5', r'\dn{1.5}'))
    message = requirements_prompt(job, output, pages=8, batch_start=3, batch_end=4,
                                  evidence={'embedded_pdf_font_names_by_page':
                                            {'1': ['A'], '3': ['B'], '4': ['C'], '8': ['D']}})
    assert 'Ausschließlich PDF-Ausgabeseiten 3 bis 4' in message
    assert 'Andere Seiten werden in eigenen unabhängigen Batches geprüft' in message
    assert '"3": ["B"]' in message and '"8": ["D"]' not in message
    with pytest.raises(ValueError):
        requirements_prompt(job, output, pages=8, batch_start=7, batch_end=9)


def test_workflow_salvages_only_safe_line_then_performs_normal_reviews(tmp_path, job_factory):
    root = improve_job(tmp_path, job_factory,
                       source='\\starttext\nBAD 20V\nMesswert 0,152Ω\n\\stoptext\n')
    configure_bad_word_rule(root)
    config = yaml.safe_load((root / 'job.yaml').read_text())
    config['limits']['max_agent_turns'] = 32
    (root / 'job.yaml').write_text(yaml.safe_dump(config))

    class SalvageSession(ImproveSession):
        partial_calls = 0

        def run_followup(self, prompt, previous_response_id):
            self.followups.append(prompt)
            if 'bad_word' in prompt:
                before = (self.remote / 'main.tex').read_text()
                after = before.replace('BAD 20V', r'GOOD 20\unit{V}')
                after = after.replace('0,152Ω', '0,125Ω')  # Deliberate regression.
                (self.remote / 'main.tex').write_text(after)
                self._write_pdf_and_log()
            return self._turn('repair', 'combined edits')

        def apply_quality_edits(self, edits, *, max_api_calls):
            self.partial_calls += 1
            before = (self.remote / 'main.tex').read_text()
            after = check_edits(before, [Edit(**item) for item in edits])
            (self.remote / 'main.tex').write_text(after)
            self._write_pdf_and_log()
            return self._turn('partial', 'safe subset applied')

    sessions = []
    def factory(job, *_):
        session = SalvageSession(job)
        sessions.append(session)
        return session

    report = run_job(root, session_factory=factory)
    assert report.status == 'success', report.errors
    assert sessions[0].partial_calls == 1
    result = (root / 'result/main.tex').read_text()
    assert r'GOOD 20\unit{V}' in result
    assert '0,152Ω' in result
    assert '0,125Ω' not in result
    assert (root / 'result/rejected/0001/main.tex').is_file()
    assert any(event['event'] == 'quality_partial_candidate_compiled'
               for event in report.quality_journal)
    assert any(check['status'] == 'passed' for check in report.requirements_checks)


def test_canonical_unit_checker_and_autofix(tmp_path, job_factory):
    from context_agent.quality_rules import QualityContext, load_rules, run_checkers
    root = job_factory(tmp_path)
    config = yaml.safe_load((root / 'job.yaml').read_text())
    config['quality'] = ['number_with_unit']
    (root / 'job.yaml').write_text(yaml.safe_dump(config))
    source = root / 'result/main.tex'
    source.parent.mkdir(exist_ok=True)
    source.write_text('\\starttext\n2\\unit{kiloohm}\n\\stoptext\n')
    job = load_job(root)
    rules = load_rules(job)
    context = QualityContext(job, source, None, None)
    findings, failures = run_checkers(rules, context)
    assert not failures
    assert len(findings) == 1
    edits = rules[0].propose_edits(context, findings)
    assert len(edits) == 1
    assert r'2\unit{kOhm}' in check_edits(source.read_text(), edits)
