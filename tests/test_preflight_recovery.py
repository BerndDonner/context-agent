"""Regression tests for unpredictable LLM preflight plan output."""
import json
from types import SimpleNamespace

import pytest

from context_agent.errors import ContextAgentError
from context_agent.job import load_job
from context_agent.quality_preflight import llm_preflight, parse_preflight
from context_agent.quality_rules import load_rules
from context_agent.workflow import run_job

IDS = ('dollar_math', 'semantic_numbers', 'number_with_unit')


def make_payload(plan, *, status='passed', conflicts=None):
    return json.dumps({'status': status, 'conflicts': conflicts if conflicts is not None else [],
                       'uncertainties': [], 'plan': plan})


@pytest.mark.parametrize('bad_plan,reason', [
    (None, 'invalid_plan_shape'),
    ({'batches': [['dollar_math']]}, 'invalid_plan_shape'),
    ([[]], 'invalid_plan_shape'),
    (['dollar_math'], 'invalid_plan_shape'),
    ([['dollar_math']], 'invalid_plan_coverage'),
    ([['dollar_math','semantic_numbers','semantic_numbers','number_with_unit']],
     'invalid_plan_coverage'),
    ([['dollar_math','semantic_numbers','number_with_unit','invented']],
     'invalid_plan_coverage'),
])
def test_invalid_plan_falls_back_without_changing_explicit_selection(bad_plan, reason):
    result = parse_preflight(make_payload(bad_plan), IDS)
    assert result['plan'] == [[rule_id] for rule_id in IDS]
    assert result['plan_fallback_reason'] == reason
    assert [r for batch in result['plan'] for r in batch] == list(IDS)


def test_valid_plan_is_preserved():
    proposed = [['semantic_numbers','number_with_unit'],['dollar_math']]
    result = parse_preflight(make_payload(proposed), IDS)
    assert result['plan'] == proposed
    assert 'plan_fallback_reason' not in result


def test_true_blocking_conflict_is_never_bypassed():
    conflict = {'rules': ['semantic_numbers'], 'reason': 'incompatible',
                'relevance': 'blocking'}
    with pytest.raises(ContextAgentError, match='blocking conflict'):
        parse_preflight(make_payload(None, status='passed', conflicts=[conflict]), IDS)
    blocked = parse_preflight(make_payload(None, status='blocked', conflicts=[conflict]), IDS)
    assert blocked['status'] == 'blocked'
    with pytest.raises(ContextAgentError, match='preflight status'):
        parse_preflight(make_payload(None,status='unknown'),IDS)


def test_failing_preflight_keeps_previous_result_and_durable_diagnostics(tmp_path, job_factory):
    root = job_factory(tmp_path)
    old = root / 'result' / 'main.tex'
    old.write_text('valuable existing output')

    def bad_preflight(job, rules):
        raise ContextAgentError('consistency preflight did not return JSON')

    with pytest.raises(ContextAgentError, match='diagnostics:'):
        run_job(root, preflight_factory=bad_preflight,
                session_factory=lambda *args: (_ for _ in ()).throw(AssertionError('no session')))
    assert old.read_text() == 'valuable existing output'
    events_path = root / '.context-agent' / 'preflight-events.jsonl'
    events = [json.loads(line) for line in events_path.read_text().splitlines()]
    assert [e['event'] for e in events] == ['preflight_started', 'preflight_failed']
    assert all('valuable existing output' not in str(event) for event in events)


def test_llm_preflight_logs_shape_without_response_body(monkeypatch, tmp_path, job_factory):
    root = job_factory(tmp_path)
    job = load_job(root)
    rules = load_rules(job)
    secret = 'private-student-source-NOT-IN-DIAGNOSTICS'
    payload = make_payload({'batches': [secret]})

    class FakeFiles:
        def create(self, **kwargs):
            return SimpleNamespace(id='file-1')
        def delete(self, id):
            pass

    class FakeResponses:
        def create(self, **kwargs):
            return SimpleNamespace(output_text=payload,
                model_dump=lambda mode: {'id': 'resp-test', 'status': 'completed',
                                         'usage': {'total_tokens': 90}})

    client = SimpleNamespace(files=FakeFiles(), responses=FakeResponses())
    from context_agent.openai_backend import OpenAIHostedSession
    monkeypatch.setattr(OpenAIHostedSession, '_create_client', staticmethod(lambda timeout: client))
    answer = llm_preflight(job, rules)
    assert answer['plan'] == []
    assert answer['plan_fallback_reason'] == 'invalid_plan_shape'
    events = (root / '.context-agent' / 'preflight-events.jsonl').read_text()
    assert 'resp-test' in events
    assert 'invalid_plan_shape' not in events  # runner adds the fallback event
    assert secret not in events
    assert 'output_sha256' in events
    assert 'plan_type' in events
