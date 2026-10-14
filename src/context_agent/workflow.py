from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import replace
from datetime import datetime, UTC
from collections.abc import Callable
from pathlib import Path

from context_agent.bundling import build_job_bundle, direct_model_files
from context_agent.checkpoint import SCHEMA, fingerprint, read_checkpoint, save_checkpoint
from context_agent.content_audit import (
    InventoryEntry, missing_prompt, output_prompt, parse_inventory,
    parse_missing, parse_output_check, source_prompt,
)
from context_agent.errors import ContextAgentError
from context_agent.job import load_job, prepare_result_directory
from context_agent.include_sync import IncludeTransaction, read_include_snapshot
from context_agent.models import (
    AgentTurn,
    ContentPolicy,
    InputRole,
    ArtifactState,
    CheckerFailure,
    QualityFinding,
    ResolvedJob,
    RunReport,
)
from context_agent.quality_rules import (QualityContext, findings_as_prompt, load_rules, run_checkers,
                                        check_edits, Edit)
from context_agent.quality_preflight import Preflight, llm_preflight
from context_agent.requirements import prompt as requirements_prompt, parse_result as parse_requirements
from context_agent.openai_backend import AgentSession, OpenAIHostedSession
from context_agent.progress import Progress
from context_agent.scan_markers import visible_scan_markers
from context_agent.prompts import (
    load_prompt,
    render_initial_prompt,
    render_missing_artifacts_prompt,
)
from context_agent.report import append_transcript, write_report
from context_agent.reproduction import (
    parse_review, render_pages, repair_prompt, reproduction_scope, review_prompt,
)

SessionFactory = Callable[[ResolvedJob, Path, tuple[Path, ...], str], AgentSession]


def default_session_factory(
    job: ResolvedJob,
    bundle_path: Path,
    direct_files: tuple[Path, ...],
    system_prompt: str,
) -> AgentSession:
    return OpenAIHostedSession(job, bundle_path, direct_files, system_prompt)


