from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from context_agent.errors import ArtifactError
from context_agent.reproduction import parse_review, render_pages, review_prompt


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
    assert 'Seitenumbrüche' in review_prompt(3, 1, 3, last=True)


def test_bad_reviews_fail_closed() -> None:
    for response in ['done', '{"findings":[],"uncertainties":"oops"}',
                     '{"findings":[{"type":"content","output_page":99,"message":"test","confidence":1}],"uncertainties":[]}']:
        with pytest.raises(ArtifactError):
            parse_review(response, start_page=1, end_page=3)
