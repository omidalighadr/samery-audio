"""Command-line access to local lossless audio verification."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

from . import VerificationError, compare, probe


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
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
    try:
        if args.command == "inspect":
            result = probe(args.source, timeout=args.timeout)
            code = 0
        else:
            result = compare(args.source, args.candidate, timeout=args.timeout)
            code = 0 if result.equivalent else 1
    except (VerificationError, OSError) as error:
        if args.json:
            print(json.dumps({"error": str(error)}))
        else:
            print(str(error), file=sys.stderr)
        return 2
    report = asdict(result)
    if args.json:
        print(json.dumps(report, indent=2))
    elif args.command == "inspect":
        print(f"{result.codec.upper()} · {result.bit_depth}-bit · {result.sample_rate} Hz · {result.channels} channel(s)")
    else:
        print("PASS: matching decoded PCM and format properties." if result.equivalent
              else "FAIL: differences in " + ", ".join(result.differences))
    return code
