#!/usr/bin/env python3
"""Publish a changelog entry to Confluence.

Single entry point for both the merge trigger and the manual (workflow_dispatch)
path. Input is either a PR body containing a fenced ```yaml block, or a plain
YAML entry (as produced by assemble_dispatch_entry.py for manual entries).

Steps: resolve version -> idempotency check -> render body -> create page ->
move into folder -> apply labels -> patch in the page link for the Teams draft.

There is no Teams webhook call. The stakeholder alert is a draft section on the
page itself; a human sends it to Teams manually.
"""

import argparse
import sys

from changelog_common import (
    ConfluenceClient,
    build_labels,
    build_title,
    bump_version,
    extract_yaml_block,
    find_existing_page,
    parse_entry,
    render_page_body,
    resolve_latest_version,
    validate_entry,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to PR body or YAML entry file, or - for stdin")
    parser.add_argument("--dry-run", action="store_true", help="Render only, skip all Confluence calls")
    args = parser.parse_args()

    raw = sys.stdin.read() if args.input == "-" else open(args.input, encoding="utf-8").read()
    yaml_text = extract_yaml_block(raw) or raw
    entry = parse_entry(yaml_text)

    errors = validate_entry(entry)
    if errors:
        print("Changelog entry failed validation:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        entry.setdefault("version", "0.0.0-dryrun")
        print(render_page_body(entry, page_url="(dry run — no page created)"))
        return

    client = ConfluenceClient()

    if not entry.get("version"):
        latest = resolve_latest_version(client)
        entry["version"] = bump_version(latest, entry["severity"]) if latest else "1.0.0"

    existing = find_existing_page(client, entry["version"])
    if existing:
        print(f"Entry for v{entry['version']} already exists (page {existing['id']}) — skipping.")
        return

    title = build_title(entry)
    created = client.create_page(title, render_page_body(entry, page_url=None))
    page_id = created["id"]

    client.move_into_folder(page_id)
    client.add_labels(page_id, build_labels(entry))

    webui = (created.get("_links") or {}).get("webui", "")
    page_url = f"{client.base_url}{webui}" if webui else None
    client.update_page(
        page_id,
        title,
        render_page_body(entry, page_url=page_url),
        version_number=2,
        message="add stakeholder draft link",
    )

    print(f"Published changelog entry v{entry['version']}: {page_url or page_id}")


if __name__ == "__main__":
    main()
