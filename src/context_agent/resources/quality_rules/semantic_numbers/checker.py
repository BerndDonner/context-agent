"""Candidate-only number scanner; not a ConTeXt parser."""
import re
from context_agent.quality_rules import QualityContext, candidate, source_without_unset_text
from context_agent.models import QualityFinding

_NUMBERS = re.compile(r'(?<![\\\w\d])(?:-?\d+\{,\}\d+|-?\d+\.\d+|-?\d{4,})(?![\w\d])')

def check(context: QualityContext) -> list[QualityFinding]:
    text = context.main_tex.read_text(encoding='utf-8')
    code = source_without_unset_text(text)
    code = re.sub(r'\\dn\{[^{}]*\}|\\digits\{[^{}]*\}|\\unit\{[^{}]*\}',
                  lambda m: ' ' * len(m.group()), code)
    code = re.sub(r'\\startMP(?:code|page).*?\\stopMP(?:code|page)',
                  lambda m: re.sub(r'[^\n]', ' ', m.group()), code, flags=re.S)
    findings = []
    for match in _NUMBERS.finditer(code):
        value = match.group()
        line = text[text.rfind('\n', 0, match.start()) + 1:text.find('\n', match.end()) if '\n' in text[match.end():] else len(text)]
        if re.search(r'\b(?:19|20)\d\d\b', value) and re.search(r'Jahr|seit|bis|Schuljahr|SS|WS', line, re.I):
            continue
        findings.append(candidate('semantic_numbers', text, match.start(),
                                  f'Zahl {value!r}: ist \\dn erforderlich?',
                                  hint='Dezimal- oder große Zahlgrößen mit \\dn schreiben; Kalenderjahre ausnehmen.'))
    return findings
