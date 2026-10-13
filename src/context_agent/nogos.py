from __future__ import annotations

import importlib.util
import sys
import traceback
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Callable, Protocol, cast

from context_agent.models import (
    NogoCheckerFailure,
    NogoFinding,
    ResolvedJob,
)


@dataclass(frozen=True)
class NogoContext:
    job: ResolvedJob
    main_tex: Path
    main_pdf: Path | None
    context_log: Path | None
    include_override: Path | None = None
    remote_lint: Callable[[str], list[NogoFinding]] | None = None

    @property
    def result_dir(self) -> Path:
        return self.job.result_dir

    @property
    def template_path(self) -> Path:
        return self.job.template_path

    @property
    def include_dir(self) -> Path:
        return self.include_override or self.job.include_dir

    def read_text(self, path: str | Path, *, encoding: str = "utf-8") -> str:
        candidate = self._resolve_allowed(path)
        return candidate.read_text(encoding=encoding)

    def read_bytes(self, path: str | Path) -> bytes:
        candidate = self._resolve_allowed(path)
        return candidate.read_bytes()

    def _resolve_allowed(self, path: str | Path) -> Path:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.job.root / candidate
        candidate = candidate.resolve()
        if self.include_override and _is_below(candidate, self.job.include_dir.resolve()):
            candidate = self.include_override / candidate.relative_to(self.job.include_dir.resolve())
        allowed_roots = (self.job.root.resolve(),)
        if self.include_override:
            allowed_roots += (self.include_override.resolve(),)
        if not any(_is_below(candidate, root) for root in allowed_roots):
            raise ValueError(f"path outside job directory: {candidate}")
        return candidate


class Checker(Protocol):
    def __call__(self, context: NogoContext) -> list[NogoFinding]: ...


@dataclass(frozen=True)
class LoadedChecker:
    name: str
    path: Path
    check: Checker


def _is_below(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _load_module(path: Path, unique_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(unique_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot create module spec for {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_checkers(directory: Path | None) -> tuple[list[LoadedChecker], list[NogoCheckerFailure]]:
    """Load mandatory packaged checkers plus optional job-specific checkers.

    Every checker uses the same regular plugin interface. Missing mandatory
    checker files are a fatal loading failure rather than a silent no-op.
    """
    builtin = Path(__file__).resolve().parent / "resources" / "nogos"
    directories = [builtin]
    if directory is not None and directory.resolve() != builtin.resolve():
        directories.append(directory)
    loaded: list[LoadedChecker] = []
    failures: list[NogoCheckerFailure] = []
    names: set[str] = set()
    for current in directories:
        if not current.is_dir():
            failures.append(NogoCheckerFailure(
                checker=str(current), message="No-go directory missing", traceback=""))
            continue
        directory_string = str(current.resolve())
        sys.path.insert(0, directory_string)
        try:
            for index, path in enumerate(sorted(current.glob("*.py"))):
                if path.name.startswith("_"):
                    continue
                if path.stem in names:
                    failures.append(NogoCheckerFailure(
                        checker=path.name, message="Duplicate no-go checker name", traceback=""))
                    continue
                try:
                    module = _load_module(path, f"context_agent_nogo_{len(loaded)}_{index}_{path.stem}")
                    check = getattr(module, "check", None)
                    if not callable(check):
                        raise TypeError("module does not export callable check(context)")
                    loaded.append(LoadedChecker(path.stem, path, cast(Checker, check)))
                    names.add(path.stem)
                except Exception as exc:
                    failures.append(NogoCheckerFailure(
                        checker=path.name, message=str(exc), traceback=traceback.format_exc()))
        finally:
            if sys.path and sys.path[0] == directory_string:
                sys.path.pop(0)
            else:
                with suppress(ValueError):
                    sys.path.remove(directory_string)
    return loaded, failures


def run_checkers(
    checkers: list[LoadedChecker], context: NogoContext
) -> tuple[list[NogoFinding], list[NogoCheckerFailure]]:
    findings: list[NogoFinding] = []
    failures: list[NogoCheckerFailure] = []

    for checker in checkers:
        try:
            raw_findings = checker.check(context)
            if not isinstance(raw_findings, list):
                raise TypeError("check(context) must return list[NogoFinding]")
            for finding in raw_findings:
                if not isinstance(finding, NogoFinding):
                    raise TypeError(
                        "checker returned an item that is not context_agent.models.NogoFinding"
                    )
                findings.append(finding)
        except Exception as exc:
            failures.append(
                NogoCheckerFailure(
                    checker=checker.name,
                    message=str(exc),
                    traceback=traceback.format_exc(),
                )
            )

    return findings, failures


def findings_as_prompt(findings: list[NogoFinding]) -> str:
    lines = [
        "Die lokale No-go-Prüfung hat folgende Verstöße gefunden.",
        "Behebe alle Befunde im bestehenden Dokument, kompiliere erneut und lasse",
        "den letzten kompilierbaren Stand nicht verloren gehen.",
        "Wörtliche und unveränderliche Eingaben dürfen dabei nicht geändert werden.",
        "",
    ]
    for index, finding in enumerate(findings, start=1):
        location = ""
        if finding.file:
            location = f" Datei: {finding.file}"
            if finding.line is not None:
                location += f", Zeile: {finding.line}"
        lines.append(f"{index}. [{finding.rule_id}]{location}")
        lines.append(f"   {finding.message}")
        if finding.repair_hint:
            lines.append(f"   Reparaturhinweis: {finding.repair_hint}")
    lines.extend(
        [
            "",
            "Erwartete Ergebnisdateien bleiben:",
            "/mnt/data/work/job/result/main.tex",
            "/mnt/data/work/job/result/main.pdf",
            "/mnt/data/work/job/result/context.log",
            "bash /mnt/data/work/runtime/collect-includes.sh /mnt/data/work/job",
        ]
    )
    return "\n".join(lines)
