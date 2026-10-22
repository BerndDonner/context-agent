"""Safe canonicalization of equivalent, explicitly recognized unit aliases."""
from __future__ import annotations

import hashlib
import re

from context_agent.quality_rules import Edit, QualityContext, source_without_unset_text
from context_agent.models import QualityFinding

_ALIAS = re.compile(r'\\unit\{(?:kiloohm|Kiloohm|KiloOhm)\}')


def propose_edits(context: QualityContext, findings: list[QualityFinding]) -> list[Edit]:
    text = context.main_tex.read_text(encoding='utf-8')
    mask = source_without_unset_text(text)
    reported = {item.line for item in findings if item.rule_id == 'number_with_unit'}
    digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
    return [Edit('number_with_unit', 'main.tex', match.group(), r'\unit{kOhm}',
                 match.start(), digest)
            for match in _ALIAS.finditer(mask)
            if text.count('\n', 0, match.start()) + 1 in reported]
