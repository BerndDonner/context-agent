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
    NogoCheckerFailure,
    NogoFinding,
    ResolvedJob,
    RunReport,
)
from context_agent.nogos import NogoContext, findings_as_prompt, load_checkers, run_checkers
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
) -> RunReport:
    """Run one complete generation and no-go repair workflow.

    The function deliberately keeps the outer workflow small. The hosted model is responsible
    for inspecting files, compiling ConTeXt, and repairing compiler failures inside its sandbox.
    """
    original_job = load_job(job_directory)
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
        # A new attempt gets a new repair budget, but historical totals remain visible.
        old_report = stored.get('report') or {}
        report.nogo_repairs = int(old_report.get('nogo_repairs', 0))
        report.content_repairs = int(old_report.get('content_repairs', 0))
        report.visual_repairs = int(old_report.get('visual_repairs', 0))
        report.review_repairs = report.content_repairs + report.visual_repairs
        for name in ('findings', 'content_findings', 'review_findings'):
            values = old_report.get(name, [])
            setattr(report, name, [NogoFinding(**value) for value in values])
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
                             resume_result=(job.result_dir if resume else None))
            direct_files = direct_model_files(job)
            system_prompt = load_prompt(prompt_dir, "system.md")
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
                initial_prompt = render_initial_prompt(job, prompt_dir)
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

            checkers, load_failures = load_checkers(job.nogo_directory)
            report.checker_failures.extend(load_failures)
            if load_failures:
                report.errors.append("One or more no-go checkers could not be loaded.")

            nogo_repairs = 0
            content_repairs = 0
            visual_repairs = 0
            while not report.checker_failures:
                progress('Lokale No-go-Prüfung gestartet')
                assert state.main_tex is not None
                assert state.include_snapshot is not None
                # Review helpers from the *same* sandbox snapshot as main.tex.
                remote_files = read_include_snapshot(state.include_snapshot)
                include_transaction.changes(remote_files)  # validate before reviewing
                with tempfile.TemporaryDirectory(prefix="context-agent-check-includes-") as stage:
                    include_stage = Path(stage) / "include"
                    for relative, data in remote_files.items():
                        target = include_stage / relative
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(data)
                    def remote_lint(name: str) -> list[NogoFinding]:
                        if name != "dollar_math":
                            raise ContextAgentError(f"unknown remote linter: {name}")
                        if not _may_turn(report, job):
                            raise ContextAgentError("not enough agent turns for dynamic ConTeXt lint")
                        progress('Dynamischer ConTeXt-Lint im Hosted-Container gestartet')
                        payload, turn = session.run_dollar_lint(
                            max_api_calls=job.config.limits.max_agent_turns - report.agent_turns)
                        report.agent_turns += turn.api_calls
                        report.response_ids.extend(turn.raw.get('response_ids', [turn.response_id]))
                        report.add_usage(turn.usage, phase='nogo-dollar-lint', raw=turn.raw)
                        append_transcript(transcript_path, turn_number=report.agent_turns,
                                          phase='nogo-dollar-lint', turn=turn)
                        findings = [NogoFinding(**item) for item in payload['findings']]
                        progress(f'Dynamischer ConTeXt-Lint: {len(findings)} Befunde')
                        return findings

                    context = NogoContext(
                        job=job,
                        main_tex=state.main_tex,
                        main_pdf=state.main_pdf,
                        context_log=state.context_log,
                        include_override=include_stage,
                        remote_lint=remote_lint,
                    )
                    findings, runtime_failures = run_checkers(checkers, context)
                    if job.config.review.reproduction:
                        findings.extend(visible_scan_markers(state.main_tex))
                report.checker_failures.extend(runtime_failures)
                report.findings = findings
                if runtime_failures:
                    report.errors.append("One or more no-go checkers failed during execution.")
                    break
                if findings:
                    progress(f'No-go-Prüfung: {len(findings)} Verstöße')
                    if nogo_repairs >= job.config.limits.max_nogo_repairs or not _may_turn(report, job):
                        break
                    nogo_repairs += 1
                    report.nogo_repairs = nogo_repairs
                    state = repair(findings_as_prompt(findings),
                                   f'repair-nogos-{nogo_repairs}')
                    if _missing_artifacts(state):
                        report.errors.append("A no-go repair destroyed required artifacts.")
                        break
                    continue

                progress('Lokale No-go-Prüfung bestanden')
                report.review_findings = []
                report.review_uncertainties = []
                report.content_findings = []
                report.content_uncertainties = []
                if job.config.review.reproduction:
                    report.content_uncertainties = list(source_uncertainties)
                    progress('Unabhängige Inhaltsprüfung gestartet')

                    assert state.main_pdf is not None
                    with tempfile.TemporaryDirectory(prefix="context-agent-content-") as temporary:
                        output_pages = render_pages(state.main_pdf, Path(temporary),
                                                    max_pages=job.config.review.max_pages)
                        content_findings: list[NogoFinding] = []
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
                    review_findings: list[NogoFinding] = []
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
                # Uncertainty is NOT proof of fidelity. Do not change Git files.
                if report.review_uncertainties or report.content_uncertainties:
                    progress('Offene Quellunsicherheiten: manuelle Prüfung erforderlich')
                    report.status = "needs_review"
                    break
                # Do not touch Git working files before all checks succeeded.
                report.include_changes = include_transaction.apply(remote_files)
                report.status = "success"
                break

            report.compile_success = not _missing_artifacts(state)
            if report.status not in ("success", "needs_review"):
                report.status = "failed"
                if report.findings:
                    report.errors.append(f"{len(report.findings)} no-go finding(s) remain.")
                if report.review_findings:
                    report.errors.append(
                        f"{len(report.review_findings)} reproduction finding(s) remain.")
                if report.content_findings:
                    report.errors.append(
                        f"{len(report.content_findings)} content finding(s) remain.")
                if report.checker_failures:
                    report.errors.append("No-go checker failure prevents acceptance.")

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
