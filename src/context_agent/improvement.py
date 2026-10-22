"""Evidence-oriented protection of numerical content in ``mode: improve``.

Compare quantities *in their changed source regions*, not unordered inventories
of the entire file. This recognizes TeX formatting aliases without treating a
new value, changed sign or swapped unit as an innocent normalization. It is not
an arbitrary TeX evaluator: uncertain constructions require explicit approval
and independent requirements review.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher, unified_diff
from collections.abc import Mapping, Sequence
import re

_DN = re.compile(r'\\+dn\s*\{\s*([-+]?\d+(?:[.,]\d+)?)\s*\}')
_BRACES = re.compile(r'(\d+)\s*\{,\}\s*(\d+)')
# A TeX control-space after a comma is ambiguous unless explicitly resolved.
_NUMBER = re.compile(
    r'(?<![\w\\])(?P<sign>[+-]?\s*)(?P<whole>\d+)'
    r'(?:(?P<sep>\{,\}|[.,]|,\s*\\\s+)(?P<fract>\s*\d+))?'
)

# Explicit spelling aliases only. No automatic SI conversion: 1000 mV is not
# silently identified with 1 V, and a prefix change is always conspicuous.
_UNIT_ALIASES = {
    '%': '%', 'Percent': '%', 'Degree': 'deg', '°': 'deg',
    'V': 'V', 'Volt': 'V', 'mV': 'mV', 'MilliVolt': 'mV',
    'kV': 'kV', 'KiloVolt': 'kV',
    'uV': 'uV', 'µV': 'uV', 'μV': 'uV', 'MicroVolt': 'uV',
    'microvolt': 'uV', 'mu V': 'uV',
    'A': 'A', 'Ampere': 'A', 'mA': 'mA', 'MilliAmpere': 'mA',
    'Ω': 'Ohm', 'Ohm': 'Ohm', 'kΩ': 'kOhm', 'kOhm': 'kOhm',
    'KiloOhm': 'kOhm', 'Kiloohm': 'kOhm', 'kiloohm': 'kOhm',
    'Hz': 'Hz', 'Hertz': 'Hz', 'kHz': 'kHz', 'KiloHertz': 'kHz',
    's': 's', 'Second': 's', 'ms': 'ms', 'MilliSecond': 'ms',
    'min': 'min', 'Minute': 'min', 'day': 'day', 'days': 'day',
    'Tag': 'day', 'Tage': 'day',
}
_RAW_UNIT = '|'.join(re.escape(u) for u in sorted(_UNIT_ALIASES, key=len, reverse=True))
_SPACE = r'(?:[ \t]|\\,|\\thinspace|\\[ ]|~)*'
_UNIT = re.compile(
    _SPACE + r'(?:\\+unit\s*\{(?P<unit>[^{}]+)\}'
    r'|(?P<kohm>\\+(?:mathrm|text)\{k\}\s*\\Omega)'
    r'|(?P<hyphenk>-kΩ)'
    r'|\\+(?:mathrm|text)\s*\{(?P<rm>[^{}]+)\}'
    r'|(?P<mu>\\m\s*\{\\mu\}\s*V|\\mu\s*V)'
    r'|(?P<omega>\\+Omega)'
    r'|(?P<percent>\\+%)'
    r'|(?P<raw>' + _RAW_UNIT + r')(?![A-Za-z0-9_]))'
)


@dataclass(frozen=True)
class Quantity:
    number: str
    unit: str | None


def _units(name: str) -> str | None:
    name = name.strip()
    return _UNIT_ALIASES.get(name)


def _semantic_quantities(source: str) -> list[Quantity]:
    source = _DN.sub(lambda m: m.group(1), source)
    source = _BRACES.sub(r'\1.\2', source)
    result: list[Quantity] = []
    for match in _NUMBER.finditer(source):
        raw_sign = match.group('sign').strip()
        whole = match.group('whole')
        sep = match.group('sep')
        fraction = match.group('fract')
        if fraction is None:
            number = whole
        elif sep is not None and '\\' in sep:
            # Don't guess what a separated comma means. It is not an ordinary
            # decimal number until an externally approved resolution exists.
            number = 'ambiguous:' + whole + ',' + fraction.strip()
        else:
            number = whole + '.' + fraction.strip()
        if not number.startswith('ambiguous:'):
            try:
                number = str(Decimal((raw_sign or '') + number).normalize())
            except InvalidOperation:
                number = 'invalid:' + number
        unit_match = _UNIT.match(source, match.end())
        unit = None
        if unit_match is not None:
            group = unit_match.groupdict()
            if group['mu']:
                unit = 'uV'
            elif group['kohm'] or group['hyphenk']:
                unit = 'kOhm'
            elif group['omega']:
                unit = 'Ohm'
            elif group['percent']:
                unit = '%'
            else:
                spelling = group['unit'] or group['rm'] or group['raw']
                unit = _units(spelling) if spelling is not None else None
                if spelling is not None and unit is None:
                    unit = 'unknown:' + spelling.strip()
        result.append(Quantity(number, unit))
    return result


def _changed_regions(original: str, updated: str) -> list[tuple[int, str, str]]:
    before, after = original.splitlines(keepends=True), updated.splitlines(keepends=True)
    result = []
    for op, i, j, k, l in SequenceMatcher(
            None, before, after, autojunk=False).get_opcodes():
        if op != 'equal':
            result.append((i + 1, ''.join(before[i:j]), ''.join(after[k:l])))
    return result


def _apply_approved_resolutions(source: str, destination: str, start_line: int,
                                approvals: Sequence[Mapping[str, object]] | None) -> str:
    """Make only *explicitly approved* reference resolutions comparable.

    The workflow validates the approval manifest and reference before calling.
    Each exact pair must be present in the changed region; no fuzzy matching.
    """
    for approval in approvals or ():
        previous, replacement = approval.get('before'), approval.get('after')
        source_line = approval.get('source_line')
        lines = source.splitlines()
        anchored = (type(source_line) is int and
                    start_line <= source_line < start_line + len(lines) and
                    isinstance(previous, str) and
                    previous in lines[source_line - start_line])
        target_lines = destination.splitlines()
        if (anchored and isinstance(replacement, str) and
                (replacement in target_lines[source_line - start_line]
                 if len(target_lines) == len(lines) else replacement in destination)):
            source = source.replace(previous, replacement, 1)
    return source


def improvement_guard(original: str, updated: str, *,
                      approved_resolutions: Sequence[Mapping[str, object]] | None = None) -> list[str]:
    """Conservatively reject changed values/signs/units in modified passages.

    Approval manifests authorize exact source spellings, not arbitrary number
    changes. The independent requirements reviewer still checks document meaning.
    """
    problems: list[str] = []
    for index, (start_line, old, new) in enumerate(_changed_regions(original, updated), 1):
        protected_old = _apply_approved_resolutions(old, new, start_line, approved_resolutions)
        previous = _semantic_quantities(protected_old)
        current = _semantic_quantities(new)
        if previous != current:
            problems.append(f'Changed region {index}: protected quantities differ: '
                            f'before={previous!r}; after={current!r}')
    return problems



@dataclass(frozen=True)
class PartialCandidate:
    """Only the changes that independently pass the original-content guard.

    The returned text is a *candidate*, not an accepted document: it must be
    compiled and independently requirements/quality reviewed before promotion.
    """

    source: str
    included_regions: int
    excluded_regions: int


def isolate_safe_changes(original: str, accepted: str, candidate: str, *,
                         approved_resolutions: Sequence[Mapping[str, object]] | None = None,
                         ) -> PartialCandidate:
    """Select independent changed lines without silently authorizing ambiguities.

    Align the candidate to the last protected revision. Equal-sized replace
    runs are broken into single lines (a bad OCR value cannot contaminate the
    neighboring unit replacements). Insertions/deletions are indivisible.
    Every inclusion is re-checked against the *original* source, rather than
    only the most recent accepted text. Never alter the input source itself.
    """
    before = accepted.splitlines(keepends=True)
    after = candidate.splitlines(keepends=True)
    choices: list[tuple[int, int, list[str]]] = []
    for op, i, j, k, l in SequenceMatcher(None, before, after,
                                         autojunk=False).get_opcodes():
        if op == 'equal':
            continue
        if op == 'replace' and j - i == l - k:
            choices.extend((i + n, i + n + 1, [after[k + n]])
                           for n in range(j - i))
        else:
            choices.append((i, j, after[k:l]))

    def assemble(chosen: list[tuple[int, int, list[str]]]) -> str:
        lines = before.copy()
        for start, end, replacement in reversed(chosen):
            lines[start:end] = replacement
        return ''.join(lines)

    selected: list[tuple[int, int, list[str]]] = []
    for choice in choices:
        proposal = assemble(selected + [choice])
        if not improvement_guard(original, proposal,
                                 approved_resolutions=approved_resolutions):
            selected.append(choice)
    safe = assemble(selected)
    assert not improvement_guard(original, safe,
                                 approved_resolutions=approved_resolutions)
    return PartialCandidate(safe, len(selected), len(choices) - len(selected))


def guarded_source_replacement(current: str, replacement: str) -> list[dict[str, object]]:
    """A single optimistic edit for the existing SHA-verified Hosted transport."""
    return [{'rule_id': 'partial_salvage', 'path': 'main.tex', 'offset': 0, 'old': current, 'new': replacement,
             'expected_sha256': hashlib.sha256(current.encode('utf-8')).hexdigest()}]


def improvement_diff(original: str, updated: str, *, max_lines: int = 500) -> str:
    lines = list(unified_diff(original.splitlines(), updated.splitlines(),
                              fromfile='source/main.tex', tofile='result/main.tex',
                              lineterm='', n=3))
    excerpt = lines[:max_lines]
    if len(lines) > max_lines:
        excerpt.append(f'... truncated {len(lines) - max_lines} diff lines')
    return '\n'.join(excerpt) or '(unchanged)'
