"""Prevent visible uncertainty metadata from leaking into reproduced documents."""
from __future__ import annotations

import re
from pathlib import Path

from context_agent.models import QualityFinding

_MARKER = re.compile(r'\[(?:Scan unklar:|Index unklar\])')


def visible_scan_markers(main_tex: Path) -> list[QualityFinding]:
    findings: list[QualityFinding] = []
    verbatim = False
    for line_no, line in enumerate(main_tex.read_text(encoding='utf-8').splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith((r'\starttyping', r'\startbuffer')):
            verbatim = True
        if stripped.startswith((r'\stoptyping', r'\stopbuffer')):
            verbatim = False
            continue
        if verbatim or stripped.startswith('%'):
            continue
        # Respect escaped percent signs, but not ordinary comment tails.
        content = re.split(r'(?<!\\)%', line, maxsplit=1)[0]
        if _MARKER.search(content):
            findings.append(QualityFinding(
                rule_id='visible-scan-uncertainty',
                message='Unklarer Scan ist als redaktioneller Platzhalter im sichtbaren PDF-Text',
                file='main.tex', line=line_no,
                repair_hint=('Plausible Transkription oder ? verwenden; an genau dieser '
                             'Stelle `% [Scan unklar: ...]` als ConTeXt-Kommentar setzen.'),
            ))
    return findings


def inherited_scan_uncertainties(main_tex: Path) -> list[str]:
    """Preserve existing, explicitly labelled source ambiguities in improve jobs.

    These findings are inherited review items, not new quality violations and
    not permission to change already visible placeholders without a task.
    """
    result: list[str] = []
    for line_number, line in enumerate(main_tex.read_text(encoding='utf-8').splitlines(), 1):
        # Skip the macro declaration itself and plain explanatory comments.
        if line.lstrip().startswith('%') or r'\define' in line:
            continue
        matches = re.findall(r'\\ScanUnklar\{([^{}]+)\}|\[(Index unklar[^]]*|Scan unklar:[^]]*)\]', line)
        for group in matches:
            value = next((item for item in group if item), '')
            if value:
                result.append(f'Ausgangsdatei Zeile {line_number}: {value}')
    return result
