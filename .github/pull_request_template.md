<!--
If this PR changes the attribution model, fill in the changelog block below.
Field reference: .claude/skills/attribution-changelog/reference/schema.md
-->

## Attribution model changelog entry

```yaml
version:            # leave blank to auto-increment
effective_date:     # YYYY-MM-DD
severity:           # major | minor | patch
source: merge
restates_history:   # true | false
restated_back_to:   # YYYY-MM-DD, required if restates_history is true
summary:
expected_effect:    # required if major: what changes in the numbers, and why (plain language)
period_compared:    # period a before/after was measured over, e.g. 2026-06-01..2026-08-31
impact:             # required if major; one item per channel that moves
  # - channel: paid_social
  #   metric: attributed_revenue   # optional
  #   direction: up                # up | down | flat
  #   magnitude: "8-12%"
  #   before: 120k                 # optional
  #   after: 134k                  # optional
  #   basis: measured              # measured (before/after run) | estimated (reasoned)
  #   confidence: medium           # optional: low | medium | high
  #   note: shorter window credits fewer upper-funnel touches
downstream:         # dashboards, budget models, bidding rules that read this output
  # - Marketing performance dashboard
action_required:
owner:
reviewer:
```

- [ ] This PR is *only part* of a model change — some of it happens outside the repo
      (UI retune, channel mapping, upstream platform). If checked, also log a manual entry
      (`/attribution-changelog`).
