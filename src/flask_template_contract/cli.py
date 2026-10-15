from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .analyzer import analyze


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="flask-template-contract")
    parser.add_argument("root", nargs="?", default=".", help="Flask project root")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--strict", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = analyze(Path(args.root), strict=args.strict)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(result.to_dict(strict=args.strict), indent=2))
    else:
        for finding in result.findings:
            location = finding.location.to_dict() if finding.location else None
            where = f"{location['file']}:{location['line']}" if location else "<unknown>"
            details = ", ".join(filter(None, (finding.template, finding.variable)))
            render_location = finding.related_locations[0] if finding.related_locations else finding.location
            render_where = (f"{render_location.file}:{render_location.line}"
                            if render_location else "<unknown>")
            owner = finding.route or finding.function or "<unknown>"
            print(f"{finding.severity.value.upper()}: {where}: {details}: {finding.reason} "
                  f"[route/function={owner}, render={render_where}]")
        summary = result.to_dict(strict=args.strict)["summary"]
        print(f"{summary['errors']} error(s), {summary['warnings']} warning(s), {summary['cant_verify']} can't verify")
    return result.exit_code(strict=args.strict)
