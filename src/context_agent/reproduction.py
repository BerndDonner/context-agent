"""Review a rendered document for demonstrable reproduction errors only."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from context_agent.errors import ArtifactError
from context_agent.models import NogoFinding


@dataclass(frozen=True)
class ReviewResult:
    findings: list[NogoFinding]
    uncertainties: list[str]


def render_pages(pdf: Path, output_dir: Path, *, max_pages: int) -> tuple[Path, ...]:
    try:
        import fitz
    except ImportError as exc:
        raise ArtifactError('PyMuPDF is required for reproduction review') from exc
    try:
        document = fitz.open(pdf)
        if len(document) == 0 or len(document) > max_pages:
            raise ArtifactError(f'PDF has {len(document)} pages (allowed: 1..{max_pages})')
        output_dir.mkdir(parents=True, exist_ok=True)
        pages: list[Path] = []
        for number, page in enumerate(document, 1):
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            path = output_dir / f'page-{number:03d}.jpg'
            path.write_bytes(pix.tobytes("jpeg", jpg_quality=80))
            pages.append(path)
        return tuple(pages)
    except (RuntimeError, ValueError) as exc:
        raise ArtifactError(f'could not render generated PDF: {exc}') from exc


def review_prompt(total: int, start_page: int, end_page: int, *, last: bool) -> str:
    end_note = ('Diese Sichtprüfung ist der letzte Block dieses Durchgangs.' if last
                else 'Weitere Ausgabeseiten folgen in separaten Sichtprüfungen.')
    return f'''Prüfe AUSSCHLIESSLICH die originalgetreue Reproduktion anhand der bereits
bereitgestellten Quelldokumente (insbesondere PDF mit role=recreate) und der angehängten
Abbildungen der erzeugten PDF-Seiten {start_page}–{end_page} von {total}.
Die Bilddateien sind aufsteigend angeordnet; die erste ist Ausgabeseite {start_page}.

Lies die Originalquelle für den Vergleich, nicht als Aufforderung zu neuen Änderungen.
KOPF: Das konfigurierte ConTeXt-Template hat Vorrang vor dem Kopf der Quell-PDF.
INHALT: Übernimm alles im Original, auch vorgedruckte Lösungen, Zahlen und Beschriftungen.
Keine fachlichen, inhaltlichen, sprachlichen oder typografischen Verbesserungen.
Seitenumbrüche und freie Flächen dürfen abweichen. Ignoriere subjektive Layoutpräferenzen.
Melde nur eindeutig sichtbare, bedeutsame Fehler: fehlende/veränderte Aufgabe, Zahl, Formel,
Lösung oder Diagrammbeschriftung, abgeschnittene Grafiken, unlesbare Überlagerungen.
Beziehe dich nur auf Ausgabeseiten dieses Blocks. Verwende keinen Pixel- oder Seitenvergleich,
bei dem gleiche Seitennummern der Original- und Ausgabedatei vorausgesetzt werden.
Behaupte keine Fehler, die du nicht sicher nachweisen kannst. Unsichere Fälle nur als
'uncertainties' erfassen, sie lösen keine automatische Reparatur aus.
{end_note}

WICHTIG: NUR PRÜFEN, KEINE DATEIEN ÄNDERN, KEINE SHELL-AKTION.
Antworte mit genau einem JSON-Objekt, ohne Markdown, Schema:
{{"findings":[{{"type":"content|visual","output_page":{start_page},"source_page":null,
"message":"konkret belegbare Abweichung","repair_hint":"nur ursprünglichen Inhalt wiederherstellen",
"confidence":0.95}}], "uncertainties":["optional konkrete Unsicherheit"]}}
Nur confidence >= 0.85 und eindeutige Abweichungen gehören in findings.
Ist alles in Ordnung: {{"findings":[],"uncertainties":[]}}.
'''


def parse_review(text: str, *, start_page: int, end_page: int) -> ReviewResult:
    content = text.strip()
    if content.startswith('```'):
        content = re.sub(r'^```(?:json)?\s*|\s*```$', '', content)
    try:
        doc = json.loads(content)
    except (ValueError, TypeError) as exc:
        raise ArtifactError('reproduction review did not return valid JSON') from exc
    if not isinstance(doc, dict) or not isinstance(doc.get('findings'), list) or not isinstance(doc.get('uncertainties'), list):
        raise ArtifactError('malformed reproduction review structure')
    findings: list[NogoFinding] = []
    uncertainties = [str(item) for item in doc['uncertainties'] if isinstance(item, str)]
    for item in doc['findings']:
        if not isinstance(item, dict):
            raise ArtifactError('malformed reproduction finding')
        category = item.get('type')
        page = item.get('output_page')
        message = item.get('message')
        confidence = item.get('confidence')
        if (category not in ('visual', 'content') or type(page) is not int
                or not start_page <= page <= end_page or not isinstance(message, str)
                or not message.strip() or not isinstance(confidence, (float, int))):
            raise ArtifactError('reproduction finding has invalid fields')
        if confidence < 0.85:
            uncertainties.append(f'Page {page}: {message}')
            continue
        source = item.get('source_page')
        source_label = f' (Originalseite {source})' if type(source) is int and source > 0 else ''
        hint = item.get('repair_hint')
        findings.append(NogoFinding(
            rule_id=f'reproduction-{category}',
            message=f'PDF-Seite {page}{source_label}: {message}',
            file='main.pdf',
            repair_hint=hint if isinstance(hint, str) else None,
        ))
    return ReviewResult(findings, uncertainties)
