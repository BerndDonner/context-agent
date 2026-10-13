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


def test_batch_mode_rejected_early_with_flex_advice(tmp_path: Path, job_factory) -> None:  # type: ignore[no-untyped-def]
    root = job_factory(tmp_path)
    yaml_path = root / "job.yaml"
    yaml_path.write_text(yaml_path.read_text() + "\nprocessing:\n  mode: batch\n")
    with pytest.raises(ConfigurationError, match="processing.mode=flex"):
        load_job(root)


def test_gpt_6_1_sol_invalid_effort_is_rejected(tmp_path: Path, job_factory) -> None:  # type: ignore[no-untyped-def]
    root = job_factory(tmp_path)
    yaml_path = root / "job.yaml"
    yaml_path.write_text(
        yaml_path.read_text().replace(
            "model: test-model", "model: gpt-6.1-sol\nreasoning:\n  effort: minimal"
        )
    )
    with pytest.raises(ConfigurationError, match="requires reasoning.effort"):
        load_job(root)


def test_new_job_configuration_defaults_preserve_legacy_behavior(tmp_path: Path, job_factory) -> None:  # type: ignore[no-untyped-def]
    job = load_job(job_factory(tmp_path))
    assert job.config.reasoning.effort is None
    assert job.config.processing.mode == "auto"
