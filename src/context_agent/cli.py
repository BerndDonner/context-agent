from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from context_agent import __version__
from context_agent.errors import ContextAgentError
from context_agent.job import load_job
from context_agent.workflow import run_job


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="context-agent",
        description="Agentische Erstellung kompilierter ConTeXt-Dokumente.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="einen Job ausführen")
    run_parser.add_argument("job", type=Path, help="Pfad zum Jobverzeichnis")

    validate_parser = subparsers.add_parser("validate", help="Jobstruktur und YAML prüfen")
    validate_parser.add_argument("job", type=Path, help="Pfad zum Jobverzeichnis")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate":
            job = load_job(args.job)
            print(f"Job gültig: {job.root}")
            print(f"Template: {job.template_path}")
            print(f"Eingaben: {len(job.inputs)}, Referenzen: {len(job.references)}")
            return 0

        report = run_job(args.job)
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
        return 0 if report.status == "success" else 1
    except ContextAgentError as exc:
        print(f"context-agent: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
