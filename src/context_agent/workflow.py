from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from context_agent.bundling import build_job_bundle, direct_model_files
from context_agent.errors import ContextAgentError
from context_agent.job import load_job, prepare_result_directory
from context_agent.include_sync import IncludeTransaction, read_include_snapshot
from context_agent.models import (
    AgentTurn,
    ArtifactState,
    NogoCheckerFailure,
    NogoFinding,
    ResolvedJob,
    RunReport,
)
from context_agent.nogos import NogoContext, findings_as_prompt, load_checkers, run_checkers
from context_agent.openai_backend import AgentSession, OpenAIHostedSession
from context_agent.prompts import (
    load_prompt,
    render_initial_prompt,
    render_missing_artifacts_prompt,
)
from context_agent.report import append_transcript, write_report
from context_agent.reproduction import parse_review, render_pages, review_prompt

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
) -> RunReport:
    """Run one complete generation and no-go repair workflow.

    The function deliberately keeps the outer workflow small. The hosted model is responsible
    for inspecting files, compiling ConTeXt, and repairing compiler failures inside its sandbox.
    """
    job = load_job(job_directory)
    include_transaction = IncludeTransaction.capture(job.include_dir)
    prepare_result_directory(job.result_dir)

    resource_root = Path(__file__).resolve().parent / "resources"
    prompt_dir = (prompt_directory or resource_root / "prompts").resolve()
    runtime_dir = (runtime_directory or resource_root / "runtime").resolve()

    report = RunReport(
        status="running",
        model=job.config.model,
        started_at=datetime.now(UTC),
    )
    report_path = job.result_dir / "report.json"
    transcript_path = job.result_dir / "transcript.jsonl"
    session: AgentSession | None = None

    try:
        with tempfile.TemporaryDirectory(prefix="context-agent-") as temporary:
            bundle_path = Path(temporary) / "context-agent-job.tar.gz"
            build_job_bundle(job, bundle_path, runtime_dir)
            direct_files = direct_model_files(job)
            system_prompt = load_prompt(prompt_dir, "system.md")
            session = session_factory(job, bundle_path, direct_files, system_prompt)
            report.remote_container_id = session.container_id

            initial_prompt = render_initial_prompt(job, prompt_dir)
            turn = _call_turn(
                session=session,
                prompt=initial_prompt,
                previous_response_id=None,
                phase="initial",
                report=report,
                transcript_path=transcript_path,
            )
            state = _sync_state(session, job.result_dir)

            while _missing_artifacts(state) and _may_turn(report, job):
                prompt = render_missing_artifacts_prompt(_missing_artifacts(state), prompt_dir)
                turn = _call_turn(
                    session=session,
                    prompt=prompt,
                    previous_response_id=turn.response_id,
                    phase="repair-artifacts",
                    report=report,
                    transcript_path=transcript_path,
                )
                state = _sync_state(session, job.result_dir)

            missing = _missing_artifacts(state)
            if missing:
                report.errors.append("Missing or invalid result artifacts: " + ", ".join(missing))
                report.status = "failed"
                return _finish(report, state, report_path)

            checkers, load_failures = load_checkers(job.nogo_directory)
            report.checker_failures.extend(load_failures)
            if load_failures:
                report.errors.append("One or more no-go checkers could not be loaded.")

            nogo_repairs = 0
            review_repairs = 0
            while not report.checker_failures:
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
                    context = NogoContext(
                        job=job,
                        main_tex=state.main_tex,
                        main_pdf=state.main_pdf,
                        context_log=state.context_log,
                        include_override=include_stage,
                    )
                    findings, runtime_failures = run_checkers(checkers, context)
                report.checker_failures.extend(runtime_failures)
                report.findings = findings
                if runtime_failures:
                    report.errors.append("One or more no-go checkers failed during execution.")
                    break
                if findings:
                    if nogo_repairs >= job.config.limits.max_nogo_repairs or not _may_turn(report, job):
                        break
                    nogo_repairs += 1
                    report.nogo_repairs = nogo_repairs
                    turn = _call_turn(
                        session=session, prompt=findings_as_prompt(findings),
                        previous_response_id=turn.response_id,
                        phase=f"repair-nogos-{nogo_repairs}", report=report,
                        transcript_path=transcript_path,
                    )
                    state = _sync_state(session, job.result_dir)
                    if _missing_artifacts(state):
                        report.errors.append("A no-go repair destroyed required artifacts.")
                        break
                    continue

                report.review_findings = []
                if job.config.review.reproduction:
                    review_findings: list[NogoFinding] = []
                    with tempfile.TemporaryDirectory(prefix="context-agent-review-") as temporary:
                        assert state.main_pdf is not None
                        pages = render_pages(state.main_pdf, Path(temporary),
                                             max_pages=job.config.review.max_pages)
                        batch_size = job.config.review.pages_per_batch
                        for offset in range(0, len(pages), batch_size):
                            if not _may_turn(report, job):
                                raise ContextAgentError(
                                    "Not enough max_agent_turns to complete reproduction review")
                            batch = pages[offset:offset + batch_size]
                            prompt = review_prompt(len(pages), offset + 1, offset + len(batch),
                                                   last=offset + len(batch) == len(pages))
                            # A review turn cannot execute shell commands or edit files.
                            turn = _call_review(session=session, prompt=prompt,
                                                previous_response_id=turn.response_id,
                                                pages=batch, report=report,
                                                transcript_path=transcript_path)
                            review = parse_review(turn.output_text, start_page=offset + 1,
                                                  end_page=offset + len(batch))
                            review_findings.extend(review.findings)
                            report.review_uncertainties.extend(review.uncertainties)
                    report.review_findings = review_findings
                    if review_findings:
                        if review_repairs >= job.config.review.max_repairs or not _may_turn(report, job):
                            break
                        review_repairs += 1
                        report.review_repairs = review_repairs
                        prompt = findings_as_prompt(review_findings) + (
                            "\nBewahre ALLE Originalinhalte einschließlich gedruckter Lösungen. "
                            "Keine Verbesserungen. Erzeuge nach Kompilierung erneut "
                            "include-snapshot.tar.gz mit collect-includes.sh."
                        )
                        turn = _call_turn(
                            session=session, prompt=prompt,
                            previous_response_id=turn.response_id,
                            phase=f"repair-reproduction-{review_repairs}", report=report,
                            transcript_path=transcript_path,
                        )
                        state = _sync_state(session, job.result_dir)
                        if _missing_artifacts(state):
                            report.errors.append("A reproduction repair destroyed required artifacts.")
                            break
                        continue
                # Do not touch Git working files before all checks succeeded.
                report.include_changes = include_transaction.apply(remote_files)
                report.status = "success"
                break

            report.compile_success = not _missing_artifacts(state)
            if report.status != "success":
                report.status = "failed"
                if report.findings:
                    report.errors.append(f"{len(report.findings)} no-go finding(s) remain.")
                if report.review_findings:
                    report.errors.append(
                        f"{len(report.review_findings)} reproduction finding(s) remain.")
                if report.checker_failures:
                    report.errors.append("No-go checker failure prevents acceptance.")

            return _finish(report, state, report_path)

    except ContextAgentError as exc:
        report.status = "failed"
        report.errors.append(str(exc))
        return _finish(report, _artifact_state(job.result_dir), report_path)
    except Exception as exc:
        report.status = "failed"
        report.errors.append(f"Unexpected error: {type(exc).__name__}: {exc}")
        _finish(report, _artifact_state(job.result_dir), report_path)
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
    report.add_usage(turn.usage)
    append_transcript(
        transcript_path,
        turn_number=report.agent_turns,
        phase=phase,
        turn=turn,
    )
    return turn


def _call_review(
    *, session: AgentSession, prompt: str, previous_response_id: str,
    pages: tuple[Path, ...], report: RunReport, transcript_path: Path,
) -> AgentTurn:
    turn = session.review_pages(prompt, previous_response_id, pages)
    report.agent_turns += 1
    report.response_ids.append(turn.response_id)
    report.add_usage(turn.usage)
    append_transcript(transcript_path, turn_number=report.agent_turns,
                      phase="review-reproduction", turn=turn)
    return turn


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
    write_report(report, report_path)
    return report
