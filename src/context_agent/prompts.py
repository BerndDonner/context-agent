from __future__ import annotations

from pathlib import Path

from context_agent.models import ResolvedJob


def load_prompt(prompt_dir: Path, name: str) -> str:
    return (prompt_dir / name).read_text(encoding="utf-8")


def render_initial_prompt(job: ResolvedJob, prompt_dir: Path) -> str:
    template = load_prompt(prompt_dir, "initial-job.md")
    attachments = []
    for item in job.inputs:
        attachments.append(
            f"- {item.relative_path}: Rolle={item.role.value}, Policy={item.policy.value}"
        )
    for path in job.references:
        attachments.append(f"- {path.relative_to(job.root).as_posix()}: Referenz")

    return template.format(
        task_path=job.config.task,
        template_path=job.config.template.path,
        attachments="\n".join(attachments) if attachments else "- keine",
    )


def render_missing_artifacts_prompt(missing: list[str], prompt_dir: Path) -> str:
    template = load_prompt(prompt_dir, "repair-missing-artifacts.md")
    return template.format(missing="\n".join(f"- {item}" for item in missing))
