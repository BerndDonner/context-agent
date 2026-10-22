"""Conservative numerical and unit regression checks for ``mode: improve``.

Exact decimal values (not binary floats) are compared independently from known
physical units.  This is not a TeX parser or a proof of document equivalence:
unknown expressions still require the independent requirements review.
"""
from __future__ import annotations

from collections import Counter
from decimal import Decimal
from difflib import unified_diff
import re

# A digit directly before a physical unit (``200Ω`` or ``7,5V``) is a
# complete number.  Do not require a word boundary *after* the number.
# A leading letter/backslash excludes indices and control-sequence names.
_NUM = re.compile(r'(?<![\w\\])[-+]?(?:\d+\s*\{,\}\s*\d+|\d+[.,]\d+|\d+)(?!\d)')
_DN = re.compile(r'\\+dn\s*\{\s*([-+]?(?:\d+(?:[.,]\d+)?))\s*\}')
_DECIMAL_BRACES = re.compile(r'(\d+)\s*\{,\}\s*(\d+)')
# Only known units are compared; arbitrary textual suffixes are not units.
_UNIT_NAMES = {
    '%': '%', 'Percent': '%', 'Degree': 'deg', '°': 'deg',
    'V': 'V', 'Volt': 'V', 'mV': 'mV', 'MilliVolt': 'mV',
    'kV': 'kV', 'KiloVolt': 'kV', 'uV': 'uV', 'MicroVolt': 'uV',
    'µV': 'uV', 'μV': 'uV', 'KiloOhm': 'kOhm',
    'A': 'A', 'Ampere': 'A', 'mA': 'mA', 'MilliAmpere': 'mA',
    'Ω': 'Ohm', 'Ohm': 'Ohm', 'kΩ': 'kOhm', 'kOhm': 'kOhm',
    'Hz': 'Hz', 'Hertz': 'Hz', 'kHz': 'kHz', 'KiloHertz': 'kHz',
    's': 's', 'Second': 's', 'ms': 'ms', 'MilliSecond': 'ms',
    'min': 'min', 'Minute': 'min',
}
_UNIT_PART = '|'.join(re.escape(key) for key in sorted(_UNIT_NAMES, key=len, reverse=True))
# The permitted spacing is typographic spacing, not arbitrary TeX code.
_SPACING = r'(?:[ \t]|\\+,|\\+thinspace|~)*'
_UNIT = re.compile(
    _SPACING + r'(?:\\+unit\s*\{\s*(' + _UNIT_PART + r')\s*\}'
    + r'|\\+mathrm\s*\{\s*(' + _UNIT_PART + r')\s*\}'
    + r'|(\\+%)|(\\+m\s*\{\s*\\+mu\s*\}\s*V)'
    + r'|(' + _UNIT_PART + r')(?![A-Za-z0-9_]))'
)


def _normalized_source(tex: str) -> str:
    # Keep command wrapping out of the numerical comparison.  The original
    # source itself is never modified by this normalisation.
    tex = _DN.sub(lambda m: m.group(1), tex)
    return _DECIMAL_BRACES.sub(r'\1.\2', tex)


def _decimal(number: str) -> str:
    return str(Decimal(number.replace(',', '.').replace(' ', '')).normalize())


def _numbers_and_units(tex: str) -> tuple[Counter[str], Counter[tuple[str, str]]]:
    normalized = _normalized_source(tex)
    values: Counter[str] = Counter()
    units: Counter[tuple[str, str]] = Counter()
    for match in _NUM.finditer(normalized):
        value = _decimal(match.group())
        values[value] += 1
        unit = _UNIT.match(normalized, match.end())
        if unit is not None:
            unit_name = next((group for group in unit.groups() if group), None)
            if unit_name is not None:
                canonical = ('uV' if unit_name.startswith('\\m') else
                             _UNIT_NAMES.get(unit_name, '%'))
                units[(value, canonical)] += 1
    return values, units


def improvement_guard(original: str, updated: str) -> list[str]:
    """Reject changed numeric values or changed *recognized* physical units.

    Unrecognized unit syntax does not authorize a conversion: it is checked by
    the independent requirements audit. Values in protected source remain
    exact, including repeated values and signs.
    """
    before, before_units = _numbers_and_units(original)
    after, after_units = _numbers_and_units(updated)
    results: list[str] = []
    if before - after:
        results.append('Original numeric literals missing: ' + str(dict(before - after)))
    if after - before:
        results.append('New numeric literals: ' + str(dict(after - before)))
    if before_units != after_units:
        results.append('Recognized quantity units changed: missing=' +
                       str(dict(before_units - after_units)) + ' new=' +
                       str(dict(after_units - before_units)))
    return results


def improvement_diff(original: str, updated: str, *, max_lines: int = 500) -> str:
    lines = list(unified_diff(original.splitlines(), updated.splitlines(),
                              fromfile='source/main.tex', tofile='result/main.tex',
                              lineterm='', n=3))
    excerpt = lines[:max_lines]
    if len(lines) > max_lines:
        excerpt.append(f'... truncated {len(lines) - max_lines} diff lines')
    return '\n'.join(excerpt) or '(unchanged)'
