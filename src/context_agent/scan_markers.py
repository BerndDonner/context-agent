"""Prevent visible uncertainty metadata from leaking into reproduced documents."""
from __future__ import annotations

import re
from pathlib import Path

from context_agent.models import NogoFinding

_MARKER = re.compile(r'\[(?:Scan unklar:|Index unklar\])')


def visible_scan_markers(main_tex: Path) -> list[NogoFinding]:
    findings: list[NogoFinding] = []
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
            findings.append(NogoFinding(
                rule_id='visible-scan-uncertainty',
                message='Unklarer Scan ist als redaktioneller Platzhalter im sichtbaren PDF-Text',
                file='main.tex', line=line_no,
                repair_hint=('Plausible Transkription oder ? verwenden; an genau dieser '
                             'Stelle `% [Scan unklar: ...]` als ConTeXt-Kommentar setzen.'),
            ))
    return findings
