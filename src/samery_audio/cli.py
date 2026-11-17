"""Command-line access to local lossless audio verification."""

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from . import AudioInfo, Comparison, VerificationError, __version__, compare, probe


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=f"samery-audio {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="Read audio stream properties")
    inspect.add_argument("source", type=Path)
    comparison = commands.add_parser("compare", help="Compare decoded PCM and format properties")
    comparison.add_argument("source", type=Path)
    comparison.add_argument("candidate", type=Path)
    for command in (inspect, comparison):
        command.add_argument("--json", action="store_true", help="Print a JSON report")
        command.add_argument("--timeout", type=float, default=300, help="Seconds per subprocess")
    args = parser.parse_args(argv)
    result: AudioInfo | Comparison
    try:
        if args.command == "inspect":
            result = probe(args.source, timeout=args.timeout)
            code = 0
        else:
            result = compare(args.source, args.candidate, timeout=args.timeout)
            code = 0 if result.equivalent else 1
    except VerificationError as error:
        if args.json:
            print(
                json.dumps(
                    {
                        "error": str(error),
                        "code": error.code,
                        "operation": error.operation,
                        "returncode": error.returncode,
                    }
                )
            )
        else:
            print(f"{error.code}: {error}", file=sys.stderr)
        return 2
    report = asdict(result)
    if args.json:
        print(json.dumps(report, indent=2))
    elif isinstance(result, AudioInfo):
        print(
            f"{result.codec.upper()} · {result.bit_depth}-bit · {result.sample_rate} Hz · {result.channels} channel(s)"
        )
    else:
        print(
            "PASS: matching decoded PCM and format properties."
            if result.equivalent
            else "FAIL: differences in " + ", ".join(result.differences)
        )
    return code
