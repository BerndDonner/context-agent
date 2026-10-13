"""Mandatory dynamic dollar-math check; ConTeXt LMTX is the syntax authority.

The actual lint compilation runs inside the job's existing Hosted Shell container.
This wrapper deliberately does not inspect or tokenize TeX or MetaPost in Python.
"""

from context_agent.models import NogoFinding
from context_agent.nogos import NogoContext


def check(context: NogoContext) -> list[NogoFinding]:
    if context.remote_lint is None:
        raise RuntimeError("dynamic ConTeXt check requires the active Hosted Shell session")
    return context.remote_lint("dollar_math")
