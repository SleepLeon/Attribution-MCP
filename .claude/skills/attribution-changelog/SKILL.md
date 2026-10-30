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
  -f expected_effect="<what changes and why>" \
  -f impact="<channel:direction:magnitude:basis[:confidence]; ...>" \
  -f period_compared="<start..end, if measured>" \
  -f downstream="<consumer; consumer>" \
  -f action_required="<optional>"
```

`impact` is required for `major`. Ask for it channel by channel — see
"Impact estimate" below.

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

## Impact estimate

The most valuable field and the easiest to skip — don't let it stay blank
on a major change. Ask: *which channels' attributed numbers move, in which
direction, roughly how much?* Then: *what reads this output* (dashboards,
Pigment budget model, bidding rules) → `downstream`.

- Start with `expected_effect`: two or three plain sentences — what moves,
  roughly how much, and the mechanism (e.g. "a shorter window drops credit
  from early upper-funnel touches, so paid social gains and affiliate loses").
  Mechanisms must come from the model's documented methodology
  (`get_methodology`), not general MTA theory.
- One item per channel; `direction` is `up`, `down` or `flat`.
- Record `basis`: `measured` if someone ran a before/after (give
  `period_compared`, and `before`/`after` values if known), `estimated` if
  reasoned from the change. Never label an estimate as measured.
- Add `confidence` and a one-line `note` where it helps a reader trust or
  question the number.
- Magnitude as a range or approximation (`"8-12%"`, `"~5%"`), not false precision.
- Same phrasing across authors: channel names as they appear in the model
  (`paid_social`, `affiliate`), signed from the *attributed* number's point of view.
- If you can't estimate it from the diff (path 1) or the user doesn't know
  (path 2), say so and ask them to run a before/after comparison rather
  than inventing numbers. The validator requires a magnitude for every
  item, so a real estimate has to come from a person.

## Severity examples

- **major** — lookback window 30d → 14d; switching the model type; changing how
  a channel's touchpoints are weighted. `restates_history: true`, `impact` required.
- **minor** — new channel or touchpoint added; retuning a parameter going forward.
- **patch** — fixing a mis-mapped campaign; correcting a null-handling bug.

## Uncertainty handling

If the diff or the description of a manual change doesn't make clear
whether historical output is reprocessed, say so and ask — don't guess.
A confidently wrong `restates_history` flag is worse than asking one
more question, because it's the exact thing that causes dashboards and
past reporting to silently disagree.

## Stakeholder message

`publish.py` renders a short draft (version, one-line summary, severity,
restatement flag, one-line impact, page link) directly onto the Confluence
page. Keep the `summary` field itself short — it becomes that headline
verbatim, and the whole draft should stay a pointer, not a report. There
is no automatic Teams post (deliberately dropped for now); a human sends it
manually from the page.
