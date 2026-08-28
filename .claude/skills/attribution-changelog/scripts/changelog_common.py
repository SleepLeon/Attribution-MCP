"""Shared schema parsing, validation, and Confluence rendering for the attribution changelog.

Used by both validate.py (PR check) and publish.py (merge + manual publish).
"""

import base64
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date
from urllib.parse import quote

REQUIRED_FIELDS = [
    "version",
    "effective_date",
    "severity",
    "source",
    "restates_history",
    "summary",
    "owner",
    "reviewer",
]
SEVERITIES = {"major", "minor", "patch"}
SOURCES = {"merge", "manual"}
COLLECTION_LABEL = "attribution-changelog"

YAML_BLOCK_RE = re.compile(r"```yaml\s*\n(.*?)```", re.DOTALL)


def extract_yaml_block(text):
    """Pull the fenced ```yaml block out of a PR body. Returns None if absent."""
    match = YAML_BLOCK_RE.search(text or "")
    return match.group(1) if match else None


def parse_entry(yaml_text):
    import yaml

    data = yaml.safe_load(yaml_text)
    if not isinstance(data, dict):
        raise ValueError("changelog entry block did not parse to a mapping")
    return data


def _is_date(value):
    if isinstance(value, date):
        return True
    try:
        date.fromisoformat(str(value))
        return True
    except ValueError:
        return False


def validate_entry(entry):
    """Return a list of human-readable error strings; empty list means valid.

    `version` is exempt from the required-field check when absent, since publish.py
    fills it in by auto-increment — the field is still required by the time a page
    is created, just not at PR-description time.
    """
    errors = []

    for field in REQUIRED_FIELDS:
        if field == "version":
            continue
        if entry.get(field) in (None, "", []):
            errors.append(f"missing required field: {field}")

    effective_date = entry.get("effective_date")
    if effective_date is not None and not _is_date(effective_date):
        errors.append(f"effective_date is not a valid ISO date: {effective_date!r}")

    severity = entry.get("severity")
    if severity is not None and severity not in SEVERITIES:
        errors.append(f"severity must be one of {sorted(SEVERITIES)}, got {severity!r}")

    source = entry.get("source")
    if source is not None and source not in SOURCES:
        errors.append(f"source must be one of {sorted(SOURCES)}, got {source!r}")

    restates_history = entry.get("restates_history")
    if not isinstance(restates_history, bool):
        errors.append("restates_history must be true or false")
    elif restates_history:
        restated_back_to = entry.get("restated_back_to")
        if not restated_back_to:
            errors.append("restated_back_to is required when restates_history is true")
        elif not _is_date(restated_back_to):
            errors.append(f"restated_back_to is not a valid ISO date: {restated_back_to!r}")
        if severity is not None and severity != "major":
            errors.append(
                "restates_history=true implies severity=major "
                "(severity is derived from restatement, not self-declared)"
            )
    else:
        if severity == "major":
            errors.append(
                "severity=major implies restates_history=true "
                "(a methodology change that doesn't restate history is inconsistent)"
            )

    return errors


def bump_version(current, severity):
    major, minor, patch = (int(x) for x in current.split("."))
    if severity == "major":
        return f"{major + 1}.0.0"
    if severity == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def build_title(entry):
    return f"{entry['effective_date']} · v{entry['version']} · {entry['severity']} · {entry['summary']}"


def build_labels(entry):
    labels = [
        COLLECTION_LABEL,
        f"severity-{entry['severity']}",
        f"source-{entry['source']}",
    ]
    if entry.get("restates_history"):
        labels.append("restates-history")
    return labels


def render_teams_draft_lines(entry, page_url=None):
    lines = [
        f"Attribution model changelog — v{entry['version']}",
        entry["summary"],
        f"Severity: {entry['severity']}"
        + (" (history restated)" if entry.get("restates_history") else ""),
    ]
    lines.append(f"Details: {page_url}" if page_url else "Details: (link added once the page is created)")
    return lines


