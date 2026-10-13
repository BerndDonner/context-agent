from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from context_agent.errors import ArtifactError
from context_agent.job import load_job
from context_agent.models import NogoFinding
from context_agent.reproduction import (
    parse_review, render_pages, repair_prompt, reproduction_scope, review_prompt,
)


def test_render_pdf_pages(tmp_path: Path) -> None:
    pdf = tmp_path / 'generated.pdf'
    doc = fitz.open()
    for number in range(3):
        page = doc.new_page()
        page.insert_text((70, 70), f'page {number}')
    doc.save(pdf)
    doc.close()
    pages = render_pages(pdf, tmp_path / 'pages', max_pages=4)
    assert [p.name for p in pages] == ['page-001.jpg', 'page-002.jpg', 'page-003.jpg']
    assert pages[0].read_bytes().startswith(b'\xff\xd8')
    with pytest.raises(ArtifactError, match='allowed'):
        render_pages(pdf, tmp_path / 'other', max_pages=2)


def test_review_finds_only_certain_errors() -> None:
    result = parse_review('''{"findings": [
      {"type":"content","output_page":2,"source_page":4,"message":"Lösung fehlt",
       "repair_hint":"Lösung übernehmen", "confidence":0.96},
      {"type":"visual","output_page":2,"message":"vielleicht verwaschen",
       "confidence":0.5}], "uncertainties":[]}''', start_page=1, end_page=3)
    assert len(result.findings) == 1
    assert 'Lösung fehlt' in result.findings[0].message
    assert len(result.uncertainties) == 1
    assert 'Seitenumbrüche' in review_prompt(3, 1, 3, last=True, scope='test task')


def test_bad_reviews_fail_closed() -> None:
    for response in ['done', '{"findings":[],"uncertainties":"oops"}',
                     '{"findings":[{"type":"content","output_page":99,"message":"test","confidence":1}],"uncertainties":[]}']:
        with pytest.raises(ArtifactError):
            parse_review(response, start_page=1, end_page=3)


def test_job_scope_controls_subset_and_preserves_included_solutions(
    tmp_path: Path, job_factory,
) -> None:  # type: ignore[no-untyped-def]
    job_root = job_factory(tmp_path)
    (job_root / 'task.md').write_text(
        'Nur Aufgaben 3 bis 5; Seite 1 und das Deckblatt weglassen. '
        'Gedruckte Lösungen der Aufgaben 3 bis 5 übernehmen.',
        encoding='utf-8',
    )
    job = load_job(job_root)
    scope = reproduction_scope(job)
    prompt = review_prompt(5, 1, 4, last=False, scope=scope)
    assert 'Nur Aufgaben 3 bis 5' in scope
    assert 'Deckblatt weglassen' in prompt
    assert 'Policy=guidance' in scope
    assert 'Quell-PDF ist nicht automatisch vollständig' in scope
    assert 'späteren Ausgabeseiten' in prompt
    assert 'gedruckte' in prompt
    assert 'Quelle und Ausgabe' in prompt
    assert 'letzte Ausgabeseitenblock' in review_prompt(5, 5, 5, last=True, scope=scope)
    fixes = repair_prompt(
        [NogoFinding(rule_id='reproduction-content', message='Aufgabe 4 unvollständig')],
        scope=scope,
    )
    assert 'Nur Aufgaben 3 bis 5' in fixes
    assert 'keine ausdrücklich ausgeschlossenen Quellbestandteile' in fixes
    assert 'Aufgabe 4 unvollständig' in fixes


def test_full_reproduction_of_scanned_sheets_still_preserves_all_solutions(
    tmp_path: Path, job_factory,
) -> None:  # type: ignore[no-untyped-def]
    job_root = job_factory(tmp_path)
    (job_root / 'task.md').write_text(
        'Reproduziere sämtliche Aufgaben und vorhandenen Lösungen des gescannten '
        'Messtechnik-Arbeitsblatts. Übernehme den Kopf aus dem Template.',
        encoding='utf-8',
    )
    scope = reproduction_scope(load_job(job_root))
    prompt = review_prompt(11, 9, 11, last=True, scope=scope)
    assert 'sämtliche Aufgaben und vorhandenen Lösungen' in prompt
    assert 'gescannte PDFs OHNE Textebene' in prompt
    assert 'letzte Ausgabeseitenblock' in prompt
    assert 'Template-Vorgaben' in prompt
    assert 'GESAMTEN beauftragten Inhalts' in prompt


def test_review_prompt_references_do_not_create_new_reproduction_obligations(
    tmp_path: Path, job_factory,
) -> None:  # type: ignore[no-untyped-def]
    job_root = job_factory(tmp_path)
    reference = job_root / 'references' / 'tutorial.pdf'
    reference.write_bytes(b'pdf placeholder')
    config = job_root / 'job.yaml'
    config.write_text(config.read_text().replace('references: []',
                      'references:\n  - references/tutorial.pdf'))
    scope = reproduction_scope(load_job(job_root))
    assert 'references/tutorial.pdf: Referenz, nicht automatisch zu reproduzieren' in scope
