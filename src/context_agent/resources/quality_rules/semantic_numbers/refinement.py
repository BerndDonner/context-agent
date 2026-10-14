"""Safe literal fixes; candidates involving meaning, years or units go to the LLM."""
import hashlib
import re
from context_agent.quality_rules import Edit, QualityContext, source_without_unset_text
from context_agent.models import QualityFinding

_MANUAL_DECIMAL = re.compile(r'(?<![\\\w\d])(-?\d+)\{,\}(\d+)(?![\w\d])')

def propose_edits(context: QualityContext, findings: list[QualityFinding]) -> list[Edit]:
    text = context.main_tex.read_text(encoding='utf-8')
    mask = source_without_unset_text(text)
    mask = re.sub(r'\\dn\{[^{}]*\}|\\digits\{[^{}]*\}', lambda m: ' '*len(m.group()), mask)
    digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
    reported_lines = {f.line for f in findings if f.rule_id == 'semantic_numbers'}
    edits = []
    for match in _MANUAL_DECIMAL.finditer(mask):
        if text.count('\n', 0, match.start()) + 1 not in reported_lines:
            continue
        replacement = f'\\dn{{{match[1]}.{match[2]}}}'
        edits.append(Edit('semantic_numbers', 'main.tex', match.group(), replacement,
                          match.start(), digest))
    return edits
