# Attribution model changelog — implementation plan

## Goal

Every change to the attribution model produces a durable, structured record in Confluence and a short alert to stakeholders in Teams. The record must say not just *what* changed, but whether historical numbers were restated — because that is what causes dashboards and past reporting to silently disagree.

Two entry paths: automatic on merge for changes that go through the repo, and manual for changes that do not (UI-side retunes, channel mapping changes, upstream platform behaviour).

---

## Decisions already made

| Decision | Choice | Why |
|---|---|---|
| Storage shape | Confluence **folder** with timestamped child pages | Append-only. No shared page to mutate, so no read-modify-write, no version conflicts, no retry logic. |
| Filtering | **Labels**, queried via CQL | Recovers the filtering an index table would have given, without a mutable index. |
| Merge trigger | GitHub Action, **no model involved** | Publishing is deterministic API calls. Keep CI reliable. |
| Validation gate | **Plain schema check**, not a model | A required status check must give the same result every run. |
| Skill count | **One** skill, two entry paths | The judgment work is identical; only the input source differs. |
| Manual entry | **Conversational**, form as fallback | Forms produce worse impact estimates than dialogue. |
| Manual publishing | Skill fires `gh workflow run`; script runs **in CI** | Keeps credentials in one place, gives every entry a run log. |

---

## Architecture

```
PR opened ──> validate (schema check, required)
                   │
              merge to main
                   │
                   ▼
            publish.py ──> Confluence page ──> move into folder ──> labels
                   │
                   └────> Teams webhook

Manual ──> skill (conversational) ──> gh workflow run ──> publish.py ──> same
```

The skill sits *beside* this, not inside it: used locally to help authors draft the block, and to drive the manual path.

---

## Entry schema

A fenced YAML block in the PR description (or assembled by the skill for manual entries).

```yaml
version: 2.3.0
effective_date: 2026-09-01
severity: major            # major | minor | patch
source: merge              # merge | manual
restates_history: true
restated_back_to: 2026-01-01   # required when restates_history is true
summary: Lookback window shortened from 30d to 14d
impact:
  - channel: paid_social
    direction: up
    magnitude: "8-12%"
  - channel: affiliate
    direction: down
    magnitude: "~5%"
downstream:
  - Marketing performance dashboard
  - Pigment budget model
  - Paid social bidding rules
action_required: Re-baseline Q4 channel targets before planning cycle
owner: <name>
reviewer: <name>
```

### Severity rules

- **major** — methodology change (attribution logic, lookback window, model type). History restated, past numbers move.
- **minor** — new channel or touchpoint, parameter retune. Forward-looking, history intact.
- **patch** — bug fix or data correction. Little or no material movement.

Derive severity from `restates_history` where possible rather than trusting the author's declaration — it is harder to game.

---

## Repository layout

```
.claude/skills/attribution-changelog/
    SKILL.md
    scripts/publish.py
    scripts/validate.py
    reference/schema.md
.github/workflows/changelog-validate.yml
.github/workflows/changelog-publish.yml
.github/pull_request_template.md
CODEOWNERS
```

`CODEOWNERS` must cover `.claude/skills/` and `.github/workflows/` — anyone with write access there is effectively editing what runs in CI.

---

## Confluence setup

**Folder:** "Attribution model changelog", in the analytics space.

**Page titles:** ISO date first so alphabetical sort equals chronological.

```
2026-08-28 · v2.3.0 · major · Lookback window 30→14d
```

**Labels on every page:**

- `attribution-changelog` — collection marker, used for all queries
- `severity-{major|minor|patch}`
- `restates-history` — only when true
- `source-{merge|manual}`
- `channel-{name}` — one per affected channel

### API notes to verify first

Reports from 2024–2025 indicate two constraints. **Both need confirming against current behaviour before building** — Atlassian may have closed these gaps.

1. Using a folder ID as `parentId` when creating a page returns a 500. Workaround: create the page normally via `POST /wiki/api/v2/pages`, then move it into the folder using the **v1 move-page endpoint**.
2. The v2 folder API offers only create, get-by-ID, and delete. There is no list-children or list-folders endpoint, so the idempotency check must query by label and title via CQL rather than traversing the folder.

If you are on Confluence **Server or Data Center**, folders do not exist. Use a parent page with child pages instead — the design is otherwise identical, and page-as-parent has no API wrinkle.

---

## `publish.py`

