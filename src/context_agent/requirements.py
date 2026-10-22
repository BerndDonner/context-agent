"""General independent original-task audit for every generated document."""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping

import fitz
from dataclasses import dataclass
from pathlib import Path

from context_agent.errors import ContextAgentError
from context_agent.include_sync import read_include_snapshot
from context_agent.models import QualityFinding, ResolvedJob


@dataclass(frozen=True)
class RequirementsResult:
    status: str
    findings: tuple[QualityFinding, ...]
    uncertainties: tuple[str, ...]
    regressions: tuple[dict[str, str], ...] = ()


def verified_evidence(
    job: ResolvedJob,
    *,
    main_pdf: Path,
    context_log: Path,
    include_snapshot: Path,
    initial_fingerprints: Mapping[str, str],
) -> dict[str, object]:
    """Facts checked by the orchestrator, not guesses by the LLM reviewer.

    Host-side file immutability is not a claim about the copies in the
    remote container. A valid PDF and a log file do not by themselves prove
    that recompilation will succeed on every other machine.
    """
    files = {
        'result/main.pdf': main_pdf,
        'result/context.log': context_log,
        'result/include-snapshot.tar.gz': include_snapshot,
    }
    artifacts = {
        name: {'exists': path.is_file(),
               'bytes': path.stat().st_size if path.is_file() else None}
        for name, path in files.items()
    }
    snapshot_count = (len(read_include_snapshot(include_snapshot))
                      if include_snapshot.is_file() else None)
    protected = (job.config_path, job.task_path, job.template_path,
                 *((job.source_path,) if job.source_path else ()),
                 *(item.path for item in job.inputs), *job.references)
    comparisons: dict[str, bool] = {}
    for path in protected:
        name = path.relative_to(job.root).as_posix()
        expected = initial_fingerprints.get(name)
        comparisons[name] = bool(path.is_file() and expected and
                                 hashlib.sha256(path.read_bytes()).hexdigest() == expected)
    fonts: dict[str, list[str]] = {}
    sample_font_runs: dict[str, list[dict[str, object]]] = {}
    if main_pdf.is_file():
        with fitz.open(main_pdf) as pdf:
            for i, page in enumerate(pdf):
                fonts[str(i + 1)] = sorted({entry[3] for entry in page.get_fonts()})
                runs = [
                    {'text': span['text'][:90], 'font': span['font'],
                     'size_pt': round(span['size'], 1)}
                    for block in page.get_text('dict')['blocks']
                    for line in block.get('lines', [])
                    for span in line['spans'] if span['text'].strip()
                ]
                sample_font_runs[str(i + 1)] = runs[:16]
            pdf_pages = len(pdf)
    else:
        pdf_pages = None
    return {
        'files': artifacts,
        'pdf_page_count': pdf_pages,
        'include_snapshot_validated_file_count': snapshot_count,
        'embedded_pdf_font_names_by_page': fonts,
        'sample_rendered_text_font_runs_by_page': sample_font_runs,
        'host_source_files_unchanged_since_start': comparisons,
        'limitations': ('Host input hashes do not establish whether remote temporary copies '
                        'were modified. The existence of a log and a readable PDF is not '
                        'an independent proof of reproducibility on another system.'),
    }


