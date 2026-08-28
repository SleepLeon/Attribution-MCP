#!/usr/bin/env python3
"""Turn workflow_dispatch inputs (env vars) into a plain YAML entry on stdout.

Called by changelog-publish.yml on the manual path before handing off to
publish.py, which accepts plain YAML (no fence) as a fallback input shape.
"""

import os
import sys

import yaml


def env(name):
    return os.environ.get(name, "")


def parse_bool(raw):
    return str(raw).strip().lower() in ("true", "1", "yes")


def main():
    entry = {
        "version": env("VERSION") or None,
        "effective_date": env("EFFECTIVE_DATE"),
        "severity": env("SEVERITY"),
        "source": "manual",
        "restates_history": parse_bool(env("RESTATES_HISTORY")),
        "summary": env("SUMMARY"),
        "owner": env("OWNER"),
        "reviewer": env("REVIEWER"),
        "restated_back_to": env("RESTATED_BACK_TO") or None,
        "action_required": env("ACTION_REQUIRED") or None,
    }
    entry = {key: value for key, value in entry.items() if value is not None}
    yaml.safe_dump(entry, sys.stdout, sort_keys=False)


if __name__ == "__main__":
    main()
