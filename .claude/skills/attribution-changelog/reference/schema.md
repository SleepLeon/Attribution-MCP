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
expected_effect: <plain language: what changes in the numbers and why>   # required when major
period_compared: <e.g. 2026-06-01..2026-08-31>                          # optional
impact:                              # required when severity is major
  - channel: <channel name>
    metric: <e.g. attributed_revenue>      # optional
    direction: <up | down | flat>
    magnitude: <"8-12%", "~5%", ...>
    before: <value>                        # optional
    after: <value>                         # optional
    basis: <measured | estimated>
    confidence: <low | medium | high>      # optional
    note: <why this channel moves>         # optional
downstream:                          # optional list of consumers of the output
  - <dashboard / budget model / bidding rule>
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
| `expected_effect` | Required if `major` | Short plain-language account of what changes in the numbers and why. Rendered as its own section. |
| `period_compared` | No | Period a before/after comparison covers. Say so whenever `basis: measured`. |
| `impact` | Required if `major` | One item per channel: `channel`, `direction`, `magnitude`, `basis` required; `metric`, `before`, `after`, `confidence`, `note` optional. `basis: measured` = from a before/after run; `estimated` = reasoned from the change (shown as "est." in the Teams draft). Rendered as a table; each channel becomes a label. A range or "~" is fine. |
| `downstream` | No | Free-text list of what reads this output (dashboards, Pigment, bidding rules). Warned about if `impact` is set without it. |
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
- `channel-{name}` — one per channel in `impact`
- `pr-{number}` — merge path only; the idempotency key, so a re-run never duplicates a page

## Stakeholder alert

There is no Teams webhook call. `publish.py` renders a short draft message
(version, summary, severity, restatement flag, page link) directly onto the
Confluence page, under "Stakeholder message (draft — send manually to
Teams)". A human copies that into Teams — nothing posts automatically.

## Manual dispatch format

`workflow_dispatch` inputs are flat strings, so `impact` and `downstream` are
semicolon-separated:

- `impact`: `paid_social:up:8-12%:measured:high; affiliate:down:~5%:estimated:low`
  (`channel:direction:magnitude:basis[:confidence]`)
- `expected_effect`, `period_compared`: plain strings
- `downstream`: `Marketing dashboard; Pigment budget model`

`assemble_dispatch_entry.py` converts these to the YAML shape above.

## Scheduled coverage check

`changelog-coverage.yml` runs monthly and reports merge vs manual entry counts
over the last 90 days to the job summary, flagging a window with zero manual
entries.