def prompt(job: ResolvedJob, main_tex: Path, *, pages: int,
           evidence: dict[str, object] | None = None) -> str:
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
    baseline = (job.source_path.read_text(encoding='utf-8')
                if job.source_path is not None else None)
    from context_agent.improvement import improvement_diff
    changed = (improvement_diff(baseline, tex) if baseline is not None else "")
    facts = json.dumps(evidence or {}, ensure_ascii=False, indent=2)
    if baseline is not None:
        # An improve audit is a DELTA audit, not re-transcription of the whole
        # document. The exact changed source passages include old/new context.
        # The independent reviewer sees real output page images separately.
        from context_agent.improvement import improvement_diff
        complete_diff = improvement_diff(baseline, tex, max_lines=1000000)
        compact_evidence = dict(evidence or {})
        # Images, not thousands of repeated extracted font spans, provide the
        # visual evidence. Keep the checked page font names and host integrity.
        compact_evidence.pop('sample_rendered_text_font_runs_by_page', None)
        return (
            'UNABHÄNGIGE REQUIREMENTS VALIDATION – IMPROVE-REGRESSIONS-AUDIT. Prüfe ausschließlich '
            'durch folgende Quelländerungen neu eingeführte Inhalts-, Zahlen-, '
            'Einheiten-, Formel- und Layoutfehler. Die ausgewählten Quality-Checker '
            'prüfen den Grad der Formatkorrektur getrennt. Alte Scanunsicherheiten '
            'und noch offene Formatierungsziele sind KEINE neuen Regressionen. '
            'Prüfe das beigefügte PDF-Seitenbild gegen den ORIGINALAUFTRAG und '
            'die Quelle. Die vollständigen ORIGINAL-/NEU-Passagen sind im '
            'unverkürzten Unified-Diff enthalten (mit Kontext). '
            'Für jeden vermuteten Fehler liefere exakte original_excerpt und '
            'updated_excerpt aus demselben geänderten Diff-Hunk. '
            'Ohne nachweisbare neue Quellabweichung nutze uncertainties, niemals '
            'eine erfundene Regression. Technische Fakten aus EVIDENZ gelten; '
            'wiederhole keine dort widerlegten Verfügbarkeitsbedenken. '
            'JSON ohne Markdown: '
            '{"status":"passed|failed|uncertain","findings":[],"uncertainties":[],"regressions":'
            '[{"message":"...","original_excerpt":"...","updated_excerpt":"..."}]}\n'
            f'MODUS: improve\nORIGINALAUFTRAG:\n{task}\n'
            f'VERBINDLICHES TEMPLATE:\n{template}\n'
            f'QUELLEINGABEN:\n{chr(10).join(sources)}\n'
            f'VOLLSTÄNDIGES ÄNDERUNGSDIFF:\n{complete_diff}\n'
            f'VERIFIZIERTE EVIDENZ:\n{json.dumps(compact_evidence, ensure_ascii=False)}'
        )
    improve_instruction = ("IMPROVE-DELTA-AUDIT: Bewerte AUSSCHLIESSLICH NEU durch die gezeigten "
        "ÄNDERUNGEN eingeführte inhaltliche oder Layout-Regressionen. "
        "Unveränderte Ausgangsmängel, vorhandene Scanunsicherheiten und noch "
        "nicht vollständig erledigte Formatierungsziele sind KEINE Regressionen. "
        "Formatierungsfortschritt beurteilen die ausgewählten Checker. "
        "Für jede neue Regression liefere unter regressions ein Objekt mit "
        "message, original_excerpt und updated_excerpt (exakte, nichtleere "
        "Teilzeichenfolgen aus den beigefügten ConTeXt-Quellen, in der "
        "betroffenen geänderten Passage). Ohne belegbare veränderte "
        "Quellpassage keine Regression behaupten; dann uncertainties nutzen. "
        "Nutze das beigefügte ORIGINAL-PDF nur zur Klärung schwieriger Stellen; "
        "wenn es beigefügt ist, behaupte NICHT es liege nicht vor. "
        "Antworte mit JSON-Feld regressions zusätzlich zu den anderen Feldern. "
        if baseline is not None else "")
    return ("UNABHÄNGIGE REQUIREMENTS VALIDATION. " + improve_instruction +
            "Prüfe ausschließlich gegen den ORIGINALAUFTRAG, "
            "Template und Quellen; NIEMALS allein gegen eine Zwischenfassung. "
            "Kontrolliere Inhalt, Zahlen, Formeln, Vollständigkeit und, soweit die "
            f"{pages} Ausgabeseitenbilder reichen, sichtbares Layout. "
            "Keine Schreibaktionen. Bei fehlender Evidenz zu einer FACHLICHEN "
            "Anforderung UNCERTAIN statt PASSED. Die untenstehenden, vom Orchestrator "
            "deterministisch verifizierten Fakten sind verbindliche Prüfevidenz. "
            "Melde Artefakte, überprüfte Schriftmetadaten oder unveränderte lokale "
            "Originaldateien NICHT erneut als unbekannt, wenn sie dort bestätigt sind. "
            "Unterscheide lokale Eingabeintegrität von nicht nachgewiesener "
            "Integrität entfernter temporärer Kopien. Letztere ist ohne konkrete "
            "Verdachtsmomente kein eigenständiger Dokumentmangel. "
            "Keine nicht belegten Beanstandungen. JSON ohne Markdown: "
            '{"status":"passed|failed|uncertain","findings":['
            '{"message":"konkreter Fehler","file":"main.tex","line":null}],'
            '"uncertainties":["..." ],"regressions":['
            '{"message":"...","original_excerpt":"...","updated_excerpt":"..."}]}.\n'
            f'MODUS: {job.config.mode.value}\nORIGINALAUFTRAG:\n{task}\nTEMPLATE:\n{template}\n'
            f'ORIGINALDATEI (bei improve verbindliche Baseline):\n{(baseline or "")[:60000]}\n'
            f'ÄNDERUNGEN GEGEN ORIGINALDATEI:\n{changed[:45000]}\n'
            f'ORIGINALQUELLEN:\n{chr(10).join(sources)}\n'
            f'AUSGABESOURCE:\n{tex[:90000]}\n'
            f'VERIFIZIERTE TECHNISCHE EVIDENZ:\n{facts}')


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
    if data['status'] == 'failed' and not findings and not data.get('regressions'):
        raise ContextAgentError('failed requirements review must provide an evidence-backed finding')
    regressions = data.get('regressions', [])
    if not isinstance(regressions, list):
        raise ContextAgentError('requirements review returned invalid regressions')
    validated = []
    for entry in regressions:
        if not isinstance(entry, dict) or not all(isinstance(entry.get(key), str) and
                entry[key].strip() for key in ('message','original_excerpt','updated_excerpt')):
            raise ContextAgentError('requirements review returned invalid regression evidence')
        validated.append({key: entry[key] for key in
                          ('message','original_excerpt','updated_excerpt')})
    if data['status'] == 'passed' and validated:
        raise ContextAgentError('requirements review cannot pass with regressions')
    return RequirementsResult(data['status'],tuple(findings),uncertainties,tuple(validated))


def verify_regressions(result: RequirementsResult, original: str,
                       updated: str) -> tuple[list[QualityFinding], list[str]]:
    """Only accept regressions with actual, changed, source-anchored evidence.

    Never compare language-model wording from independent baseline reviews.
    Inconclusive evidence cannot prove a regression and stays needs_review.
    """
    verified: list[QualityFinding] = []
    uncertainties: list[str] = []
    from difflib import SequenceMatcher
    old_lines, new_lines = original.splitlines(), updated.splitlines()
    changed = [('\n'.join(old_lines[i:j]), '\n'.join(new_lines[k:l]))
               for tag,i,j,k,l in SequenceMatcher(None,old_lines,new_lines,autojunk=False).get_opcodes()
               if tag != 'equal']
    for entry in result.regressions:
        old, new = entry['original_excerpt'], entry['updated_excerpt']
        anchored = any(old in before and new in after for before,after in changed)
        if (not anchored or old == new):
            uncertainties.append('Nicht verifizierbare geänderte Passage: ' + entry['message'])
            continue
        verified.append(QualityFinding('original-requirements',entry['message'],'main.tex'))
    return verified, uncertainties
