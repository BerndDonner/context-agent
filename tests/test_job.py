from pathlib import Path

import pytest

from context_agent.errors import ConfigurationError
from context_agent.job import load_job


def test_load_job_resolves_files(tmp_path: Path, job_factory) -> None:  # type: ignore[no-untyped-def]
    job_root = job_factory(tmp_path)
    job = load_job(job_root)
    assert job.task_path.name == "task.md"
    assert job.template_path.name == "template.tex"
    assert job.inputs[0].role.value == "content"
    assert job.result_dir.is_dir()


def test_job_paths_may_not_escape(tmp_path: Path, job_factory) -> None:  # type: ignore[no-untyped-def]
    job_root = job_factory(tmp_path)
    config = job_root / "job.yaml"
    config.write_text(config.read_text().replace("task: task.md", "task: ../outside.md"))
    (tmp_path / "outside.md").write_text("outside")
    with pytest.raises(ConfigurationError, match="escapes"):
        load_job(job_root)
