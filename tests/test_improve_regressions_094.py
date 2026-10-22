"""Regression evidence from the Messtechnik 0.9.3 Hosted improve failure."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from context_agent.diagnostics import shell_output_events
from context_agent.improvement import improvement_guard
from context_agent.models import QualityFinding
from context_agent.openai_backend import OpenAIHostedSession
from context_agent.runtime_evidence import reconcile_availability_warnings
from context_agent.job import load_job


@pytest.mark.parametrize(('before', 'after'), [
    (r'200Ω', r'200\unit{Ohm}'),
    (r'0,152kΩ', r'\dn{0.152}\unit{kOhm}'),
    (r'0,1Ω', r'\dn{0.1}\unit{Ohm}'),
    (r'7,5V', r'\dn{7.5}\unit{Volt}'),
    (r'110Ω', r'110\unit{Ohm}'),
    (r'150\,\mathrm{V}', r'150\unit{Volt}'),
    (r'100\m{\mu}V', r'100\unit{MicroVolt}'),
    (r'\m{f=\pm 3{,}75\%}', r'\m{f=\pm \dn{3.75}\unit{Percent}}'),
    (r'\m{I=-28{,}4\,\mathrm{mA}}',
     r'\m{I=\dn{-28.4}\unit{MilliAmpere}}'),
])
def test_valid_formatting_keeps_value_and_unit(before: str, after: str) -> None:
    assert improvement_guard(before, after) == []


@pytest.mark.parametrize(('before', 'after'), [
    (r'200Ω', r'200\unit{Volt}'),
    (r'0,152kΩ', r'\dn{0.152}\unit{Ohm}'),
    (r'0,152kΩ', r'\dn{0.125}\unit{kOhm}'),
    (r'\m{-28{,}4\,\mathrm{mA}}', r'\m{\dn{28.4}\unit{MilliAmpere}}'),
    (r'\m{3{,}75\%}', r'\m{\dn{3.75}\unit{Volt}}'),
])
def test_wrong_units_values_and_signs_are_rejected(before: str, after: str) -> None:
    assert improvement_guard(before, after)


def test_multiple_quantities_preserve_repetitions_and_ignore_identifiers():
    before = r'R2 = 200Ω; 200Ω, I1=0,152kΩ; 90 min'
    after = (r'R2 = 200\unit{Ohm}; 200\unit{Ohm}, '
             r'I1=\dn{0.152}\unit{kOhm}; 90\unit{Minute}')
    assert improvement_guard(before, after) == []
    assert improvement_guard(before, after.replace('200\\unit{Ohm}', '200\\unit{Volt}', 1))


def test_real_messtechnik_source_mixed_formatting():
    source = (Path(__file__).parents[1] / 'examples/ca-messtechnik-improve/input/main.tex'
              ).read_text(encoding='utf-8')
    changed = (source.replace('0,152kΩ', r'\dn{0.152}\unit{kOhm}')
              .replace('149,8 Ω', r'\dn{149.8}\unit{Ohm}')
              .replace('200Ω', r'200\unit{Ohm}')
              .replace('7,5V', r'\dn{7.5}\unit{Volt}')
              .replace('110Ω', r'110\unit{Ohm}'))
    assert changed != source
    assert improvement_guard(source, changed) == []
    assert improvement_guard(source, changed.replace(r'\dn{0.152}', r'\dn{0.125}'))


def _finding(message: str, rule: str = 'dollar_math', *, confirmed=False):
    return QualityFinding(rule_id=rule, message=message,
                          certainty='confirmed' if confirmed else 'warning',
                          severity='error' if confirmed else 'warning')


def test_runtime_evidence_replaces_only_proven_stale_availability_warnings(tmp_path):
    (tmp_path / 'mymacros.mp').write_text('beginfig(1); endfig;', encoding='utf-8')
    (tmp_path / 'plotmod.lua').write_text('return {}', encoding='utf-8')
    findings = [
        _finding('Die MetaPost-Datei ../include/mymacros.mp und plotmod.lua liegen nicht vor.'),
        _finding('Ein dynamischer ConTeXt-Dollar-Linter-Befund, ein Satzlauf und '
                 'die Originalvorlage liegen nicht vor.'),
        _finding('Die Lesart von 1,\\ 6 ist unklar.'),
        _finding('Andere fehlende Bilder dürfen nicht verschwinden.', rule='number_with_unit'),
        _finding('mymacros.mp und plotmod fehlen.', confirmed=True),
    ]
    active, reasons = reconcile_availability_warnings(
        findings, pdf_compiled=True, dollar_lint_ok=True,
        includes=tmp_path, references_available=True)
    assert len(active) == 3
    assert len(reasons) == 2
    assert any('1,\\ 6' in f.message for f in active)
    assert any(f.certainty == 'confirmed' for f in active)
    assert any(f.rule_id == 'number_with_unit' for f in active)
    missing_evidence, reasons = reconcile_availability_warnings(
        findings, pdf_compiled=False, dollar_lint_ok=False,
        includes=tmp_path / 'missing', references_available=False)
    assert missing_evidence == findings and reasons == []


def test_shell_metadata_does_not_include_user_commands_or_output():
    secret = 'sk-private-token'
    events = shell_output_events({'output': [
        {'type': 'shell_call', 'call_id': secret, 'status': 'completed',
         'action': {'commands': [f'echo {secret}', 'context main.tex']}},
        {'type': 'shell_call_output', 'call_id': secret, 'status': 'completed',
         'output': [{'stdout': secret, 'stderr': secret}]},
    ]})
    assert len(events) == 5
    assert secret not in json.dumps(events)
    assert events[1]['command_sha256'] != events[2]['command_sha256']
    assert events[-1]['event'] == 'generator_shell_output'
    assert events[-2]['event'] == 'generator_shell_result'


def test_generator_shell_events_durably_written(tmp_path, job_factory):
    job = load_job(job_factory(tmp_path))
    session = object.__new__(OpenAIHostedSession)
    session.job = job
    session.container_id = 'test-container'
    session.system_prompt = 'system'
    session.direct_files = ()
    session._uploaded = []
    response = SimpleNamespace(
        id='resp-test', status='completed', output_text='done', _request_id='req-test',
        model_dump=lambda **_: {'usage': {'total_tokens': 3}, 'output': [
            {'type': 'shell_call', 'call_id': 'call-test', 'status': 'completed',
             'action': {'commands': ['echo private']}}]})
    session._client = SimpleNamespace(responses=SimpleNamespace(create=lambda **_: response))
    session.run_initial('test')
    events = [json.loads(line) for line in
              (job.result_dir / 'execution-events.jsonl').read_text().splitlines()]
    assert any(x['event'] == 'generator_shell_command' for x in events)
    assert 'echo private' not in json.dumps(events)
    assert any(x['event'] == 'agent_api_response' for x in events)
