from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TemplateParts:
    preamble: str
    body: str
    trailing: str


_COMMAND_RE = re.compile(r"\\(starttext|stoptext)\b")
_VERBATIM_START_RE = re.compile(
    r"\\start(typing|buffer|luacode|MPcode|MPdefinitions)\b"
)
_VERBATIM_END_TEMPLATE = r"\\stop{environment}\b"


def _masked_source(source: str) -> str:
    """Mask comments and common verbatim-like environments without changing length."""
    chars = list(source)
    i = 0
    environment: str | None = None

    while i < len(source):
        if environment is not None:
            end_re = re.compile(_VERBATIM_END_TEMPLATE.format(environment=re.escape(environment)))
            match = end_re.search(source, i)
            end = match.end() if match else len(source)
            for index in range(i, end):
                if source[index] not in "\r\n":
                    chars[index] = " "
            i = end
            environment = None
            continue

        if source[i] == "%" and (i == 0 or source[i - 1] != "\\"):
            newline = source.find("\n", i)
            end = len(source) if newline == -1 else newline
            for index in range(i, end):
                chars[index] = " "
            i = end
            continue

        if source[i] == "\\":
            match = _VERBATIM_START_RE.match(source, i)
            if match:
                environment = match.group(1)
                for index in range(match.start(), match.end()):
                    chars[index] = " "
                i = match.end()
                continue

        i += 1

    return "".join(chars)


def split_template(source: str) -> TemplateParts:
    masked = _masked_source(source)
    commands = list(_COMMAND_RE.finditer(masked))
    starts = [match for match in commands if match.group(1) == "starttext"]
    if not starts:
        raise ValueError("template has no effective \\starttext")

    start = starts[0]
    stop = next(
        (
            match
            for match in commands
            if match.group(1) == "stoptext" and match.start() > start.end()
        ),
        None,
    )
    if stop is None:
        raise ValueError("template has no effective \\stoptext after \\starttext")

    return TemplateParts(
        preamble=source[: start.start()],
        body=source[start.end() : stop.start()],
        trailing=source[stop.end() :],
    )


def assemble_document(preamble: str, body: str) -> str:
    return f"{preamble.rstrip()}\n\n\\starttext\n{body.strip()}\n\\stoptext\n"