def render_page_body(entry, page_url=None):
    """Render Confluence storage-format (XHTML) body for the changelog page."""

    def esc(value):
        return html.escape(str(value))

    parts = []
    parts.append(
        f"<p><strong>Version:</strong> {esc(entry['version'])} &middot; "
        f"<strong>Effective date:</strong> {esc(entry['effective_date'])} &middot; "
        f"<strong>Severity:</strong> {esc(entry['severity'])} &middot; "
        f"<strong>Source:</strong> {esc(entry['source'])}</p>"
    )

    if entry.get("restates_history"):
        parts.append(
            f"<p><strong>History restated back to:</strong> {esc(entry.get('restated_back_to'))}</p>"
        )
    else:
        parts.append("<p><strong>History restated:</strong> No</p>")

    parts.append(f"<h2>Summary</h2><p>{esc(entry['summary'])}</p>")

    if entry.get("action_required"):
        parts.append(f"<h2>Action required</h2><p>{esc(entry['action_required'])}</p>")

    parts.append(
        f"<p><strong>Owner:</strong> {esc(entry['owner'])} &middot; "
        f"<strong>Reviewer:</strong> {esc(entry['reviewer'])}</p>"
    )

    teams_html = "<br/>".join(esc(line) for line in render_teams_draft_lines(entry, page_url))
    parts.append("<h2>Stakeholder message (draft — send manually to Teams)</h2>")
    parts.append(
        f'<ac:structured-macro ac:name="panel"><ac:rich-text-body><p>{teams_html}</p>'
        "</ac:rich-text-body></ac:structured-macro>"
    )

    return "".join(parts)


def _require_env(name):
    value = os.environ.get(name)
    if not value:
        print(f"missing required environment variable: {name}", file=sys.stderr)
        sys.exit(1)
    return value


class ConfluenceClient:
    def __init__(self):
        self.base_url = _require_env("CONFLUENCE_BASE_URL").rstrip("/")
        email = _require_env("CONFLUENCE_EMAIL")
        token = _require_env("CONFLUENCE_API_TOKEN")
        self.space_id = _require_env("CONFLUENCE_SPACE_ID")
        self.folder_id = _require_env("CONFLUENCE_FOLDER_ID")
        credentials = base64.b64encode(f"{email}:{token}".encode()).decode()
        self.auth_header = f"Basic {credentials}"

    def _request(self, method, path, body=None):
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", self.auth_header)
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            raise RuntimeError(f"{method} {url} failed: {exc.code} {detail}") from exc

    def create_page(self, title, body_html):
        payload = {
            "spaceId": self.space_id,
            "status": "current",
            "title": title,
            "body": {"representation": "storage", "value": body_html},
        }
        return self._request("POST", "/api/v2/pages", payload)

    def update_page(self, page_id, title, body_html, version_number, message="update"):
        payload = {
            "id": page_id,
            "status": "current",
            "title": title,
            "body": {"representation": "storage", "value": body_html},
            "version": {"number": version_number, "message": message},
        }
        return self._request("PUT", f"/api/v2/pages/{page_id}", payload)

    def move_into_folder(self, page_id):
        # v1 move-page endpoint, used as a workaround because creating a page with the
        # folder as `parentId` via the v2 API has been reported to 500 (2024-2025 reports —
        # NOT yet re-verified against current Confluence Cloud behavior; confirm before relying
        # on this in production, per the implementation plan's API notes).
        return self._request("PUT", f"/rest/api/content/{page_id}/move/append/{self.folder_id}")

    def add_labels(self, page_id, labels):
        payload = [{"prefix": "global", "name": label} for label in labels]
        return self._request("POST", f"/rest/api/content/{page_id}/label", payload)

    def search_cql(self, cql, limit=5):
        return self._request("GET", f"/rest/api/content/search?cql={quote(cql)}&limit={limit}")


def resolve_latest_version(client):
    data = client.search_cql(f'label="{COLLECTION_LABEL}" order by created desc', limit=1)
    results = (data or {}).get("results", [])
    if not results:
        return None
    match = re.search(r"v(\d+\.\d+\.\d+)", results[0].get("title", ""))
    return match.group(1) if match else None


def find_existing_page(client, version):
    cql = f'label="{COLLECTION_LABEL}" and title ~ "v{version}"'
    data = client.search_cql(cql, limit=1)
    results = (data or {}).get("results", [])
    return results[0] if results else None
