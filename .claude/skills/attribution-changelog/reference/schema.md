# Changelog entry schema

A fenced YAML block in a PR description (merge path), or the same shape
assembled from conversation on the manual path. Every value is taken from
that specific PR / manual entry — there is no fixed or expected set of
values anywhere in the tooling, only these field names and types.

```yaml
version: <semver, optional>          # auto-incremented from severity if omitted
effective_date: <ISO date>
severity: <major | minor | patch>
source: <merge | manual>
restates_history: <true | false>
restated_back_to: <ISO date>         # required when restates_history is true
summary: <one-line description of what this PR changed>
action_required: <optional free text>
owner: <name>
reviewer: <name>
```

## Field notes

| Field | Required | Notes |
|---|---|---|
| `version` | No | Auto-incremented (semver) from the latest published entry if omitted. |
| `effective_date` | Yes | ISO date. |
| `severity` | Yes | `major` \| `minor` \| `patch`. Must agree with `restates_history` (see below). |
| `source` | Yes | `merge` \| `manual`. |
| `restates_history` | Yes | Boolean. Drives severity consistency check. |
| `restated_back_to` | Conditional | Required, ISO date, only when `restates_history: true`. |
| `summary` | Yes | One line, describing this PR's change. Also becomes the Teams draft headline and part of the page title. |
| `action_required` | No | Free text, only if this specific PR requires someone to do something before trusting new numbers. |
| `owner` | Yes | Who made the change (this PR's author). |
| `reviewer` | Yes | Who reviewed it (this PR's reviewer). |

## Severity rules

- **major** — methodology change (attribution logic, lookback window, model type). History restated, past numbers move.
- **minor** — new parameter, retune, or non-breaking addition. Forward-looking, history intact.
- **patch** — bug fix or data correction. Little or no material movement.

Severity is checked against `restates_history`, not trusted as a bare
declaration:
- `restates_history: true` implies `severity: major`.
- `severity: major` implies `restates_history: true`.
- `minor` and `patch` both require `restates_history: false`; the distinction
  between them still requires human judgment `validate.py` cannot make.

## Labels applied on publish

- `attribution-changelog` — collection marker, used for all CQL queries
- `severity-{major|minor|patch}`
- `restates-history` — only when true
- `source-{merge|manual}`

## Stakeholder alert

There is no Teams webhook call. `publish.py` renders a short draft message
(version, summary, severity, restatement flag, page link) directly onto the
Confluence page, under "Stakeholder message (draft — send manually to
Teams)". A human copies that into Teams — nothing posts automatically.