def run_job(
    job_directory: Path,
    *,
    session_factory: SessionFactory = default_session_factory,
    prompt_directory: Path | None = None,
    runtime_directory: Path | None = None,
    resume: bool = False,
    preflight_factory: Preflight | None = None,
) -> RunReport:
    """Run generation and independently validated quality-rule refinements.

    The function deliberately keeps the outer workflow small. The hosted model is responsible
    for inspecting files, compiling ConTeXt, and repairing compiler failures inside its sandbox.
    """
    original_job = load_job(job_directory)
    rules = load_rules(original_job)
    # Strict preflight BEFORE deleting or replacing any prior result.
    consistency = (preflight_factory or llm_preflight)(original_job, rules)
    if consistency.get('status') != 'passed':
        problems = consistency.get('conflicts', [])
        raise ContextAgentError('Quality/requirement preflight blocked execution: ' +
                                json.dumps(problems, ensure_ascii=False))
    selected = tuple(rule.id for rule in rules)
    plan = consistency['plan']
    progress = Progress()
    stored: dict | None = None
    stage = original_job.root / '.resume-work'
    if resume:
        # No migration from reports/transcripts produced before checkpoints.
        stored = read_checkpoint(original_job)
        if stage.exists():
            if not stage.is_dir():
                raise ContextAgentError('resume staging path is not a directory')
            # A previous interrupted resume can also be continued.
            staged_job = replace(original_job, result_dir=stage)
            staged = read_checkpoint(staged_job)
            stored = staged
        else:
            shutil.copytree(original_job.result_dir, stage)
        job = replace(original_job, result_dir=stage)
        progress('Resume: gespeicherten Arbeitsstand in separater Stage geöffnet')
    else:
        if stage.exists():
            raise ContextAgentError('unfinished resume work exists; complete resume or remove .resume-work explicitly')
        job = original_job
        prepare_result_directory(job.result_dir)
        progress(f'Job gestartet: {job.root.name}')
    include_transaction = IncludeTransaction.capture(job.include_dir)

    resource_root = Path(__file__).resolve().parent / "resources"
    prompt_dir = (prompt_directory or resource_root / "prompts").resolve()
    runtime_dir = (runtime_directory or resource_root / "runtime").resolve()

    report = RunReport(
        status="running",
        model=job.config.model,
        started_at=datetime.now(UTC),
        reasoning_effort=job.config.reasoning.effort,
        processing_mode=job.config.processing.mode,
    )
    report.consistency = {key:value for key,value in consistency.items() if key != 'usage'}
    report.quality_plan = plan
    if isinstance(consistency.get('usage'), dict):
        report.agent_turns += 1
        report.add_usage(consistency['usage'], phase='consistency-preflight')
    report_path = job.result_dir / "report.json"
    transcript_path = job.result_dir / "transcript.jsonl"
    session: AgentSession | None = None
    input_fingerprint = fingerprint(original_job)
    source_uncertainties: list[str] = list(stored.get('source_uncertainties', [])) if stored else []
    phase_state = 'started'
    generator_response_id: str | None = None
    if stored:
        report.source_inventory = list(stored.get('source_inventory', []))
        report.review_history = list(stored.get('review_history', []))
        report.quality_journal = list((stored.get('report') or {}).get('quality_journal', []))
        report.requirements_checks = list((stored.get('report') or {}).get('requirements_checks', []))
        # A new attempt gets a new repair budget, but historical totals remain visible.
        old_report = stored.get('report') or {}
        report.quality_repairs = int(old_report.get('quality_repairs', 0))
        report.content_repairs = int(old_report.get('content_repairs', 0))
        report.visual_repairs = int(old_report.get('visual_repairs', 0))
        report.review_repairs = report.content_repairs + report.visual_repairs
        for name in ('findings', 'content_findings', 'review_findings'):
            values = old_report.get(name, [])
            setattr(report, name, [QualityFinding(**value) for value in values])
        report.content_uncertainties = list(old_report.get('content_uncertainties', []))
        report.review_uncertainties = list(old_report.get('review_uncertainties', []))

    def checkpoint(phase: str) -> None:
        nonlocal phase_state
        phase_state = phase
        save_checkpoint(job.result_dir / 'checkpoint.json', {
            'schema': SCHEMA,
            'inputs': input_fingerprint,
            'phase': phase,
            'source_inventory': report.source_inventory,
            'source_uncertainties': source_uncertainties,
            'review_history': report.review_history,
            'generator_response_id': generator_response_id,  # reference only, never trusted for fresh container
            'report': report.as_dict(),
            'working_summary': ('Resume the saved ConTeXt artifacts; do not regenerate the '
                                'document unless artifacts are missing. Recheck after repairs.'),
        })

    checkpoint('resuming' if resume else 'started')

    def finish(state: ArtifactState) -> RunReport:
        outcome = _finish(report, state, report_path)
        checkpoint('finished-' + report.status)
        if resume and report.status == 'success':
            history = original_job.root / '.run-history'
            history.mkdir(exist_ok=True)
            previous = history / (datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ') + '-previous')
            os.replace(original_job.result_dir, previous)
            try:
                os.replace(job.result_dir, original_job.result_dir)
            except OSError:
                os.replace(previous, original_job.result_dir)
                raise
            # Returned paths and the durable report must refer to the installed result.
            report.artifacts = {
                name: str(original_job.result_dir / name)
                for name in report.artifacts
            }
            write_report(report, original_job.result_dir / 'report.json')
            progress(f'Resume erfolgreich; vorheriger Stand gesichert: {previous}')
        elif resume:
            progress('Resume nicht erfolgreich; result/ unverändert, Arbeitsstand unter .resume-work/')
        else:
            progress(f'Job beendet: {report.status}')
        return outcome

    try:
        with tempfile.TemporaryDirectory(prefix="context-agent-") as temporary:
            bundle_path = Path(temporary) / "context-agent-job.tar.gz"
            build_job_bundle(job, bundle_path, runtime_dir,
                             resume_result=(job.result_dir if resume else None), rules=rules)
            direct_files = direct_model_files(job)
            system_prompt = load_prompt(prompt_dir, "system.md")
            rule_instructions = '\n\n'.join(rule.llm_description() for rule in rules)
            if rule_instructions:
                system_prompt += ('\n\nAUSSCHLIESSLICH FÜR DIESEN JOB AUSGEWÄHLTE QUALITÄTSREGELN:\n'
                                  + rule_instructions)
            registered_resources = {}
            for rule in rules:
                for resource in rule.resources:
                    if resource.target in registered_resources:
                        continue
                    registered_resources[resource.target] = resource
                    source = job.template_path.read_text(encoding='utf-8')
                    already_defined = (f'\\def{resource.macro}' in source or
                                       any(f'\\def{resource.macro}' in file.read_text(
                                           encoding='utf-8',errors='replace')
                                           for file in job.include_dir.rglob('*.tex')))
                    if not already_defined:
                        system_prompt += (f'\n\nHilfsmakro {resource.macro} ist als technische '
                            f'Ressource {resource.target} verfügbar. Falls benötigt, '
                            f'binde es genau einmal mit \\input {resource.include} ein. '
                            'Das verbindliche Schul-Template bleibt unverändert.\n')
            initial_quality = ('\n\nAUSGEWÄHLTE QUALITÄTSREGELN UND LLM-PLAN:\n'
                               + rule_instructions + '\nBatches: '
                               + json.dumps(plan, ensure_ascii=False))
            progress('Hosted-Container wird vorbereitet')
            session = session_factory(job, bundle_path, direct_files, system_prompt)
            report.remote_container_id = session.container_id
            progress('Hosted-Container bereit')

            # Capture the sources BEFORE creation, in stateless model requests.
            # Keep rendered source pages alive for subsequent independent visual
            # comparisons, including after a repair cycle.
            scope = reproduction_scope(job) if job.config.review.reproduction else ""
            source_entries: list[InventoryEntry] = []
            source_visuals: list[tuple[str, Path]] = []
            if job.config.review.reproduction:
                if resume and report.source_inventory:
                    source_entries = [InventoryEntry(**entry) for entry in report.source_inventory]
                    source_visuals = _render_source_visuals(
                        job, Path(temporary) / 'source-pages')
                    progress(f'Quelleninventar wiederverwendet: {len(source_entries)} Einträge')
                else:
                    progress('Quelleninventar wird erstellt')
                    source_entries, source_uncertainties, source_visuals = _inventory_sources(
                        session=session, job=job, scope=scope,
                        source_directory=Path(temporary) / "source-pages",
                        report=report, transcript_path=transcript_path,
                        progress=progress,
                    )
                    report.source_inventory = [entry.as_dict() for entry in source_entries]
                    checkpoint('inventory-complete')
                    progress(f'Quelleninventar fertig: {len(source_entries)} Einträge')

            state = _artifact_state(job.result_dir) if resume else ArtifactState(None, None, None)
            if resume and not _missing_artifacts(state):
                progress('Vorhandene PDF und ConTeXt-Quellen übernommen; keine Neugenerierung')
                # New container has no generation conversation. It will be bootstrapped
                # only if a targeted repair is required.
            else:
                if not _may_turn(report, job):
                    raise ContextAgentError('Quelleninventar verbrauchte alle Agentenrunden')
                initial_prompt = render_initial_prompt(job, prompt_dir) + initial_quality
                if job.config.review.reproduction:
                    initial_prompt += ("\n\nVORAB ERSTELLTES QUELLENINVENTAR:\n" +
                                       json.dumps(report.source_inventory, ensure_ascii=False) +
                                       "\nUnsichere Originalstellen NICHT als sicher ausgeben:\n" +
                                       json.dumps(source_uncertainties, ensure_ascii=False))
                    initial_prompt += _uncertainty_generation_instruction()
                progress('Dokumenterzeugung gestartet')
                turn = _call_turn(
                    session=session, prompt=initial_prompt,
                    previous_response_id=None, phase='initial',
                    report=report, transcript_path=transcript_path,
                )
                generator_response_id = turn.response_id
                state = _sync_state(session, job.result_dir)
                checkpoint('generated')
                progress(f'Dokumentartefakte synchronisiert: {len(_missing_artifacts(state))} fehlen')

            def repair(text: str, phase: str) -> ArtifactState:
                nonlocal generator_response_id
                if generator_response_id is None:
                    # The previous model response and old container are deliberately
                    # NOT resumed. Bootstrap the fresh container using bundled artifacts.
                    bootstrap = render_resume_prompt(job, prompt_dir,
                                                     source_uncertainties=source_uncertainties)
                    prompt = bootstrap + '\n\nAKTUELLER REPARATURAUFTRAG:\n' + text
                else:
                    prompt = text
                if job.config.review.reproduction:
                    prompt += _uncertainty_generation_instruction()
                progress(f'Reparatur gestartet: {phase}')
                result = _call_turn(session=session, prompt=prompt,
                                    previous_response_id=generator_response_id,
                                    phase=phase, report=report,
                                    transcript_path=transcript_path)
                generator_response_id = result.response_id
                updated = _sync_state(session, job.result_dir)
                checkpoint('repair-complete')
                progress(f'Reparatur beendet: {phase}')
                return updated

            while _missing_artifacts(state) and _may_turn(report, job):
                prompt = render_missing_artifacts_prompt(_missing_artifacts(state), prompt_dir)
                state = repair(prompt, 'repair-artifacts')

            missing = _missing_artifacts(state)
            if missing:
                report.errors.append("Missing or invalid result artifacts: " + ", ".join(missing))
                report.status = "failed"
                return finish(state)

            quality_repairs = 0
            content_repairs = 0
            visual_repairs = 0
            quality_seen: set[str] = set()
            last_validated = job.result_dir / '.validated'
            was_quality_repair = False
            pending_quality_batch: list[str] = []
            baseline_quality_counts: dict[str,int] = {}
            while True:
                if _missing_artifacts(state):
                    report.errors.append('Required artifacts were lost after repair')
                    report.status = 'failed'
                    break
                report.review_findings = []
                report.review_uncertainties = []
                report.content_findings = []
                report.content_uncertainties = []
                # Requirements are always reviewed BEFORE quality and after every
                # refinement. Non-reproduction jobs use an independent audit too.
                if not job.config.review.reproduction:
                    if not _may_turn(report, job):
                        report.review_uncertainties.append('Budget exhausted before requirements validation')
                        report.status = 'needs_review'
                        break
                    with tempfile.TemporaryDirectory(prefix='context-agent-requirements-') as td:
                        try:
                            pages = render_pages(state.main_pdf, Path(td),
                                max_pages=job.config.review.max_pages)
                        except Exception as exc:
                            raise ContextAgentError(f'Unable to render generated PDF for requirements audit: {exc}') from exc
                        all_findings = []
                        all_uncertainties = []
                        for offset in range(0, len(pages), job.config.review.pages_per_batch):
                            _require_review_turn(report, job)
                            batch = pages[offset:offset + job.config.review.pages_per_batch]
                            prompt = requirements_prompt(job, state.main_tex, pages=len(pages))
                            prompt += f'\nOutput pages {offset+1} through {offset+len(batch)} of {len(pages)}.'
                            checked = _call_review(session=session, prompt=prompt,
                                previous_response_id=None, pages=batch, report=report,
                                transcript_path=transcript_path, phase='review-requirements')
                            result = parse_requirements(checked.output_text)
                            all_findings.extend(result.findings)
                            all_uncertainties.extend(result.uncertainties)
                            if result.status == 'uncertain' and not result.uncertainties:
                                all_uncertainties.append('Requirements not verifiable with available evidence')
                        report.content_findings = list(all_findings)
                        report.content_uncertainties = list(all_uncertainties)
                    report.requirements_checks.append({
                        'phase': 'requirements',
                        'source_sha256': _source_digest(state),
                        'status': ('failed' if report.content_findings else
                                   'uncertain' if report.content_uncertainties else 'passed'),
                        'findings': [f.as_dict() for f in report.content_findings],
                        'uncertainties': list(report.content_uncertainties),
                    })
                    checkpoint('requirements-reviewed')
                    if report.content_findings:
                        if was_quality_repair:
                            _restore_validated(job.result_dir, last_validated)
                            state = _artifact_state(job.result_dir)
                            report.quality_journal.append({'event':'rollback',
                                 'reason':'original requirements regressed'})
                            report.status = 'needs_review'
                            break
                        if content_repairs >= job.config.review.max_content_repairs or not _may_turn(report, job):
                            report.status = 'failed'
                            break
                        content_repairs += 1
                        report.content_repairs += 1
                        report.review_repairs += 1
                        state = repair(findings_as_prompt(report.content_findings),
                                       f'repair-requirements-{content_repairs}')
                        continue
                    if report.content_uncertainties:
                        if was_quality_repair:
                            _restore_validated(job.result_dir, last_validated)
                            state = _artifact_state(job.result_dir)
                            report.quality_journal.append({'event':'rollback',
                                 'reason':'requirements verification uncertain'})
                        report.status = 'needs_review'
                        break
                else:
                    report.content_uncertainties = list(source_uncertainties)
                    progress('Unabhängige Inhaltsprüfung gestartet')

                    assert state.main_pdf is not None
                    with tempfile.TemporaryDirectory(prefix="context-agent-content-") as temporary:
                        output_pages = render_pages(state.main_pdf, Path(temporary),
                                                    max_pages=job.config.review.max_pages)
                        content_findings: list[QualityFinding] = []
                        present: set[str] = set()
                        mismatched_ids: set[str] = set()
                        for offset in range(0, len(output_pages), job.config.review.pages_per_batch):
                            _require_review_turn(report, job)
                            batch = output_pages[offset:offset + job.config.review.pages_per_batch]
                            prompt = output_prompt(source_entries, scope=scope,
                                                   start=offset + 1, end=offset + len(batch),
                                                   total=len(output_pages))
                            progress(f'Inhalt: Ausgabeseiten {offset + 1}-{offset + len(batch)} '
                                     f'von {len(output_pages)}')
                            checked = _call_review(
                                session=session, prompt=prompt, previous_response_id=None,
                                pages=batch, report=report, transcript_path=transcript_path,
                                phase="review-content",
                            )
                            result = parse_output_check(checked.output_text, entries=source_entries,
                                                        start=offset + 1, end=offset + len(batch))
                            present.update(result.present)
                            content_findings.extend(result.findings)
                            mismatched_ids.update(result.affected)
                            report.content_uncertainties.extend(result.uncertainties)
                        pending = [entry for entry in source_entries
                                   if entry.id not in present and entry.id not in mismatched_ids]
                        if pending:
                            _require_review_turn(report, job)
                            missing_review = _call_review(
                                session=session,
                                prompt=missing_prompt(pending, scope=scope),
                                previous_response_id=None,
                                pages=output_pages,  # ALL pages, not earlier model memory
                                phase="review-content-missing",
                                report=report, transcript_path=transcript_path,
                            )
                            missing_findings, uncertainties = parse_missing(
                                missing_review.output_text, pending)
                            content_findings.extend(missing_findings)
                            report.content_uncertainties.extend(uncertainties)
                        if not source_entries:
                            report.content_uncertainties.append(
                                'Kein überprüfbares Quelleninventar erstellt; Vollständigkeit nicht bestätigt.')
                    report.content_findings = content_findings
                    report.review_history.append({
                        "phase": "content", "findings": [f.as_dict() for f in content_findings],
                        "uncertainties": list(report.content_uncertainties),
                    })
                    checkpoint('content-reviewed')
                    if content_findings:
                        progress(f'Inhaltsprüfung: {len(content_findings)} Fehler')
                        if content_repairs >= job.config.review.max_content_repairs or not _may_turn(report, job):
                            break
                        content_repairs += 1
                        report.content_repairs += 1
                        report.review_repairs += 1
                        state = repair(repair_prompt(content_findings, scope=scope),
                                       f'repair-content-{content_repairs}')
                        if _missing_artifacts(state):
                            report.errors.append("A content repair destroyed required artifacts.")
                            break
                        continue
                    progress('Unabhängige Sichtprüfung gestartet')
                    review_findings: list[QualityFinding] = []
                    with tempfile.TemporaryDirectory(prefix="context-agent-review-") as temporary:
                        assert state.main_pdf is not None
                        pages = render_pages(state.main_pdf, Path(temporary),
                                             max_pages=job.config.review.max_pages)
                        batch_size = job.config.review.pages_per_batch
                        for offset in range(0, len(pages), batch_size):
                            _require_review_turn(report, job)
                            batch = pages[offset:offset + batch_size]
                            prompt = review_prompt(len(pages), offset + 1, offset + len(batch),
                                                   last=(offset + len(batch) == len(pages)),
                                                   scope=scope,
                                                   source_labels=[name for name, _ in source_visuals],
                                                   inventory=report.source_inventory)
                            # Originals first, then this output batch. Every visual
                            # reviewer sees the originals but no generator transcript.
                            visual_pages = tuple(path for _, path in source_visuals) + batch
                            progress(f'Sichtprüfung: Ausgabeseiten {offset + 1}-{offset + len(batch)} '
                                     f'von {len(pages)}')
                            checked = _call_review(session=session, prompt=prompt,
                                                   previous_response_id=None,
                                                   pages=visual_pages, report=report,
                                                   transcript_path=transcript_path,
                                                   phase="review-reproduction")
                            review = parse_review(checked.output_text,
                                                  start_page=offset + 1,
                                                  end_page=offset + len(batch))
                            review_findings.extend(review.findings)
                            report.review_uncertainties.extend(review.uncertainties)
                    report.review_findings = review_findings
                    report.review_history.append({
                        "phase": "visual", "findings": [f.as_dict() for f in review_findings],
                        "uncertainties": list(report.review_uncertainties),
                    })
                    checkpoint('visual-reviewed')
                    if review_findings:
                        progress(f'Sichtprüfung: {len(review_findings)} Fehler')
                        if visual_repairs >= job.config.review.max_visual_repairs or not _may_turn(report, job):
                            break
                        visual_repairs += 1
                        report.visual_repairs += 1
                        report.review_repairs += 1
                        state = repair(repair_prompt(review_findings, scope=scope),
                                       f'repair-reproduction-{visual_repairs}')
                        if _missing_artifacts(state):
                            report.errors.append("A reproduction repair destroyed required artifacts.")
                            break
                        continue
                # A successful requirements check is the only accepted rollback baseline.
                if report.review_uncertainties or report.content_uncertainties:
                    report.status = 'needs_review'
                    break
                # A repaired state may not replace the rollback baseline until
                # BOTH original requirements AND other selected rules pass.
                if not was_quality_repair:
                    _save_validated(job.result_dir, last_validated, report)
                # Use one checker pass on the SAME main.tex/include snapshot.
                if rules:
                    assert state.main_tex is not None and state.include_snapshot is not None
                    remote_files = read_include_snapshot(state.include_snapshot)
                    include_transaction.changes(remote_files)
                    with tempfile.TemporaryDirectory(prefix='context-agent-quality-includes-') as stage:
                        include_stage = Path(stage) / 'include'
                        for relative, data in remote_files.items():
                            dst = include_stage / relative
                            dst.parent.mkdir(parents=True, exist_ok=True)
                            dst.write_bytes(data)
                        def remote_lint(name: str) -> list[QualityFinding]:
                            if name != 'dollar_math':
                                raise ContextAgentError(f'unknown dynamic lint: {name}')
                            if not _may_turn(report, job):
                                raise ContextAgentError('Not enough turns for dynamic ConTeXt lint')
                            payload, turn = session.run_dollar_lint(
                                max_api_calls=job.config.limits.max_agent_turns - report.agent_turns)
                            report.agent_turns += turn.api_calls
                            report.response_ids.extend(turn.raw.get('response_ids', [turn.response_id]))
                            report.add_usage(turn.usage, phase='quality-dollar-lint', raw=turn.raw)
                            append_transcript(transcript_path, turn_number=report.agent_turns,
                                              phase='quality-dollar-lint', turn=turn)
                            return [QualityFinding(**dict(item, rule_id='dollar_math'))
                                    for item in payload['findings']]
                        context = QualityContext(job, state.main_tex, state.main_pdf, state.context_log,
                                                 include_stage, remote_lint)
                        findings, failures = run_checkers(rules, context)
                        if failures:
                            report.checker_failures.extend(failures)
                            report.status = 'failed'
                            report.errors.append('Selected quality checker failed')
                            break
                        if job.config.review.reproduction:
                            findings.extend(visible_scan_markers(state.main_tex))
                        # The LLM performs one targeted semantic checker pass to cover
                        # problems a conservative regex checker cannot prove or find.
                        if _may_turn(report, job):
                            review = _call_review_text(session=session,
                                prompt=_quality_semantic_prompt(rules, state.main_tex, findings),
                                previous_response_id=None, report=report,
                                transcript_path=transcript_path, phase='quality-semantic-check')
                            semantic, dismissed = _quality_semantic_findings(
                                review.output_text, selected, len(findings))
                            findings = [finding for index, finding in enumerate(findings)
                                if index not in dismissed or finding.certainty == 'confirmed']
                            findings.extend(semantic)
                        else:
                            report.review_uncertainties.append('No budget for semantic quality audit')
                        report.findings = _deduplicate(findings)
                        current_counts = _quality_counts(report.findings)
                        if was_quality_repair:
                            worsened = {rule: (baseline_quality_counts.get(rule,0), count)
                                for rule, count in current_counts.items()
                                if rule not in pending_quality_batch and
                                   count > baseline_quality_counts.get(rule,0)}
                            if worsened:
                                _restore_validated(job.result_dir, last_validated)
                                state = _artifact_state(job.result_dir)
                                report.quality_journal.append({'event':'rollback',
                                    'reason':'another selected rule regressed',
                                    'worsened':worsened})
                                report.status = 'needs_review'
                                break
                            report.quality_journal.append({'event':'regression_gate_passed',
                                                   'source_sha256':_source_digest(state)})
                            was_quality_repair = False
                            pending_quality_batch = []
                            _save_validated(job.result_dir, last_validated, report)
                        if report.review_uncertainties:
                            report.status = 'needs_review'
                            break
                        if report.findings:
                            if quality_repairs >= job.config.limits.max_quality_repairs or not _may_turn(report, job):
                                report.status = 'needs_review'
                                break
                            digest = _source_digest(state)
                            if digest in quality_seen:
                                report.status = 'needs_review'
                                report.quality_journal.append({'event':'no_progress','source_sha256':digest})
                                break
                            quality_seen.add(digest)
                            # Batch only rules selected by the LLM plan; do not
                            # run new rules or blindly apply overlapping edits.
                            pending_batch = next((batch for batch in plan if any(
                                f.rule_id in batch for f in report.findings)), list(selected))
                            batch_findings = [f for f in report.findings if f.rule_id in pending_batch]
                            baseline_quality_counts = current_counts
                            pending_quality_batch = pending_batch
                            edits: list[Edit] = []
                            for rule in rules:
                                if rule.id in pending_batch and rule.propose_edits:
                                    edits.extend(rule.propose_edits(context, batch_findings))
                            if edits:
                                try:
                                    check_edits(state.main_tex.read_text(encoding='utf-8'), edits)
                                except ValueError as exc:
                                    report.quality_journal.append({'event':'edit_conflict','reason':str(exc)})
                                    edits = []
                            quality_repairs += 1
                            report.quality_repairs += 1
                            report.quality_journal.append({'event':'attempt',
                                 'source_sha256':digest, 'batch':pending_batch,
                                 'findings':[f.as_dict() for f in batch_findings],
                                 'edits':[e.as_dict() for e in edits]})
                            if edits and hasattr(session, 'apply_quality_edits'):
                                progress(f'{len(edits)} atomare Autofixes: {pending_batch}')
                                try:
                                    turn = session.apply_quality_edits(
                                        [e.as_dict() for e in edits],
                                        max_api_calls=job.config.limits.max_agent_turns-report.agent_turns)
                                    report.agent_turns += turn.api_calls
                                    report.response_ids.extend(turn.raw.get('response_ids', [turn.response_id]))
                                    report.add_usage(turn.usage, phase='quality-autofix', raw=turn.raw)
                                    append_transcript(transcript_path, turn_number=report.agent_turns,
                                                      phase='quality-autofix', turn=turn)
                                    state = _sync_state(session, job.result_dir)
                                except Exception as exc:
                                    _restore_validated(job.result_dir, last_validated)
                                    state = _artifact_state(job.result_dir)
                                    report.quality_journal.append({'event':'rollback', 'reason':str(exc)})
                                    report.status = 'needs_review'
                                    break
                            else:
                                prompt = findings_as_prompt(batch_findings, rules)
                                prompt += '\nVom LLM geplanter Batch: ' + ', '.join(pending_batch)
                                state = repair(prompt, f'refine-{quality_repairs}')
                            if _missing_artifacts(state):
                                _restore_validated(job.result_dir, last_validated)
                                state = _artifact_state(job.result_dir)
                                report.quality_journal.append({'event':'rollback',
                                     'reason':'repair did not compile or lost artifacts'})
                                report.status = 'needs_review'
                                break
                            if _source_digest(state) == digest:
                                _restore_validated(job.result_dir, last_validated)
                                state = _artifact_state(job.result_dir)
                                report.quality_journal.append({'event':'rollback',
                                     'reason':'quality repair made no effective source/include change'})
                                report.status = 'needs_review'
                                break
                            was_quality_repair = True
                            checkpoint('quality-repaired-unvalidated')
                            continue
                if not rules:
                    _save_validated(job.result_dir, last_validated, report)
                # No selected-rule violations remain.
                # Uncertainty is NOT proof of fidelity. Do not change Git files.
                if report.review_uncertainties or report.content_uncertainties:
                    progress('Offene Quellunsicherheiten: manuelle Prüfung erforderlich')
                    report.status = "needs_review"
                    break
                # Do not touch Git working files before all checks succeeded.
                assert state.include_snapshot is not None
                accepted_includes = read_include_snapshot(state.include_snapshot)
                report.include_changes = include_transaction.apply(accepted_includes)
                report.status = "success"
                break

            report.compile_success = not _missing_artifacts(state)
            if report.status not in ("success", "needs_review", "failed"):
                report.status = "failed"
            if report.status != 'success':
                if report.findings:
                    report.errors.append(f"{len(report.findings)} quality finding(s) remain.")
                if report.review_findings:
                    report.errors.append(
                        f"{len(report.review_findings)} reproduction finding(s) remain.")
                if report.content_findings:
                    report.errors.append(
                        f"{len(report.content_findings)} content finding(s) remain.")
                if report.checker_failures:
                    report.errors.append("Quality checker failure prevents acceptance.")

            return finish(state)

    except ContextAgentError as exc:
        report.status = "failed"
        report.errors.append(str(exc))
        return finish(_artifact_state(job.result_dir))
    except Exception as exc:
        report.status = "failed"
        report.errors.append(f"Unexpected error: {type(exc).__name__}: {exc}")
        finish(_artifact_state(job.result_dir))
        raise
    finally:
        if session is not None:
            session.close()



def _source_digest(state: ArtifactState) -> str:
    import hashlib
    assert state.main_tex is not None and state.include_snapshot is not None
    sha = hashlib.sha256()
    for file in (state.main_tex, state.include_snapshot):
        sha.update(file.read_bytes())
    return sha.hexdigest()


def _save_validated(result_dir: Path, snapshot: Path, report: RunReport) -> None:
    import hashlib
    snapshot.mkdir(exist_ok=True)
    files = ('main.tex','main.pdf','context.log','include-snapshot.tar.gz')
    hashes = {}
    for name in files:
        data = (result_dir / name).read_bytes()
        hashes[name] = hashlib.sha256(data).hexdigest()
        (snapshot / name).write_bytes(data)
    (snapshot / 'validation.json').write_text(json.dumps({
         'files':hashes, 'requirements': report.requirements_checks[-1:]
         if report.requirements_checks else report.review_history[-2:],
    }, ensure_ascii=False, indent=2), encoding='utf-8')


def _restore_validated(result_dir: Path, snapshot: Path) -> None:
    if not (snapshot / 'validation.json').is_file():
        raise ContextAgentError('no requirements-validated rollback snapshot')
    data=json.loads((snapshot / 'validation.json').read_text(encoding='utf-8'))
    import hashlib
    for name, expected in data['files'].items():
        source=snapshot / name
        if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
            raise ContextAgentError(f'validated snapshot corrupted: {name}')
    for name in data['files']:
        shutil.copy2(snapshot / name, result_dir / name)


def _quality_counts(findings: list[QualityFinding]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.rule_id] = counts.get(finding.rule_id, 0) + 1
    return counts


def _quality_semantic_prompt(rules, source: Path,
                             candidates: list[QualityFinding]) -> str:
    return ("Unabhängige QUALITÄTSPRÜFUNG auf dem Satzquelltext. "
            "Nutze ausschließlich die explizit ausgewählten Regeln. "
            "Die Python-Erkennung liefert unten nummerierte Kandidaten, KEINE "
            "automatisch sicheren Verstöße. Prüfe sie im Kontext und "
            "dismisse nachweislich harmlose Kandidaten anhand des 0-basierten Index. "
            "Füge ggf. weitere semantische Befunde hinzu. "
            "Kein Quellcodewechsel, keine Shell. Keine zusätzlichen Regeln aktivieren. "
            "Nur belegbare Befunde; unklare Dinge bleiben Warnungen. "
            "JSON ohne Markdown: {\"findings\":[{\"rule_id\":\"id\", "
            "\"message\":\"...\",\"certainty\":\"confirmed|candidate|warning\", "
            "\"severity\":\"error|warning\",\"line\":12}], "
            "\"dismissed_candidates\":[0],\"uncertainties\":[]}.\n"
            + '\n'.join(r.llm_description() for r in rules)
            + '\nPYTHON-KANDIDATEN (0-basiert):\n'
            + json.dumps([f.as_dict() for f in candidates], ensure_ascii=False)
            + '\nQUELLTEXT:\n' + source.read_text(encoding='utf-8')[:100000])


def _quality_semantic_findings(output: str, selected: tuple[str, ...],
                               candidate_count: int) -> tuple[list[QualityFinding], set[int]]:
    import re
    value = output.strip()
    if value.startswith('```'):
        value = re.sub(r'^```(?:json)?\s*|\s*```$', '', value)
    try:
        data = json.loads(value)
    except ValueError as exc:
        raise ContextAgentError('semantic quality checker returned invalid JSON') from exc
    if not isinstance(data, dict) or not isinstance(data.get('findings'),list) or not isinstance(data.get('uncertainties'),list):
        raise ContextAgentError('malformed semantic quality report')
    dismissed = data.get('dismissed_candidates', [])
    if not isinstance(dismissed,list) or any(type(i) is not int or i < 0 or i >= candidate_count for i in dismissed):
        raise ContextAgentError('quality audit attempted invalid candidate dismissal')
    findings = []
    for item in data['findings']:
        if not isinstance(item,dict) or item.get('rule_id') not in selected or not isinstance(item.get('message'),str):
            raise ContextAgentError('semantic checker returned an unselected rule')
        if item.get('certainty') not in ('confirmed','candidate','warning') or item.get('severity') not in ('error','warning'):
            raise ContextAgentError('semantic checker returned invalid finding classification')
        findings.append(QualityFinding(item['rule_id'],item['message'],
              file='main.tex',line=item.get('line') if isinstance(item.get('line'),int) else None,
              certainty=item['certainty'],severity=item['severity']))
    for uncertainty in data['uncertainties']:
        if isinstance(uncertainty,str):
            findings.append(QualityFinding(selected[0], uncertainty,
                                           certainty='warning',severity='warning'))
    return findings, set(dismissed)


def _deduplicate(findings: list[QualityFinding]) -> list[QualityFinding]:
    unique={}
    for finding in findings:
        key=(finding.rule_id, finding.file, finding.line, finding.message)
        unique[key]=finding
    return list(unique.values())


def _call_turn(
    *,
    session: AgentSession,
    prompt: str,
    previous_response_id: str | None,
    phase: str,
    report: RunReport,
    transcript_path: Path,
) -> AgentTurn:
    if previous_response_id is None:
        turn = session.run_initial(prompt)
    else:
        turn = session.run_followup(prompt, previous_response_id)

    report.agent_turns += 1
    report.response_ids.append(turn.response_id)
    report.add_usage(turn.usage, phase=phase, raw=turn.raw)
    # The API may report the actual tier (e.g. priority for fast requests).
    actual_tier = turn.raw.get("service_tier")
    if isinstance(actual_tier, str) and actual_tier not in report.observed_service_tiers:
        report.observed_service_tiers.append(actual_tier)
    append_transcript(
        transcript_path,
        turn_number=report.agent_turns,
        phase=phase,
        turn=turn,
    )
    return turn


def _call_review(
    *, session: AgentSession, prompt: str, previous_response_id: str | None,
    pages: tuple[Path, ...], report: RunReport, transcript_path: Path,
    phase: str = "review-reproduction",
) -> AgentTurn:
    turn = session.review_pages(prompt, previous_response_id, pages)
    report.agent_turns += 1
    report.response_ids.append(turn.response_id)
    report.add_usage(turn.usage, phase=phase, raw=turn.raw)
    # The API may report the actual tier (e.g. priority for fast requests).
    actual_tier = turn.raw.get("service_tier")
    if isinstance(actual_tier, str) and actual_tier not in report.observed_service_tiers:
        report.observed_service_tiers.append(actual_tier)
    append_transcript(transcript_path, turn_number=report.agent_turns,
                      phase=phase, turn=turn)
    return turn


def _call_review_text(
    *, session: AgentSession, prompt: str, previous_response_id: str | None,
    report: RunReport, transcript_path: Path, phase: str,
) -> AgentTurn:
    turn = session.review_text(prompt, previous_response_id)
    report.agent_turns += 1
    report.response_ids.append(turn.response_id)
    report.add_usage(turn.usage, phase=phase, raw=turn.raw)
    tier = turn.raw.get('service_tier')
    if isinstance(tier, str) and tier not in report.observed_service_tiers:
        report.observed_service_tiers.append(tier)
    append_transcript(transcript_path, turn_number=report.agent_turns,
                      phase=phase, turn=turn)
    return turn


def _require_review_turn(report: RunReport, job: ResolvedJob) -> None:
    if not _may_turn(report, job):
        raise ContextAgentError(
            'Not enough max_agent_turns to complete independent content/visual review. '
            'Increase limits.max_agent_turns; the document is not accepted.')


def _inventory_sources(
    *, session: AgentSession, job: ResolvedJob, scope: str,
    source_directory: Path, report: RunReport, transcript_path: Path,
    progress: Progress | None = None,
) -> tuple[list[InventoryEntry], list[str], list[tuple[str, Path]]]:
    """Read original sources before generation; retain images for later review."""
    entries: list[InventoryEntry] = []
    uncertainties: list[str] = []
    source_visuals: list[tuple[str, Path]] = []
    sources = [item for item in job.inputs if
               item.role == InputRole.RECREATE or
               (item.role in (InputRole.CONTENT, InputRole.STATEMENT)
                and item.policy in (ContentPolicy.VERBATIM, ContentPolicy.IMMUTABLE))]
    if not sources:
        return [], ['Kein verbindlicher Reproduktionsinput konfiguriert.'], []
    for number, item in enumerate(sources, 1):
        suffix = item.path.suffix.lower()
        if suffix == '.pdf':
            pages = render_pages(item.path, source_directory / f'source-{number}',
                                 max_pages=job.config.review.max_pages, scale=2.0)
            source_visuals.extend((f'{item.relative_path}, Originalseite {i}', page)
                                  for i, page in enumerate(pages, 1))
            for offset in range(0, len(pages), job.config.review.pages_per_batch):
                if progress:
                    progress(f'Quelleninventar: {item.relative_path}, Seiten {offset + 1}-'
                             f'{min(offset + job.config.review.pages_per_batch, len(pages))} '
                             f'von {len(pages)}')
                _require_review_turn(report, job)
                batch = pages[offset:offset + job.config.review.pages_per_batch]
                checked = _call_review(
                    session=session, previous_response_id=None,
                    pages=batch, report=report, transcript_path=transcript_path,
                    phase='inventory-source',
                    prompt=source_prompt(item, scope=scope, start=offset + 1,
                                         end=offset + len(batch)),
                )
                collected, unresolved = parse_inventory(
                    checked.output_text, source=item.relative_path,
                    start=offset + 1, end=offset + len(batch),
                    id_prefix=f's{number}p{offset + 1}',
                )
                entries.extend(collected)
                uncertainties.extend(unresolved)
        elif suffix in ('.png', '.jpg', '.jpeg', '.webp'):
            _require_review_turn(report, job)
            source_visuals.append((f'{item.relative_path}, Originalbild', item.path))
            checked = _call_review(
                session=session, previous_response_id=None,
                pages=(item.path,), report=report, transcript_path=transcript_path,
                phase='inventory-source',
                prompt=source_prompt(item, scope=scope, start=1, end=1),
            )
            collected, unresolved = parse_inventory(
                checked.output_text, source=item.relative_path, start=1, end=1,
                id_prefix=f's{number}p1',
            )
            entries.extend(collected)
            uncertainties.extend(unresolved)
        else:
            try:
                text = item.path.read_text(encoding='utf-8')
            except (UnicodeError, OSError):
                uncertainties.append(f'Quelle {item.relative_path} nicht lesbar')
                continue
            _require_review_turn(report, job)
            checked = _call_review_text(
                session=session, previous_response_id=None,
                report=report, transcript_path=transcript_path,
                phase='inventory-source',
                prompt=source_prompt(item, scope=scope, start=1, end=1, text=text),
            )
            collected, unresolved = parse_inventory(
                checked.output_text, source=item.relative_path, start=1, end=1,
                id_prefix=f's{number}p1',
            )
            entries.extend(collected)
            uncertainties.extend(unresolved)
    return entries, uncertainties, source_visuals


def _uncertainty_generation_instruction() -> str:
    return ("\nUNSICHERE SCANSTELLEN: Schreibe eine plausible, als unsicher dokumentierte "
            "Transkription in das PDF, statt [Scan unklar: ...] im sichtbaren Text. "
            "Füge unmittelbar an derselben Stelle in main.tex einen Kommentar "
            "`% [Scan unklar: Quelle/Seite/Aufgabe, Beschreibung]` hinzu. "
            "Wenn nicht einmal eine plausible Lesart existiert, gib im Dokument '?' aus. "
            "Keine unbelegten Sicherheitssignale und keine fachlichen Korrekturen. "
            "Die separate uncertainties.md wird vom Orchestrator geschrieben.\n")


def render_resume_prompt(job: ResolvedJob, prompt_dir: Path,
                         *, source_uncertainties: list[str]) -> str:
    """Fresh model/conversation/container, using bundled artifacts as authority."""
    prompt = load_prompt(prompt_dir, 'resume-job.md')
    prompt += ("\nDer neue Container hat keine alte Modellkonversation. "
               "Die unveränderten Originale, task.md und das Quelleninventar "
               "bleiben verbindlich.\nQuellunsicherheiten:\n" +
               json.dumps(source_uncertainties, ensure_ascii=False))
    return prompt


def _render_source_visuals(job: ResolvedJob, directory: Path) -> list[tuple[str, Path]]:
    visuals: list[tuple[str, Path]] = []
    sources = [item for item in job.inputs if
               item.role == InputRole.RECREATE or
               (item.role in (InputRole.CONTENT, InputRole.STATEMENT) and
                item.policy in (ContentPolicy.VERBATIM, ContentPolicy.IMMUTABLE))]
    for number, item in enumerate(sources, 1):
        if item.path.suffix.lower() == '.pdf':
            pages = render_pages(item.path, directory / f'source-{number}',
                                 max_pages=job.config.review.max_pages, scale=2.0)
            visuals.extend((f'{item.relative_path}, Originalseite {i}', page)
                           for i, page in enumerate(pages, 1))
        elif item.path.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp'):
            visuals.append((f'{item.relative_path}, Originalbild', item.path))
    return visuals


def _sync_state(session: AgentSession, result_dir: Path) -> ArtifactState:
    """Download into staging and preserve the last complete local artifact set."""
    previous = _artifact_state(result_dir)
    with tempfile.TemporaryDirectory(prefix="context-agent-sync-") as temporary:
        staging = Path(temporary)
        session.sync_result(staging)
        candidate = _artifact_state(staging)

        candidate_complete = not _missing_artifacts(candidate)
        previous_complete = not _missing_artifacts(previous)
        if candidate_complete or not previous_complete:
            if not candidate_complete:
                for name in ("main.tex", "main.pdf", "context.log", "include-snapshot.tar.gz"):
                    (result_dir / name).unlink(missing_ok=True)
            for name in ("main.tex", "main.pdf", "context.log", "include-snapshot.tar.gz"):
                source = staging / name
                if source.is_file():
                    shutil.copy2(source, result_dir / name)

    return _artifact_state(result_dir)


def _artifact_state(result_dir: Path) -> ArtifactState:
    def existing(name: str) -> Path | None:
        candidate = result_dir / name
        return candidate if candidate.is_file() else None

    return ArtifactState(
        main_tex=existing("main.tex"),
        main_pdf=existing("main.pdf"),
        context_log=existing("context.log"),
        include_snapshot=existing("include-snapshot.tar.gz"),
    )


def _missing_artifacts(state: ArtifactState) -> list[str]:
    missing: list[str] = []
    if not state.has_source:
        missing.append("main.tex fehlt")
    if not state.valid_pdf:
        missing.append("main.pdf fehlt oder ist kein gültig erkennbares PDF")
    if state.context_log is None or not state.context_log.is_file():
        missing.append("context.log fehlt")
    if state.include_snapshot is None:
        missing.append("include-snapshot.tar.gz fehlt")
    else:
        try:
            read_include_snapshot(state.include_snapshot)
        except ContextAgentError:
            missing.append("include-snapshot.tar.gz ist ungültig")
    return missing


def _may_turn(report: RunReport, job: ResolvedJob) -> bool:
    return report.agent_turns < job.config.limits.max_agent_turns


def _finish(report: RunReport, state: ArtifactState, report_path: Path) -> RunReport:
    report.finished_at = datetime.now(UTC)
    report.compile_success = not _missing_artifacts(state)
    for name, path in (
        ("main.tex", state.main_tex),
        ("main.pdf", state.main_pdf),
        ("context.log", state.context_log),
        ("include-snapshot.tar.gz", state.include_snapshot),
    ):
        if path is not None and path.is_file():
            report.artifacts[name] = str(path)
    if report.content_uncertainties or report.review_uncertainties:
        unique = list(dict.fromkeys(report.content_uncertainties + report.review_uncertainties))
        lines = ['# Unklare Stellen', '',
                 'Diese Stellen sind nicht als originalgetreu bestätigt. '
                 'Bitte Originalquelle und ConTeXt-Kommentare (`[Scan unklar:`) prüfen.', '']
        lines.extend(f'- {item}' for item in unique)
        (report_path.parent / 'uncertainties.md').write_text(
            '\n'.join(lines) + '\n', encoding='utf-8')
        report.artifacts['uncertainties.md'] = str(report_path.parent / 'uncertainties.md')
    write_report(report, report_path)
    return report
