"""Find suspicious manual units as candidates, not confirmed violations."""
import re
from context_agent.quality_rules import QualityContext, candidate, source_without_unset_text
from context_agent.models import QualityFinding

_CANONICAL_UNIT = re.compile(r'\\unit\{(?:kiloohm|Kiloohm|KiloOhm)\}')

_PATTERNS = [
    re.compile(r'\d+(?:\{,\}\d+|\.\d+)?\s*(?:\\,)?\s*\\mathrm\s*\{(?:V|A|m|s|kg|Hz|W|Ohm|K|C)\}'),
    re.compile(r'\d+(?:\{,\}\d+|\.\d+)?\s*\^\s*\{?\\circ\}?'),
    re.compile(r'\d+(?:\{,\}\d+|\.\d+)?\s*\\%'),
    re.compile(r'\d+\s*(?:V|mA|kV|Hz|kHz|kg|km/h)\b'),
    # Bare SI spellings commonly found in transcribed measurement sheets.
    re.compile(r'(?<![\\\w])\d+(?:\{,\}\d+|[.,]\d+)?\s*(?:μV|µV|mV|kΩ|MΩ|Ω|mΩ|µA|μA|ms|us|\\%)(?![\w])'),
    re.compile(r'(?<![\\\w])\d+[.,]\d+\s*(?:V|A|W|Hz|s|K)\b'),
]

def check(context: QualityContext) -> list[QualityFinding]:
    text=context.main_tex.read_text(encoding='utf-8')
    code=source_without_unset_text(text)
    results=[]; seen=set()
    for m in _CANONICAL_UNIT.finditer(code):
        results.append(candidate('number_with_unit', text, m.start(),
            f'Einheitenalias {m.group()!r} auf \\unit{{kOhm}} vereinheitlichen',
            hint=r'\unit{kOhm} ist die kanonische Kiloohm-Schreibweise.'))
        seen.add(m.start())
    code=re.sub(r'\\unit\{[^{}]*\}', lambda m:' '*len(m.group()), code)
    for pattern in _PATTERNS:
        for m in pattern.finditer(code):
            if m.start() in seen:
                continue
            seen.add(m.start())
            results.append(candidate('number_with_unit', text, m.start(),
                 f'Manuell gesetzte Einheit/Winkel/Prozent: {m.group()!r}',
                 hint='Zahl + \\unit{...}, Winkel: \\unit{Degree}, Prozent: \\unit{Percent}.'))
    return results
