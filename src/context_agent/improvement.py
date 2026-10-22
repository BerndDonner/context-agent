"""Protected-source comparisons for improve jobs (conservative, not a TeX parser).

The numeric guard is deliberately fail-closed for unexplained changes in numeric
literal inventory. This is NOT a semantic-equivalence proof: LLM requirements
validation must check formula meaning, units, indices, scope and authorized edits.
"""
from __future__ import annotations

from collections import Counter
from difflib import unified_diff
import re

_NUM = re.compile(r'(?<![\w\\])[-+]?(?:\d+\s*\{,\}\s*\d+|\d+[.,]\d+|\d+)(?!\w)')


def _numbers(tex: str) -> Counter[str]:
    # Rewrite ConTeXt decimal braces to one textual number, preserving value.
    normalized = re.sub(r'(\d+)\s*\{,\}\s*(\d+)', r'\1.\2', tex)
    # Do not count arbitrary digits inside TeX commands or names (e.g. \foo2).
    found = []
    for match in _NUM.finditer(normalized):
        value = match.group().replace(',', '.').replace(' ', '')
        # Numeric equality is decimal exact without floating-point rounding.
        from decimal import Decimal, InvalidOperation
        try:
            value = str(Decimal(value).normalize())
        except InvalidOperation:
            pass
        found.append(value)
    return Counter(found)


def improvement_guard(original: str, updated: str) -> list[str]:
    """Detect changed literal number inventory (keeps repeats, ignores formatting).

    Does not authorize changed values merely because a user might want such edits:
    future content-editing tasks need an explicit policy and separate proof.
    """
    before, after = _numbers(original), _numbers(updated)
    missing = before - after
    added = after - before
    results = []
    if missing:
        results.append('Original numeric literals missing: ' + str(dict(missing)))
    if added:
        results.append('New numeric literals: ' + str(dict(added)))
    return results


def improvement_diff(original: str, updated: str, *, max_lines: int = 500) -> str:
    lines = list(unified_diff(original.splitlines(), updated.splitlines(),
                              fromfile='source/main.tex', tofile='result/main.tex',
                              lineterm='', n=3))
    excerpt = lines[:max_lines]
    if len(lines) > max_lines:
        excerpt.append(f'... truncated {len(lines) - max_lines} diff lines')
    return '\n'.join(excerpt) or '(unchanged)'
