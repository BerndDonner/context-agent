"""Conservative math text warning, never ban high-level \\text or \\mtext."""
import re
from context_agent.quality_rules import QualityContext, candidate, source_without_unset_text
from context_agent.models import QualityFinding

def check(context: QualityContext) -> list[QualityFinding]:
    text = context.main_tex.read_text(encoding='utf-8')
    code = source_without_unset_text(text)
    results=[]
    for math in re.finditer(r'\\(?:m|math)\{|\\startformula\b.*?\\stopformula', code, re.S):
        span = code[math.end():] if math.group().endswith('{') else math.group()
        if math.group().endswith('{'):
            # Stop at next right brace as a heuristic only; nested braces are deliberately candidates.
            span = span[:span.find('}') if '}' in span else len(span)]
        for m in re.finditer(r'\\(?:rm|bf|it)\b', span):
            offset = math.end()+m.start() if math.group().endswith('{') else math.start()+m.start()
            results.append(candidate('semantic_math_text', text, offset,
                'Low-Level-Schriftumschaltung in Mathematik: ist hier \\text oder \\mtext gemeint?',
                hint='Textsemantik prüfen; sprachliche Passagen bevorzugt \\mtext.'))
    return results
