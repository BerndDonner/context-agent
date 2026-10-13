from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class InputRole(StrEnum):
    STATEMENT = "statement"
    RECREATE = "recreate"
    CONTENT = "content"
    REFERENCE = "reference"


class ContentPolicy(StrEnum):
    VERBATIM = "verbatim"
    IMMUTABLE = "immutable"
    EDITABLE = "editable"
    GUIDANCE = "guidance"


class TemplateSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str


class InputSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    role: InputRole
    policy: ContentPolicy


class RuntimeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context_archive: str
    memory_limit: Literal["1g", "4g", "16g", "64g"] = "4g"
    keep_remote: bool = False


class LimitsSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_agent_turns: int = Field(default=6, ge=1, le=20)
    max_nogo_repairs: int = Field(default=3, ge=0, le=20)
    timeout_seconds: int = Field(default=900, ge=60, le=3600)
    max_output_tokens: int = Field(default=12000, ge=1000, le=100000)


class ReasoningSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Omission means "use the selected model's own default".
    effort: Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"] | None = None


class ProcessingSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # "auto" preserves historical behavior (API/project decides the service tier).
    # "batch" is recognized explicitly so we can reject unsafe combinations.
    mode: Literal["auto", "standard", "flex", "batch"] = "auto"


class ReviewSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Disabled for jobs that create new content rather than reproduce a reference.
    reproduction: bool = False
    max_repairs: int = Field(default=2, ge=0, le=10)
    max_pages: int = Field(default=40, ge=1, le=200)
    pages_per_batch: int = Field(default=4, ge=1, le=8)


class JobConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    task: str = "task.md"
    reasoning: ReasoningSpec = Field(default_factory=ReasoningSpec)
    processing: ProcessingSpec = Field(default_factory=ProcessingSpec)
    template: TemplateSpec
    inputs: list[InputSpec] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    runtime: RuntimeSpec
    limits: LimitsSpec = Field(default_factory=LimitsSpec)
    review: ReviewSpec = Field(default_factory=ReviewSpec)
    nogo_directory: str | None = None

    @model_validator(mode="after")
    def reject_incompatible_batch(self) -> "JobConfig":
        if self.model == "gpt-6.1-sol" and self.reasoning.effort in ("none", "minimal"):
            raise ValueError(
                "gpt-6.1-sol requires reasoning.effort low, medium, high, xhigh, or max"
            )
        if self.processing.mode == "batch":
            raise ValueError(
                "processing.mode=batch is not supported by the interactive Hosted-Shell "
                "workflow (container lifetime and sequential repair/review turns). "
                "Use processing.mode=flex for the same 50% token discount, or "
                "processing.mode=standard for standard latency."
            )
        return self

    @field_validator("model", "task")
    @classmethod
    def non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value


@dataclass(frozen=True)
class ResolvedInput:
    path: Path
    relative_path: str
    role: InputRole
    policy: ContentPolicy


@dataclass(frozen=True)
class ResolvedJob:
    root: Path
    config_path: Path
    config: JobConfig
    task_path: Path
    template_path: Path
    inputs: tuple[ResolvedInput, ...]
    references: tuple[Path, ...]
    include_dir: Path
    result_dir: Path
    context_archive: Path
    nogo_directory: Path | None


@dataclass(frozen=True)
class NogoFinding:
    rule_id: str
    message: str
    file: str | None = None
    line: int | None = None
    repair_hint: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "message": self.message,
            "file": self.file,
            "line": self.line,
            "repair_hint": self.repair_hint,
        }


@dataclass(frozen=True)
class NogoCheckerFailure:
    checker: str
    message: str
    traceback: str

    def as_dict(self) -> dict[str, str]:
        return {
            "checker": self.checker,
            "message": self.message,
            "traceback": self.traceback,
        }


@dataclass(frozen=True)
class AgentTurn:
    response_id: str
    status: str
    output_text: str
    raw: dict[str, Any]
    usage: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ArtifactState:
    main_tex: Path | None
    main_pdf: Path | None
    context_log: Path | None
    include_snapshot: Path | None = None

    @property
    def valid_pdf(self) -> bool:
        if self.main_pdf is None or not self.main_pdf.is_file():
            return False
        try:
            with self.main_pdf.open("rb") as stream:
                return stream.read(5) == b"%PDF-"
        except OSError:
            return False

    @property
    def has_source(self) -> bool:
        return self.main_tex is not None and self.main_tex.is_file()


@dataclass
class RunReport:
    status: str
    model: str
    started_at: datetime
    reasoning_effort: str | None = None
    processing_mode: str = "auto"
    finished_at: datetime | None = None
    agent_turns: int = 0
    nogo_repairs: int = 0
    review_repairs: int = 0
    review_findings: list[NogoFinding] = field(default_factory=list)
    review_uncertainties: list[str] = field(default_factory=list)
    include_changes: list[str] = field(default_factory=list)
    response_ids: list[str] = field(default_factory=list)
    observed_service_tiers: list[str] = field(default_factory=list)
    compile_success: bool = False
    findings: list[NogoFinding] = field(default_factory=list)
    checker_failures: list[NogoCheckerFailure] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    remote_container_id: str | None = None
    artifacts: dict[str, str] = field(default_factory=dict)

    def add_usage(self, usage: dict[str, Any]) -> None:
        for key in ("input_tokens", "output_tokens", "total_tokens"):
            value = usage.get(key)
            if isinstance(value, int):
                self.usage[key] = self.usage.get(key, 0) + value

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "model": self.model,
            "reasoning_effort": self.reasoning_effort,
            "processing_mode": self.processing_mode,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "agent_turns": self.agent_turns,
            "nogo_repairs": self.nogo_repairs,
            "review_repairs": self.review_repairs,
            "review_findings": [f.as_dict() for f in self.review_findings],
            "review_uncertainties": self.review_uncertainties,
            "include_changes": self.include_changes,
            "response_ids": self.response_ids,
            "observed_service_tiers": self.observed_service_tiers,
            "compile_success": self.compile_success,
            "findings": [finding.as_dict() for finding in self.findings],
            "checker_failures": [failure.as_dict() for failure in self.checker_failures],
            "errors": self.errors,
            "usage": self.usage,
            "remote_container_id": self.remote_container_id,
            "artifacts": self.artifacts,
        }
