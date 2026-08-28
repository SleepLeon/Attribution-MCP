#!/usr/bin/env python3
"""Validate a changelog entry block. Used as a required PR status check.

Usage: validate.py --input <path-to-pr-body-file>   (or --input - for stdin)
"""

import argparse
import sys

from changelog_common import extract_yaml_block, parse_entry, validate_entry


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    args = parser.parse_args()

    raw = sys.stdin.read() if args.input == "-" else open(args.input, encoding="utf-8").read()

    yaml_text = extract_yaml_block(raw)
    if yaml_text is None:
        print("No fenced ```yaml changelog block found in the PR description.", file=sys.stderr)
        sys.exit(1)

    try:
        entry = parse_entry(yaml_text)
    except Exception as exc:
        print(f"Could not parse changelog YAML block: {exc}", file=sys.stderr)
        sys.exit(1)

    errors = validate_entry(entry)
    if errors:
        print("Changelog entry failed validation:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        sys.exit(1)

    print(f"Changelog entry OK (version={entry.get('version') or 'auto'}, severity={entry['severity']})")


if __name__ == "__main__":
    main()
