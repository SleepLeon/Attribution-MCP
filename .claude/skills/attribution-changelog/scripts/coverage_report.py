#!/usr/bin/env python3
"""Count changelog entries per source over a recent window and flag a silent manual path.

The changelog only captures repo-borne changes automatically; if manual entries stop
happening it quietly becomes incomplete. Writes a Markdown summary to stdout (CI appends it
to the job summary). Exits 0 always — this is a nudge, not a gate.

Usage: coverage_report.py [--days 90]
"""

import argparse

from changelog_common import COLLECTION_LABEL, ConfluenceClient


def count(client, source, days):
    cql = f'label="{COLLECTION_LABEL}" and label="source-{source}" and created >= now("-{days}d")'
    data = client.search_cql(cql, limit=1)
    return (data or {}).get("totalSize", len((data or {}).get("results", [])))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=90)
    args = parser.parse_args()

    client = ConfluenceClient()
    merged, manual = count(client, "merge", args.days), count(client, "manual", args.days)

    print(f"## Attribution changelog coverage — last {args.days} days\n")
    print(f"- Merge entries: {merged}")
    print(f"- Manual entries: {manual}")
    if manual == 0:
        print(
            "\n**No manual entries in this window.** Either nothing changed outside the repo, or "
            "UI retunes / channel mappings / upstream platform changes are going unlogged. "
            "Worth asking the model owners."
        )


if __name__ == "__main__":
    main()
