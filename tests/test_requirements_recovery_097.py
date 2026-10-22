"""Real malformed requirements-review response from the Messtechnik 0.9.6 run."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from context_agent.openai_backend import OpenAIHostedSession, UploadedFile
from context_agent.requirements import (REQUIREMENTS_RESPONSE_FORMAT,
    RequirementsReviewSchemaError, parse_result)
from context_agent.workflow import run_job
from test_improve import ImproveSession, improve_job
from test_workflow import FakeSession, configure_bad_word_rule


MALFORMED_HOSTED = json.dumps({
    'status': 'passed',
    'findings': [
        'Die Änderungen ersetzen Dezimaldarstellungen durch \\dn{...}.',
        'Auf Ausgabeseiten 1-2 ist keine Inhaltsabweichung erkennbar.',
    ],
    'uncertainties': ['Für die Ergebnisseiten 3-8 liegen keine Seitenbilder vor.'],
    'regressions': [],
}, ensure_ascii=False)


def test_actual_malformed_hosted_result_is_schema_error():
    with pytest.raises(RequirementsReviewSchemaError) as exc:
        parse_result(MALFORMED_HOSTED)
    assert exc.value.code == 'invalid_finding'
    with pytest.raises(RequirementsReviewSchemaError, match='passed_with_open_issues'):
        parse_result('{"status":"passed","findings":[],"uncertainties":["pages missing"],"regressions":[]}')
    assert parse_result('{"status":"uncertain","findings":[],"uncertainties":["pages missing"],"regressions":[]}').status == 'uncertain'


def test_schema_is_strict_and_consistent():
    schema = REQUIREMENTS_RESPONSE_FORMAT['schema']
    assert REQUIREMENTS_RESPONSE_FORMAT['strict'] is True
    assert schema['additionalProperties'] is False
    assert set(schema['required']) == set(schema['properties'])
    for key in ('findings', 'regressions'):
        item = schema['properties'][key]['items']
        assert item['additionalProperties'] is False
        assert set(item['required']) == set(item['properties'])


def test_review_retries_once_with_same_pages_and_succeeds(tmp_path: Path, job_factory):
    root = job_factory(tmp_path, max_turns=5)
    seen = []

    class Retrying(FakeSession):
        def review_pages(self, prompt, previous_response_id, pages):
            seen.append((prompt, tuple(pages), previous_response_id))
            if len(seen) == 1:
                return self._turn('bad-schema', MALFORMED_HOSTED)
            return self._turn('good-schema',
                '{"status":"passed","findings":[],"uncertainties":[],"regressions":[]}')

    result = run_job(root, session_factory=lambda job, *_: Retrying(job))
    assert result.status == 'success', result.errors
    assert len(seen) == 2
    assert seen[0][1] == seen[1][1]
    assert seen[0][2] is None and seen[1][2] is None
    assert 'SCHEMA-KORREKTURVERSUCH' in seen[1][0]
    assert result.agent_turns == 3
    assert (root / 'result/.validated/validation.json').is_file()
    events = [json.loads(line) for line in (root / 'result/execution-events.jsonl').read_text().splitlines()]
    assert any(x['event'] == 'requirements_review_schema_invalid' and
               x['response_id'] == 'bad-schema' and x['review_error_code'] == 'invalid_finding'
               for x in events)
    assert any(x['event'] == 'requirements_review_batch_valid' and
               x['review_attempt'] == 2 for x in events)
    assert not any('Die Änderungen ersetzen' in json.dumps(x) for x in events)


def test_two_bad_replies_do_not_make_create_failed_or_validated(tmp_path: Path, job_factory):
    root = job_factory(tmp_path, max_turns=8)
    calls = []

    class AlwaysInvalid(FakeSession):
        def review_pages(self, prompt, previous_response_id, pages):
            calls.append(tuple(pages))
            return self._turn('invalid-' + str(len(calls)), MALFORMED_HOSTED)

    result = run_job(root, session_factory=lambda job, *_: AlwaysInvalid(job))
    assert result.status == 'needs_review', result.errors
    assert len(calls) == 2
    assert result.agent_turns == 3
    assert not (root / 'result/.validated/validation.json').is_file()
    assert (root / 'result/rejected/0001/main.tex').exists()
    assert 'REJECTED_NOT_VALIDATED' in (root / 'result/rejected/0001/metadata.json').read_text()
    assert result.requirements_checks[-1]['status'] == 'uncertain'
    assert result.content_uncertainties
    events = [json.loads(line) for line in (root / 'result/execution-events.jsonl').read_text().splitlines()]
    assert any(x['event'] == 'requirements_review_unusable' for x in events)
    assert any(x['event'] == 'regression_rollback' and
               x['reason_code'] == 'requirements_review_invalid_schema' for x in events)


def test_improve_restores_baseline_and_preserves_rejected_candidate(tmp_path: Path, job_factory):
    root = improve_job(tmp_path, job_factory)
    configure_bad_word_rule(root)
    class AlwaysInvalid(ImproveSession):
        def review_pages(self, prompt, previous_response_id, pages):
            return self._turn('invalid-review', MALFORMED_HOSTED)
    result = run_job(root, session_factory=lambda job, *_: AlwaysInvalid(job))
    assert result.status == 'needs_review', result.errors
    assert 'BAD' in (root / 'result/main.tex').read_text()
    assert 'GOOD' in (root / 'result/rejected/0001/main.tex').read_text()
    assert 'GOOD' in (root / 'result/rejected/0001/candidate.diff').read_text()
    # The protected snapshot can contain the compile-only baseline; it must
    # not contain the unvalidated GOOD candidate.
    assert (root / 'result/.protected/main.tex').read_text() == (root / 'input/main.tex').read_text()
    assert 'GOOD' not in (root / 'result/changes.diff').read_text()
    assert result.agent_turns <= 15


def test_turn_limit_prevents_retry_and_returns_needs_review(tmp_path: Path, job_factory):
    root = job_factory(tmp_path, max_turns=2)
    calls = []
    class Invalid(FakeSession):
        def review_pages(self, prompt, previous_response_id, pages):
            calls.append(prompt)
            return self._turn('bad', MALFORMED_HOSTED)
    result = run_job(root, session_factory=lambda job, *_: Invalid(job))
    assert result.status == 'needs_review', result.errors
    assert len(calls) == 1
    assert result.agent_turns == 2


def test_incomplete_response_is_not_accepted_even_with_valid_json(tmp_path: Path, job_factory):
    root = job_factory(tmp_path, max_turns=4)
    count = 0
    class Incomplete(FakeSession):
        def review_pages(self, prompt, previous_response_id, pages):
            nonlocal count
            count += 1
            valid_json = '{"status":"passed","findings":[],"uncertainties":[],"regressions":[]}'
            turn = self._turn('response-' + str(count), valid_json)
            return replace(turn, status='incomplete' if count == 1 else 'completed')
    report = run_job(root, session_factory=lambda job, *_: Incomplete(job))
    assert report.status == 'success'
    assert count == 2
    events = [json.loads(line) for line in (root / 'result/execution-events.jsonl').read_text().splitlines()]
    assert any(e.get('review_error_code') == 'response_not_completed' for e in events)


def test_hosted_requirements_calls_request_structured_output(tmp_path: Path, job_factory):
    from context_agent.job import load_job
    from test_openai_backend import FakeClient
    root = job_factory(tmp_path)
    session = object.__new__(OpenAIHostedSession)
    session.job = load_job(root)
    session.direct_files = ()
    session.system_prompt = 'system'
    session.container_id = 'container-1'
    session._uploaded = []
    session._client = FakeClient()
    session._upload = lambda path: UploadedFile(path, 'output-image')
    page = tmp_path / 'page.png'
    page.write_bytes(b'png')
    session.review_pages('UNABHÄNGIGE REQUIREMENTS VALIDATION – IMPROVE-REGRESSIONS-AUDIT',
                         None, (page,))
    kwargs = session._client.responses.calls[-1]
    assert kwargs['text']['format'] == REQUIREMENTS_RESPONSE_FORMAT
    assert kwargs['tool_choice'] == 'none'
    assert 'tools' not in kwargs
    session.review_pages('UNABHÄNGIGE SICHTPRÜFUNG', None, (page,))
    assert 'text' not in session._client.responses.calls[-1]
