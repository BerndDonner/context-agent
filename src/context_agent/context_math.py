"""Built-in ConTeXt source convention checks.

Only inspect ordinary ConTeXt source. Dollar signs in comments, literal
\type{...} and code/typing environments are not inline mathematics.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from typing import TYPE_CHECKING

from context_agent.models import NogoFinding

if TYPE_CHECKING:
    from context_agent.nogos import NogoContext


_RAW_ENVIRONMENTS = (
    "typing",
    "MPcode",
    "MPdefinitions",
    "MPinclusions",
    "luacode",
    "buffer",
)
_TYPE_COMMAND = re.compile(r"\\(?:type|typ)(?:\[[^\]\n]*\])?\{")


def _skip_braced(text: str, opening: int) -> int:
    """Return the position just after a (possibly nested) literal argument."""
    depth = 1
    index = opening + 1
    while index < len(text) and depth:
        if text[index] == "\\" and index + 1 < len(text) and text[index + 1] in "{}":
            index += 2
            continue
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
        index += 1
    return index


def _dollar_positions(source: str) -> list[int]:
    """Return unescaped dollar delimiters outside comments and literal regions."""
    positions: list[int] = []
    i = 0
    while i < len(source):
        if source[i] == "%":
            newline = source.find("\n", i)
            i = len(source) if newline == -1 else newline + 1
            continue
        if source[i] == "\\":
            # Ignore the complete body of ConTeXt code and verbatim environments.
            environment = next(
                (name for name in _RAW_ENVIRONMENTS
                 if source.startswith("\\start" + name, i)
                 and (i + len("\\start" + name) == len(source)
                      or not source[i + len("\\start" + name)].isalpha())),
                None,
            )
            if environment:
                end = source.find("\\stop" + environment, i + len("\\start" + environment))
                if end == -1:
                    # Unclosed environment is not ours to diagnose here.
                    break
                i = end + len("\\stop" + environment)
                continue
            literal = _TYPE_COMMAND.match(source, i)
            if literal:
                i = _skip_braced(source, literal.end() - 1)
                continue
            if i + 1 < len(source) and source[i + 1] == "\\":
                i += 2
                continue
            # An escaped percent or dollar is a literal, not a comment/math delimiter.
            if i + 1 < len(source) and source[i + 1] in "%$":
                i += 2
                continue
            # Other TeX control sequences are ordinary source, not literal regions.
            i += 1
            continue
        if source[i] == "$":
            positions.append(i)
        i += 1
    return positions


def check(context: NogoContext) -> list[NogoFinding]:
    """Always enforce ConTeXt inline/display-math conventions."""
    source = context.main_tex.read_text(encoding="utf-8")
    delimiters = _dollar_positions(source)
    newlines = [index for index, ch in enumerate(source) if ch == "\n"]
    findings: list[NogoFinding] = []
    index = 0
    while index < len(delimiters):
        at = delimiters[index]
        doubled = index + 1 < len(delimiters) and delimiters[index + 1] == at + 1
        # Paired delimiters are one issue, not two separate findings.
        closing_index = index + (2 if doubled else 1)
        while closing_index < len(delimiters):
            close = delimiters[closing_index]
            close_doubled = (closing_index + 1 < len(delimiters)
                             and delimiters[closing_index + 1] == close + 1)
            if close_doubled == doubled:
                break
            closing_index += 2 if close_doubled else 1
        closing = closing_index < len(delimiters)
        end = (delimiters[closing_index] + (2 if doubled else 1)) if closing else at + (2 if doubled else 1)
        sample = source[at:min(end, at + 80)].replace("\n", " ")
        if not closing:
            sample += " …"
        findings.append(NogoFinding(
            rule_id="context-dollar-math",
            file="main.tex",
            line=bisect_right(newlines, at) + 1,
            message=f"TeX-Dollar-Mathematik ist in diesem Projekt nicht erlaubt: {sample!r}.",
            repair_hint=(
                "Für Inline-Mathematik \\m{...} statt $...$ verwenden; "
                "für abgesetzte Formeln \\startformula ... \\stopformula. "
                "Mathematischen Inhalt und Bezeichner unverändert lassen."
            ),
        ))
        index = closing_index + (2 if doubled else 1) if closing else len(delimiters)
    return findings