Single entry point used by both workflows. Takes the parsed block as input.

**Steps:**

1. Resolve version — query by label for the most recent entry, increment if not supplied (essential for manual entries, which have no tag or PR to derive from).
2. Idempotency check — CQL search for an existing page with this version. Skip and exit 0 if found.
3. Render storage-format body from the schema fields.
4. `POST /wiki/api/v2/pages` — create in the space.
5. v1 move endpoint — relocate into the folder.
6. Apply labels.
7. `POST` Teams webhook.

**Teams card contents** — deliberately short. Version, one-line summary, severity, whether history was restated, and the page link. The changelog holds the detail; the alert is a pointer.

Build and test this against a scratch folder before wiring any workflow to it.

---

## Workflows

### `changelog-validate.yml`

- Triggers: `pull_request` on `opened`, `edited`, `synchronize`
- Path filter: model directories only
- Parses the YAML block from the PR body, checks required fields, date parseability, severity enum, and that `restated_back_to` is present when `restates_history` is true
- Fails on missing or malformed block
- Set as a **required status check** in branch protection

`edited` matters — without it, adding the block after a red check does not re-run.

### `changelog-publish.yml`

- Trigger 1: `pull_request: closed`, guarded on `github.event.pull_request.merged == true`, path-filtered
- Trigger 2: `workflow_dispatch` with the schema fields as inputs
- Both read into the same payload shape and call `publish.py`

Using `pull_request: closed` rather than `push` means the PR body is handed to you directly, with no need to work backwards from a commit.

---

## The skill

`SKILL.md` frontmatter description determines whether it ever fires — it is the only part loaded up front. Something like:

> Use when writing or reviewing an attribution model changelog entry, classifying change severity, drafting the stakeholder notification, or logging a manual model change.

**Body contents:**

- The field schema and what each field means
- Severity classification with concrete Emma examples
- House phrasing for impact statements, so wording stays consistent across authors
- Teams message format and length ceiling
- **Uncertainty handling** — if the diff does not reveal whether historical data is reprocessed, say so and ask. A confidently wrong restatement flag is worse than a blank one.
- The two entry paths, and the instruction to ask more questions on the manual path since there is no diff to read

---

## Secrets

| Secret | Used by |
|---|---|
| `CONFLUENCE_BASE_URL` | publish |
| `CONFLUENCE_EMAIL` | publish |
| `CONFLUENCE_API_TOKEN` | publish |
| `CONFLUENCE_SPACE_ID` | publish |
| `CONFLUENCE_FOLDER_ID` | publish |
| `TEAMS_WEBHOOK_URL` | publish |
| `ANTHROPIC_API_KEY` | only if auto-drafting in CI is added later |

Consider putting these in a GitHub environment with required reviewers if you want a human gate before anything posts.

---

## Build order

1. **`publish.py` against a scratch folder.** Confirm create-then-move works, labels apply, Teams card renders. Verify the two API constraints above. Nothing else is worth building until this is solid.
2. **Merge trigger.** Wire `changelog-publish.yml` on `pull_request: closed`.
3. **`workflow_dispatch`.** Same workflow, form inputs.
4. **Validation check.** Add `changelog-validate.yml`, then make it required in branch protection.
5. **PR template.** Empty YAML block so authors are prompted rather than having to recall the schema.
6. **The skill.** Highest value for adoption, least load-bearing — so it should not block the pipeline working.

---

## Known gaps

**Coverage.** Only repo-borne changes are captured automatically. UI retunes, spreadsheet channel mappings, and upstream platform changes need the manual path. If manual entries stop happening, the changelog quietly becomes incomplete and people stop trusting it — worth reviewing the `source-manual` label count periodically.

**Batching.** Two merges close together produce two entries and two Teams pings. Acceptable at low merge frequency. If the repo sees several model merges a week, revisit and consider tag-driven publishing instead.

**The impact estimate.** The most valuable field and the easiest to skip. The skill exists largely to reduce that friction, but no automation can supply the judgment — someone has to actually think about which channels move.

---

## Open questions

1. **Confluence Cloud or Server/Data Center?** Determines folder vs parent page, and which API surface the script targets.
2. **Which space** does the folder live in?
3. **Teams routing** — one channel for everything, or severity-based (major to a broad stakeholder channel, minor and patch to a working channel)?
4. **Merge frequency** on the attribution repo — determines whether per-merge entries stay comfortable.
