"""Golden regression of the 89 actual Hosted candidate edits in October 2026."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from context_agent.improvement import improvement_guard, _changed_regions
from context_agent.job import load_job
from context_agent.errors import ConfigurationError
from context_agent.rejected import preserve_rejected
from context_agent.requirements import prompt as requirements_prompt

FIXTURES = Path(__file__).parent / 'fixtures'


def test_all_89_recorded_edits_except_unapproved_ambiguity():
    edits = json.loads((FIXTURES / 'messtechnik_095_edits.json').read_text())
    assert len(edits) == 73
    assert sum(len(v) for v in edits.values()) == 89
    old = (FIXTURES / 'messtechnik_095_before.tex').read_text()
    new = (FIXTURES / 'messtechnik_095_candidate.tex').read_text()
    problems = improvement_guard(old, new)
    assert len(problems) == 1
    assert 'ambiguous:1,6' in problems[0]
    assert 'microvolt' in str(edits['180'])
    assert len(_changed_regions(old, new)) > 50

    approved = [{'before': r'1,\ 6\ \%', 'after': r'\dn{1.6}\unit{Percent}',
                 'source_line': 195, 'reference': 'input/original.pdf', 'page': 2}]
    assert improvement_guard(old, new, approved_resolutions=approved) == []
    # An approval for a different source line cannot authorize the conversion.
    assert improvement_guard(old, new, approved_resolutions=[{**approved[0], 'source_line': 192}])


@pytest.mark.parametrize('before,after', [
    (r'100\m{\mu}V', r'\m{100\unit{microvolt}}'),
    (r'2\mathrm{k}\Omega', r'2\unit{kOhm}'),
    (r'- 0.001 \%', r'-\dn{0.001}\unit{Percent}'),
    (r'200Ω', r'200\unit{Ohm}'),
    (r'0,152kΩ', r'\dn{0.152}\unit{kOhm}'),
])
def test_semantically_equivalent_real_unit_spellings(before, after):
    assert improvement_guard('x='+before, 'x='+after) == []


@pytest.mark.parametrize('tamper', [
    lambda t: t.replace(r'\dn{0.152}', r'\dn{0.125}', 1),
    lambda t: t.replace(r'100\unit{microvolt}', r'100\unit{mV}', 1),
    lambda t: t.replace(r'\dn{1.6}\unit{Percent}', r'\dn{1.6}\unit{Volt}', 1),
    lambda t: t.replace(r'-\dn{0.001}', r'+\dn{0.001}', 1),
])
def test_golden_candidate_still_rejects_true_regressions(tamper):
    old = (FIXTURES / 'messtechnik_095_before.tex').read_text()
    new = (FIXTURES / 'messtechnik_095_candidate.tex').read_text()
    approvals = [{'before': r'1,\ 6\ \%', 'after': r'\dn{1.6}\unit{Percent}', 'source_line': 195}]
    assert improvement_guard(old, tamper(new), approved_resolutions=approvals)


def test_rejected_candidate_is_preserved_with_validation_label(tmp_path):
    result = tmp_path / 'result'
    result.mkdir()
    (result / 'main.tex').write_text('after 0.125', encoding='utf-8')
    (result / 'main.pdf').write_bytes(b'%PDF-diagnostic')
    (result / 'context.log').write_text('compiled', encoding='utf-8')
    (result / 'include-snapshot.tar.gz').write_bytes(b'include')
    baseline = tmp_path / 'accepted.tex'
    baseline.write_text('before 0.152', encoding='utf-8')
    path = preserve_rejected(result, reason_code='numeric_or_unit_inventory_changed',
                             accepted_tex=baseline)
    assert path == 'rejected/0001'
    assert (result / path / 'main.tex').read_text() == 'after 0.125'
    assert 'REJECTED_NOT_VALIDATED' in (result / path / 'metadata.json').read_text()
    assert '0.152' in (result / path / 'candidate.diff').read_text()
    assert preserve_rejected(result, reason_code='another') == 'rejected/0002'


def test_reference_approval_requires_provided_valid_pdf_and_source_line(tmp_path, job_factory):
    import fitz
    root = job_factory(tmp_path)
    (root / 'input/main.tex').write_text('Line one\n1,\\ 6\\ \\%\n', encoding='utf-8')
    pdf = root / 'input/original.pdf'
    document = fitz.open()
    document.new_page()
    document.save(pdf)
    document.close()
    config = root / 'job.yaml'
    config.write_text(config.read_text().replace('mode: create', 'mode: improve\nsource:\n  path: input/main.tex') + '''
references:
  - input/original.pdf
''')
    # job factory already uses references? It does not in these test fixtures.
    text = config.read_text()
    if 'references: []' in text:
        text = text.replace('references: []', '')
    text += '''
'''
    # Add review value through YAML to avoid duplicate review keys.
    import yaml
    data = yaml.safe_load(text)
    data.setdefault('review', {})['reference_resolutions'] = [{
        'before': r'1,\ 6\ \%', 'after': r'\dn{1.6}\unit{Percent}',
        'reference': 'input/original.pdf', 'page': 1, 'source_line': 2,
        'approved': True, 'note': 'Original-PDF auf Seite 1 bestätigt Dezimalzahl'}]
    config.write_text(yaml.safe_dump(data, allow_unicode=True))
    assert load_job(root).config.review.reference_resolutions
    data['review']['reference_resolutions'][0]['page'] = 4
    config.write_text(yaml.safe_dump(data, allow_unicode=True))
    with pytest.raises(ConfigurationError, match='page'):
        load_job(root)


def test_delta_requirements_prompt_omits_unchanged_bulk(tmp_path, job_factory):
    from context_agent.requirements import prompt
    root = job_factory(tmp_path)
    source = root / 'input/main.tex'
    # Very large unchanged sections should not be transmitted redundantly to
    # every page reviewer. The independent task/template/PDF evidence stays.
    source.write_text('\\starttext\n' + 'UNCHANGED-BULK-XYZ\n' * 500 +
                      '1{,}5\\,\\mathrm{V}\n\\stoptext\n')
    config = root / 'job.yaml'
    config.write_text(config.read_text().replace(
        'mode: create', 'mode: improve\nsource:\n  path: input/main.tex'))
    after = root / 'result/main.tex'
    after.write_text(source.read_text().replace('1{,}5\\,\\mathrm{V}',
                                                r'\dn{1.5}\unit{V}'))
    message = prompt(load_job(root), after, pages=1, evidence={
        'pdf_page_count': 1, 'sample_rendered_text_font_runs_by_page': {'1': ['huge']},
    })
    assert 'UNABHÄNGIGE REQUIREMENTS VALIDATION' in message
    assert '1{,}5' in message and r'\dn{1.5}' in message
    assert 'sample_rendered_text_font_runs_by_page' not in message
    assert message.count('UNCHANGED-BULK-XYZ') < 12
    assert len(message) < len(source.read_text())
