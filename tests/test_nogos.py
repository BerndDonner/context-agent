from pathlib import Path

from context_agent.job import load_job
from context_agent.nogos import NogoContext, load_checkers, run_checkers


def test_dynamic_nogo_checker(tmp_path: Path, job_factory) -> None:  # type: ignore[no-untyped-def]
    job_root = job_factory(tmp_path, nogo_directory="nogos")
    directory = job_root / "nogos"
    directory.mkdir()
    (directory / "bad_word.py").write_text(
        """
from context_agent.models import NogoFinding

def check(context):
    text = context.main_tex.read_text(encoding='utf-8')
    if 'BAD' in text:
        return [NogoFinding(rule_id='bad-word', message='BAD gefunden')]
    return []
""",
        encoding="utf-8",
    )
    result = job_root / "result"
    main_tex = result / "main.tex"
    main_tex.write_text("BAD", encoding="utf-8")
    job = load_job(job_root)
    checkers, failures = load_checkers(job.nogo_directory)
    assert not failures
    findings, failures = run_checkers(
        checkers,
        NogoContext(job=job, main_tex=main_tex, main_pdf=None, context_log=None),
    )
    assert not failures
    assert [finding.rule_id for finding in findings] == ["bad-word"]
