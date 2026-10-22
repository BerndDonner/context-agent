"""Explicit, composable quality rules: descriptions, read-only checks and refinements.

Only names in job.yaml's `quality` list are loaded. A rule may have neither a
Python checker nor a deterministic refinement; its documented LLM checks and
repairs remain available. Untrusted job-supplied Python rules are executable code.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import traceback
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Callable, Protocol

import yaml

from context_agent.errors import ConfigurationError
from context_agent.models import CheckerFailure, QualityFinding, ResolvedJob


@dataclass(frozen=True)
class QualityContext:
    job: ResolvedJob
    main_tex: Path
    main_pdf: Path | None
    context_log: Path | None
    include_override: Path | None = None
    remote_lint: Callable[[str], list[QualityFinding]] | None = None

    @property
    def result_dir(self) -> Path:
        return self.job.result_dir

    @property
    def template_path(self) -> Path:
        return self.job.template_path

    @property
    def include_dir(self) -> Path:
        return self.include_override or self.job.include_dir

    def read_text(self, path: str | Path, *, encoding: str = 'utf-8') -> str:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.job.root / candidate
        candidate = candidate.resolve()
        if self.include_override and candidate.is_relative_to(self.job.include_dir.resolve()):
            candidate = self.include_override / candidate.relative_to(self.job.include_dir.resolve())
        if not (candidate.is_relative_to(self.job.root.resolve()) or
                (self.include_override and candidate.is_relative_to(self.include_override.resolve()))):
            raise ValueError(f'path outside job: {candidate}')
        return candidate.read_text(encoding=encoding)


class Checker(Protocol):
    def __call__(self, context: QualityContext) -> list[QualityFinding]: ...


@dataclass(frozen=True)
class Edit:
    """Guarded local replacement; stale or overlapping edits must never be committed."""
    rule_id: str
    path: str  # main.tex only for initial deterministic refinements
    old: str
    new: str
    offset: int
    expected_sha256: str

    def as_dict(self) -> dict[str, str | int]:
        return vars(self).copy()


@dataclass(frozen=True)
class ResourceSpec:
    source: Path
    target: str
    macro: str
    include: str


@dataclass(frozen=True)
class QualityRule:
    id: str
    root: Path
    description: str
    scope: str
    exceptions: str
    generation: str
    refinement: str
    verification: str
    check: Checker | None
    propose_edits: Callable[[QualityContext, list[QualityFinding]], list[Edit]] | None
    resources: tuple[ResourceSpec, ...]

    def llm_description(self) -> str:
        return (f'{self.id}\nZiel: {self.description}\nGeltungsbereich: {self.scope}\n'
                f'Ausnahmen: {self.exceptions}\nGenerierung: {self.generation}\n'
                f'Reparatur: {self.refinement}\nPrüfung: {self.verification}')


def _module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ConfigurationError(f'cannot load quality-rule module {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_rules(job: ResolvedJob) -> tuple[QualityRule, ...]:
    builtin = Path(__file__).resolve().parent / 'resources' / 'quality_rules'
    rules: list[QualityRule] = []
    for id in job.config.quality:
        builtin_root = builtin / id
        custom_root = job.quality_directory / id if job.quality_directory else None
        # Overrides are explicit: the job-selected id must exist exactly once.
        root = custom_root if custom_root and custom_root.is_dir() else builtin_root
        if not root.is_dir():
            raise ConfigurationError(f'unknown quality rule: {id}')
        meta = root / 'rule.yaml'
        if not meta.is_file():
            raise ConfigurationError(f'quality rule {id} has no rule.yaml')
        data = yaml.safe_load(meta.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or data.get('id') != id:
            raise ConfigurationError(f'quality rule metadata/id mismatch: {meta}')
        keys = ('description', 'scope', 'exceptions', 'generation', 'refinement', 'verification')
        if any(not isinstance(data.get(key), str) or not data[key].strip() for key in keys):
            raise ConfigurationError(f'quality rule {id} has missing description fields')
        checker: Checker | None = None
        refinements = None
        if (root / 'checker.py').is_file():
            checker = getattr(_module(root / 'checker.py', f'context_agent_checker_{id}'), 'check', None)
            if not callable(checker):
                raise ConfigurationError(f'quality rule {id} missing callable check')
        if (root / 'refinement.py').is_file():
            refinements = getattr(_module(root / 'refinement.py', f'context_agent_refinement_{id}'), 'propose_edits', None)
            if not callable(refinements):
                raise ConfigurationError(f'quality rule {id} missing callable propose_edits')
        resources_list: list[ResourceSpec] = []
        for resource in data.get('resources', []):
            if not isinstance(resource, dict) or set(resource) != {'provider','path','target','macro','include'}:
                raise ConfigurationError(f'invalid resource declaration in {id}')
            provider = resource['provider']
            path = resource['path']
            target = resource['target']
            if not isinstance(provider,str) or not isinstance(path,str) or not isinstance(target,str):
                raise ConfigurationError(f'invalid resource strings in {id}')
            source_root = ((job.quality_directory / provider) if job.quality_directory and
                           (job.quality_directory / provider).is_dir() else builtin / provider)
            source = (source_root / 'resources' / path).resolve()
            if (not source.is_relative_to((source_root / 'resources').resolve()) or
                not source.is_file() or target.startswith('/') or '..' in Path(target).parts or
                not target.startswith('quality-rules/')):
                raise ConfigurationError(f'unsafe/missing resource dependency in {id}: {path}')
            resources_list.append(ResourceSpec(source,target,str(resource['macro']),
                                                str(resource['include'])))
        resources = tuple(resources_list)
        rules.append(QualityRule(id, root, *(data[key] for key in keys),
                                 checker, refinements, resources))
    return tuple(rules)


def run_checkers(rules: tuple[QualityRule, ...], context: QualityContext) -> tuple[list[QualityFinding], list[CheckerFailure]]:
    found: list[QualityFinding] = []
    failures: list[CheckerFailure] = []
    for rule in rules:
        if rule.check is None:
            continue
        try:
            candidates = rule.check(context)
            if not isinstance(candidates, list) or any(not isinstance(f, QualityFinding) or f.rule_id != rule.id for f in candidates):
                raise TypeError(f'{rule.id}.check must return QualityFinding list with matching rule_id')
            found.extend(candidates)
        except Exception as exc:
            failures.append(CheckerFailure(checker=rule.id, message=str(exc), traceback=traceback.format_exc()))
    return found, failures


def findings_as_prompt(findings: list[QualityFinding], rules: tuple[QualityRule, ...] = ()) -> str:
    descriptions = {rule.id: rule for rule in rules}
    lines = ['Bearbeite nur die explizit ausgewählten Qualitätsregeln, unter Erhaltung des Originalauftrags.',
             'Kompiliere neu und erzeuge nach jeder Änderung include-snapshot.tar.gz.',
             'Unsichere Kandidaten erst prüfen; keine blind durchgeführten Textersetzungen.', '']
    for index, finding in enumerate(findings, 1):
        location = f' ({finding.file}:{finding.line})' if finding.file else ''
        lines.append(f'{index}. [{finding.rule_id}] {finding.certainty}/{finding.severity}{location}: {finding.message}')
        if finding.repair_hint:
            lines.append('   Vorschlag: ' + finding.repair_hint)
        if finding.rule_id in descriptions:
            lines.append('   Refinement: ' + descriptions[finding.rule_id].refinement)
    return '\n'.join(lines)


def check_edits(text: str, edits: list[Edit]) -> str:
    """Atomic source-level validation; no stale, conflicting or overlapping edits."""
    digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
    for edit in edits:
        if edit.path != 'main.tex' or edit.expected_sha256 != digest:
            raise ValueError('stale edit or unsupported edit target')
        if text[edit.offset:edit.offset + len(edit.old)] != edit.old:
            raise ValueError('edit expected source mismatch')
    ordered = sorted(edits, key=lambda e: e.offset)
    for prev, nxt in zip(ordered, ordered[1:]):
        if prev.offset + len(prev.old) > nxt.offset:
            raise ValueError('overlapping edits')
    for edit in reversed(ordered):
        text = text[:edit.offset] + edit.new + text[edit.offset + len(edit.old):]
    return text


def source_without_unset_text(text: str, *, preserve_mp: bool = False) -> str:
    """Conservative candidate scanner: exclude preamble, comments and literal code.

    This is not a TeX interpreter: results are only candidates, not proof.
    """
    start = re.search(r'\\starttext\b', text)
    if start:
        text = ' ' * start.end() + text[start.end():]
    literal = r'typing|TEX|LUA|luacode|luaparameters|buffer' + ('' if preserve_mp else '|MPcode|MPpage')
    for match in list(re.finditer(r'\\start(?:' + literal + r')\b.*?\\stop(?:' + literal + r')\b', text, re.S)):
        text = text[:match.start()] + re.sub(r'[^\n]', ' ', match.group()) + text[match.end():]
    text = re.sub(r'\\type\{[^{}]*\}|\\type\|[^|]*\|', lambda m: ' ' * len(m.group()), text)
    text = re.sub(r'(?<!\\)%[^\n]*', lambda m: ' ' * len(m.group()), text)
    return text


def candidate(rule: str, text: str, offset: int, message: str, *, hint: str = '', confidence: float = .65) -> QualityFinding:
    return QualityFinding(rule_id=rule, message=message, file='main.tex',
                          line=text.count('\n', 0, offset) + 1, repair_hint=hint,
                          confidence=confidence, certainty='candidate', severity='warning')
