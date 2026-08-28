---
name: attribution-changelog
description: Use when writing or reviewing an attribution model changelog entry, classifying change severity, or logging a manual model change that didn't go through a PR.
---

# Attribution model changelog

Every change to the attribution model gets a changelog entry: a fenced
YAML block, published to Confluence with a draft stakeholder message.
Two entry paths — automatic on PR merge, and manual for changes with no
PR (UI-side retunes, upstream platform changes). This skill drives both;
the judgment involved is the same, only where the input comes from
differs.

Field reference: `reference/schema.md`.

## Path 1 — drafting the block for a PR

Read the PR's diff and description, then fill in the YAML block (see
schema.md for field definitions). Insert it into the PR description
inside a fenced ` ```yaml ` block — `changelog-validate.yml` looks for
exactly that.

## Path 2 — manual entry (no PR)

There's no diff to read, so ask more questions than you would for path 1
before drafting anything — what changed, when it took effect, whether
past numbers move, who owns it, who reviewed it. Once you have a
complete entry, hand it off by running:

```
gh workflow run changelog-publish.yml \
  -f effective_date=<date> -f severity=<major|minor|patch> \
  -f restates_history=<true|false> -f restated_back_to=<date, if applicable> \
  -f summary="<one line>" -f owner="<name>" -f reviewer="<name>" \
  -f action_required="<optional>"
```

## Severity

Derive `severity` from `restates_history`, don't just take a stated
severity at face value — `validate.py` enforces the same consistency
check, but get it right at draft time:

- **major** — methodology change (attribution logic, lookback window,
  model type). History restated, past numbers move.
- **minor** — parameter retune or forward-looking, non-breaking change.
  History intact.
- **patch** — bug fix or data correction, little or no material
  movement.

## Uncertainty handling

If the diff or the description of a manual change doesn't make clear
whether historical output is reprocessed, say so and ask — don't guess.
A confidently wrong `restates_history` flag is worse than asking one
more question, because it's the exact thing that causes dashboards and
past reporting to silently disagree.

## Stakeholder message

`publish.py` renders a short draft (version, one-line summary, severity,
restatement flag, page link) directly onto the Confluence page. Keep the
`summary` field itself short — it becomes that headline verbatim. There
is no automatic Teams post; a human sends it manually from the page.
