"""Only repeat-pair warnings; equal coordinates need not mean the same point."""
import re
from context_agent.quality_rules import QualityContext, candidate, source_without_unset_text
from context_agent.models import QualityFinding

_PAIR=re.compile(r'\(\s*(-?\d+(?:\.\d+)?\s*(?:cm|mm|pt|bp)?)\s*,\s*(-?\d+(?:\.\d+)?\s*(?:cm|mm|pt|bp)?)\s*\)')

def check(context: QualityContext) -> list[QualityFinding]:
    text=context.main_tex.read_text(encoding='utf-8')
    code=source_without_unset_text(text, preserve_mp=True)
    result=[]
    for block in re.finditer(r'\\startMP(?:code|page)\b.*?\\stopMP(?:code|page)', code, re.S):
        seen={}
        for match in _PAIR.finditer(block.group()):
            key=tuple(''.join(s.split()) for s in match.groups())
            offset=block.start()+match.start()
            if key in seen:
                result.append(candidate('coordinate_reuse', text, offset,
                    f'Koordinatenpaar {match.group()} mehrfach im selben MetaPost-Block; logische Identität unklar.',
                    hint='Nur bei identischem logischen Punkt eine pair-Variable einführen.',confidence=.5))
            else:
                seen[key]=offset
    return result
