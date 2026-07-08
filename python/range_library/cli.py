"""Command line interface for Range Library summary reports."""

from __future__ import annotations

import argparse
import json

from .report import generate_report_from_export


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a Range Library JSON summary report.")
    parser.add_argument("path", help="Path to a JSON fixture or export.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    print(json.dumps(generate_report_from_export(args.path), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
