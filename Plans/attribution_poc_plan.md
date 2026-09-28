# Attribution Model + Claude — POC Plan

## Known facts (only what's been stated)
- An attribution model exists as a complete repo. It calculates multi-touch attribution.
- It runs and exports data daily; historical data exists.
- The export destination is Redshift.
- Redshift is not currently accessible for this project — mock data is needed instead.
- Goal: a POC where Claude, connected via MCP, can answer questions about the attribution model's output.
- A stated requirement: people need to be able to ask *how the model works*, not just query output numbers — so the model's methodology needs to be understood/documented, not just its data.

Everything below is a plan to build toward that. Nothing has been built yet.

---

## Step 1 — Document the real methodology
Before any mock data is designed, pull the actual methodology from the attribution repo: what multi-touch logic it uses, any README/docs in the repo, how it weights touchpoints. This has to come from the real repo, not be assumed or invented. Write it down as its own reference doc.

## Step 2 — Document the real export schema
From the attribution repo or whoever maintains it: what tables does it write to Redshift, what columns, what grain (this has been confirmed as daily, historical). Get this from the actual DDL/schema or from the repo owner — not guessed.

## Step 3 — Design mock data that mirrors the real schema
Once Steps 1 and 2 give real schema and methodology, design mock data with the same shape (same tables, columns, grain) so the POC is a fair stand-in for the real thing.

## Step 4 — Build a small MCP server over the mock data
A server exposing the mock tables as tools Claude can call, plus a tool that surfaces the methodology doc from Step 1 so Claude can explain "why" a result looks the way it does, not just report numbers.

## Step 5 — Connect the MCP server to Claude and test
Run it locally (Claude Desktop, stdio transport for a POC), confirm Claude can call the tools, and test it against real questions people would actually ask.

## Step 6 — Log gaps and iterate
Track questions the tools can't answer well — missing filters, missing tables, methodology explanations that don't land — and refine the tool design.

---

## Parallel track — Redshift access
This doesn't block Steps 1–6 but needs to happen for the project to eventually use real data instead of mock data.

| Step | Action |
|---|---|
| 1 | Identify who owns the attribution model's Redshift schema |
| 2 | Request a read-only role scoped to just that schema |
| 3 | Decide auth method (IAM preferred vs. credentials via secrets manager) |
| 4 | Confirm network path from wherever the MCP server will run to Redshift |
| 5 | Get sign-off that read-only, schema-scoped access is acceptable |
| 6 | Store credentials securely once received |
| 7 | Test the connection standalone before wiring it into anything |

---

## Later — Cutover, hardening, distribution
Deferred until the above is done:
- Swap mock data source for a real Redshift query in the MCP server
- Decide freshness strategy (live query vs. cached per job run)
- Harden: row limits, error handling, audit logging
- Decide distribution: Desktop-only vs. hosted/web access

---

## Status as of 2026-07-03

Steps 1–5 are done:
- Steps 1–2: real methodology + export schema documented in `attribution_model_documentation.md`, sourced from the actual `attribution-model-revamp` repo.
- Steps 3–4: mock data for 3 of 7 real tables (`refactored_attribution_prod`, `refactored_pre_smad_prod`, `refactored_breakdown_prod`) + a Poetry-managed MCP server (`attribution_mcp/`) exposing query + methodology tools, verified over the real MCP stdio protocol.
- Step 5: registered with Claude Code, tested locally. `CLAUDE.md` guardrails went through several rounds of tightening based on real test questions (see gaps below).

Step 6 (log gaps and iterate) is ongoing — gaps found so far:
- Channel filters are case-sensitive (`Influencer` vs `influencer`) — silently returns an empty result instead of erroring or normalizing casing.
- Guardrail wording needed multiple rounds before behavior was reliable (e.g. a strategic question triggering an unnecessary tool call; the out-of-scope redirect not catching "link to Jira"-style asks; non-technical audience needing shorter answers than an engineer would expect). Guardrails are not a one-shot fix — they need repeated adversarial testing, not just a single pass.
- Only 3 of 7 real output tables are covered — not yet known how often real usage would need the other 4 (`refactored_total_orders_prod`, `staging_scaling_factors_prod`, `refactored_paid_social_prod`, `refactored_attribution_metrics_prod`).

## Next steps (as of 2026-07-03)

See `poc_maturity_and_redshift_plan.md` for the active, up-to-date execution
plan (POC hardening + attribution documentation + Redshift cutover). The list
below is kept for history.

1. **Harden guardrails + fix data bugs first.** Batch-test adversarial/edge-case questions against `CLAUDE.md` (ambiguous scope, chained follow-ups, prompt-injection-style asks) rather than one-off manual testing. Fix channel-value case-sensitivity and add input normalization to the query tools so non-technical users don't get silent empty results.
2. **Then start the parallel Redshift-access track** (see table above — ownership, read-only role, auth method, network path, sign-off, credential storage, standalone connection test). This is what unblocks moving off mock data.
3. **Then real user testing.** Recruit a few actual non-technical testers and capture their real questions, rather than relying on the guessed cheat sheet in `attribution_model_documentation.md` §9 — let observed usage drive what gets built/fixed next (e.g. whether the remaining 4 tables are actually needed).
4. **Deepen `attribution_model_documentation.md`.** Go back into `attribution-model-revamp` for everything not yet fully documented — in particular: the scaling-factor computation (paid social platform correction vs. TV-redistribution correction — currently only described at a high level), the redistribution logic (how TV's top-down model and leftover (direct)/(none) credit actually move between channels), and schema for the 4 remaining tables (`refactored_total_orders_prod`, `staging_scaling_factors_prod`, `refactored_paid_social_prod`, `refactored_attribution_metrics_prod`). Same rule as Steps 1–2: pull from real files with file/line citations, don't infer or invent.
