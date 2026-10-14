"""Only the executed ConTeXt syntax is authoritative for dollar math."""
from context_agent.quality_rules import QualityContext
from context_agent.models import QualityFinding

def check(context: QualityContext) -> list[QualityFinding]:
    if context.remote_lint is None:
        raise RuntimeError('dynamic ConTeXt lint requires a live session')
    return context.remote_lint('dollar_math')
