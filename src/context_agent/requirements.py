"""General independent original-task audit for every generated document."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from context_agent.errors import ContextAgentError
from context_agent.models import QualityFinding, ResolvedJob


@dataclass(frozen=True)
class RequirementsResult:
    status: str
    findings: tuple[QualityFinding, ...]
    uncertainties: tuple[str, ...]


def prompt(job: ResolvedJob, main_tex: Path, *, pages: int) -> str:
    task = job.task_path.read_text(encoding='utf-8')
    template = job.template_path.read_text(encoding='utf-8')
    sources = []
    for item in job.inputs:
        if item.path.suffix.lower() in ('.txt', '.md', '.tex'):
            sources.append(f'{item.relative_path} ({item.policy}):\n' +
                           item.path.read_text(encoding='utf-8')[:28000])
        else:
            sources.append(f'{item.relative_path}: {item.role}/{item.policy} (external source)')
    tex = main_tex.read_text(encoding='utf-8')
    return ("UNABHÄNGIGE REQUIREMENTS VALIDATION. Prüfe ausschließlich gegen den ORIGINALAUFTRAG, "
            "Template und Quellen; NIEMALS allein gegen eine Zwischenfassung. "
            "Kontrolliere Inhalt, Zahlen, Formeln, Vollständigkeit und, soweit die "
            f"{pages} Ausgabeseitenbilder reichen, sichtbares Layout. "
            "Keine Schreibaktionen. Bei fehlender Evidenz UNCERTAIN statt PASSED. "
            "Keine nicht belegten Beanstandungen. JSON ohne Markdown: "
            '{"status":"passed|failed|uncertain","findings":['
            '{"message":"konkreter Fehler","file":"main.tex","line":null}],'
            '"uncertainties":["..." ]}.\n'
            f'ORIGINALAUFTRAG:\n{task}\nTEMPLATE:\n{template}\n'
            f'ORIGINALQUELLEN:\n{chr(10).join(sources)}\n'
            f'AUSGABESOURCE:\n{tex[:90000]}')


def parse_result(output: str) -> RequirementsResult:
    value = output.strip()
    if value.startswith('```'):
        value = re.sub(r'^```(?:json)?\s*|\s*```$', '', value)
    try:
        data = json.loads(value)
    except ValueError as exc:
        raise ContextAgentError('requirements review returned invalid JSON') from exc
    if not isinstance(data, dict) or data.get('status') not in ('passed', 'failed', 'uncertain'):
        raise ContextAgentError('requirements review returned invalid status')
    if not isinstance(data.get('findings'), list) or not isinstance(data.get('uncertainties'), list):
        raise ContextAgentError('requirements review returned invalid lists')
    findings = []
    for item in data['findings']:
        if not isinstance(item, dict) or not isinstance(item.get('message'), str):
            raise ContextAgentError('requirements review returned invalid finding')
        findings.append(QualityFinding('original-requirements', item['message'],
                            str(item.get('file')) if item.get('file') else None,
                            item.get('line') if isinstance(item.get('line'), int) else None))
    uncertainties=tuple(str(x) for x in data['uncertainties'] if isinstance(x,str))
    if data['status'] == 'passed' and (findings or uncertainties):
        raise ContextAgentError('requirements review cannot pass with findings or uncertainties')
    if data['status'] == 'failed' and not findings:
        raise ContextAgentError('failed requirements review must provide an evidence-backed finding')
    return RequirementsResult(data['status'],tuple(findings),uncertainties)
