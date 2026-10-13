from __future__ import annotations

import pytest

from context_agent.content_audit import (
    InventoryEntry, parse_inventory, parse_missing, parse_output_check,
)
from context_agent.errors import ArtifactError


def test_inventory_and_matching_are_source_scoped() -> None:
    entries, uncertainties = parse_inventory(
        '{"entries":[{"source_page":2,"kind":"solution",'
        '"anchor":"Aufgabe 4","detail":"Lösung: 42"}],"uncertainties":[]}',
        source='input/scan.pdf', start=1, end=3, id_prefix='s1p1',
    )
    assert entries[0].id == 's1p1-1'
    assert entries[0].source_page == 2
    assert entries[0].detail == 'Lösung: 42'
    assert not uncertainties
    check = parse_output_check(
        '{"present":["s1p1-1"],"mismatches":[],"uncertainties":[]}',
        entries=entries, start=1, end=2,
    )
    assert check.present == frozenset({'s1p1-1'})
    assert not check.findings


def test_unconfirmed_missing_is_uncertainty_not_success() -> None:
    entries = [InventoryEntry('s1p1-1', 'input/scan.pdf', 1, 'task', 'Aufgabe 1', '12 V')]
    found, unresolved = parse_missing('{"missing":[],"uncertainties":[]}', entries)
    assert not found
    assert 'weder sicher gefunden' in unresolved[0]
    found, unresolved = parse_missing(
        '{"missing":[{"id":"s1p1-1","message":"Aufgabe fehlt",'
        '"confidence":0.93}],"uncertainties":[]}', entries,
    )
    assert len(found) == 1
    assert found[0].rule_id == 'content-missing'
    assert not unresolved


def test_low_confidence_mismatch_becomes_uncertainty() -> None:
    entries = [InventoryEntry('s1p1-1', 'input/scan.pdf', 1, 'value', 'Messwert', '5 V')]
    check = parse_output_check(
        '{"present":[],"mismatches":[{"id":"s1p1-1","output_page":1,'
        '"message":"vielleicht 6 V","confidence":0.61}],"uncertainties":[]}',
        entries=entries, start=1, end=1,
    )
    assert not check.findings
    assert check.affected == frozenset({'s1p1-1'})
    assert 'vielleicht 6 V' in check.uncertainties[0]


@pytest.mark.parametrize('text', [
    'not json',
    '{"entries":[{"source_page":4,"kind":"task","anchor":"a","detail":"b"}],"uncertainties":[]}',
    '{"entries":[{"source_page":1,"kind":"task","anchor":"a","detail":"b"}],"uncertainties":null}',
])
def test_bad_inventory_fails_closed(text: str) -> None:
    with pytest.raises(ArtifactError):
        parse_inventory(text, source='scan.pdf', start=1, end=1, id_prefix='s1p1')


def test_usage_tracks_cached_tokens_and_shell_calls() -> None:
    from datetime import UTC, datetime

    from context_agent.models import RunReport

    report = RunReport('running', 'test-model', datetime.now(UTC))
    report.add_usage(
        {'input_tokens': 100, 'output_tokens': 20, 'total_tokens': 120,
         'input_tokens_details': {'cached_tokens': 30, 'cache_write_tokens': 50},
         'output_tokens_details': {'reasoning_tokens': 15}},
        phase='initial',
        raw={'output': [
            {'type': 'shell_call', 'action': {'commands': ['pwd', 'ls']}},
            {'type': 'shell_call_output'},
            {'type': 'message'},
        ]},
    )
    assert report.shell_calls == 1
    assert report.shell_commands == 2
    assert report.usage['total_tokens'] == 120
    assert report.usage_by_phase[0] == {
        'phase': 'initial',
        'input_tokens': 100,
        'cached_input_tokens': 30,
        'cache_write_input_tokens': 50,
        'output_tokens': 20,
        'reasoning_output_tokens': 15,
        'shell_calls': 1,
        'shell_commands': 2,
    }
