"""Reconcile runtime evidence with static quality-audit availability warnings.

Never discard genuine scan/content uncertainties or mutate preflight history.
Only a *demonstrably false* environment-availability warning is superseded.
"""
from __future__ import annotations

from pathlib import Path

from context_agent.models import QualityFinding


def reconcile_availability_warnings(
    findings: list[QualityFinding], *, pdf_compiled: bool,
    dollar_lint_ok: bool, includes: Path, references_available: bool,
) -> tuple[list[QualityFinding], list[str]]:
    """Return active findings and reasons why obsolete warnings were excluded.

    Does not remove warnings about unverified numbers, ambiguous scans, or
    unknown visual fidelity. The two patterns target false claims that named
    files or executed checks are absent (not general quality concerns).
    """
    result: list[QualityFinding] = []
    superseded: list[str] = []
    resources_ok = all((includes / name).is_file() for name in ('mymacros.mp', 'plotmod.lua'))
    for finding in findings:
        if finding.rule_id != 'dollar_math' or finding.certainty not in ('warning', 'candidate'):
            result.append(finding)
            continue
        message = finding.message.casefold()
        missing_claim = ('nicht vor' in message or 'fehlen' in message or
                         'nicht ausgeführt' in message or 'liegt nicht vor' in message)
        if not missing_claim:
            result.append(finding)
            continue
        if (resources_ok and 'mymacros.mp' in message and 'plotmod' in message and
                ('nicht vor' in message or 'fehlen' in message)):
            superseded.append('referenced_include_resources_available')
        elif (dollar_lint_ok and pdf_compiled and references_available and
              ('dollar-linter' in message or 'dollar-lint' in message) and
              ('satzlauf' in message or 'kompilierung' in message)):
            superseded.append('runtime_linter_compilation_and_reference_available')
        else:
            result.append(finding)
    return result, superseded
