# Attribution Model — Documentation

This is the reference doc for the Claude + MCP POC: it should let Claude answer both "what happened" (numbers) and "why" (methodology) questions grounded in how this model actually works, not generic MTA theory.

---

## 1. Overview

A multi-touch attribution (MTA) model. For every customer journey that ends in an order, it splits credit for that order across the marketing touchpoints the customer interacted with beforehand, and writes the result to Redshift. It runs in three modes:

- **Short run** — daily, 7-day lookback. Covers every country every day.
- **Long run** — weekly, 100-day lookback. Covers a rotating subset of countries each day of the week (full explanation in §5).
- **Train run** — retrains the core model, per country, roughly twice a week.

---

## 2. Terminology glossary

| Term | Meaning |
|---|---|
| **Touchpoint (TP)** | One tracked interaction in a customer's journey before conversion — has a source, medium, campaign, keyword, and a position (first/mid/last). |
| **Path / journey** | The ordered sequence of touchpoints for one converting customer, ending in one conversion. |
| **Conversion** | A completed order, matched by order ID. |
| **Artificial touchpoint** | A touchpoint the model inserts manually because the real interaction wasn't trackable by GA4 (e.g. an influencer coupon code, a leaflet code, a "previous conversion" marker, a synthetic "direct" touchpoint for CRM-only journeys). Flagged by `is_artificial_touchpoint = true` in the output. |
| **(direct)/(none)** | GA4's label for a session where the traffic source couldn't be determined. Handled specially — see §4.2. |
| **Branded / TM touchpoint** | A touchpoint from a trademark search term (the customer searched "Emma mattress" rather than "mattress"). |
| **Top-Level model** | A separate, standalone attribution model (currently only for TV) that estimates a channel's contribution by working backward from direct/branded/organic order volume, rather than from tracked touchpoints. |
| **Top-5** | A specific set of high-traffic coupon codes treated with their own weighting logic (see §3.3). |
| **SMAD** | Internal name for the daily channel/business-unit/customer-type attribution rollup table (`refactored_pre_smad_prod`) — the level most dashboards consume. |
| **Rank** | In the touchpoint-level output table, distinguishes different runs' results for the same path (rank 0 = most recent). See §6.1. |
| **Scaling factor** | A correction multiplier applied to a channel's raw numbers — either to correct for platform over/under-reporting (paid social) or to account for touchpoints removed during preprocessing (TV redistribution). |
| **Adstock** | The delayed/carryover effect of an ad exposure on later behavior, as opposed to its immediate effect. Modeled only for paid social MMM output. |
| **AOV** | Average order value — used for outlier-clipping platform data. |
| **EDP** | Referenced throughout configs as an `is_edp` flag; not defined in code/docs. **Unconfirmed** — treat as an internal environment/platform designation, don't state a definition to end users with confidence. |

---

## 3. Core attribution method

### 3.1 The model: logistic regression on GA4 data
Trained per country, roughly twice weekly, on GA4 session/conversion data. It doesn't learn one weight per touchpoint — it learns weights for the **role** a touchpoint plays:

- coefficient for being the **first** touchpoint in the journey
- coefficient for being a **mid** touchpoint (note: *every* touchpoint counts as a mid touchpoint, including the first and last — so first/last touchpoints get their position-specific coefficient **plus** the mid coefficient, which is how the model gives them extra weight without a separate "boost" parameter)
- coefficient for being the **last** touchpoint
- coefficient for **session duration** (0 if the touchpoint has no session duration)

At attribution time, each specific touchpoint (e.g. `DE/google/cpc/(DE)<25_sfr>[search-generic]{eb}: slatted frame lattenrost/135477757150/lattenrost 140x200`) needs a matching learned coefficient. If that exact combination wasn't seen often enough during training, the model **falls back to a coarser version of the same touchpoint** — drop the keyword, then the ad group, then the campaign — until it finds a coefficient that exists. If nothing matches even at the coarsest level, it falls back to the direct-touchpoint coefficient. This hierarchical fallback is why two touchpoints with the same channel/source can get different credit: one had enough training volume to be scored specifically, the other didn't.

### 3.2 Turning coefficients into a percentage split
1. All coefficients for a touchpoint (first/mid/last + session duration, as applicable) are summed.
2. Within a path, the lowest resulting coefficient is shifted so it floors at **1** — this only happens for paths where a coefficient falls below that threshold. This avoids ever attributing negative credit to a touchpoint.
3. Coefficients are normalized to sum to 1 across the path — that becomes each touchpoint's attributed order share.

The floor of 1 was chosen experimentally against a synthetic dataset. It's a knob, not an arbitrary constant: a lower floor (e.g. 0.001) lets the learned differences between touchpoints dominate the split (higher variance, more risk of overfit-looking attribution); a higher floor (e.g. 100) pushes the outcome toward an even split regardless of what the model learned. 1 was picked as a middle ground. Because this operates in log-odds space, shifting by a constant doesn't distort the *relative* ratios between touchpoints the way it would in linear space.

### 3.3 Non-GA4 channels
These channels can't be scored by the core logistic regression because they don't produce trackable GA4 sessions, so each has its own coefficient generation, deliberately built to land in the same numeric range as the logistic regression's output:

- **Influencer**: `p = order_count / engagement_rate`, coefficient `= log(p/(1-p)) / log(p_median/(1-p_median))` — i.e. normalized against the median influencer's log-odds. Where engagement rate is missing (scraped CreatorIQ data is incomplete), it's estimated via a small linear regression of engagement rate on reach. *Known issue flagged in the docs*: this may currently use CreatorIQ metrics captured after the activity date, i.e. future data leaking into a past estimate — worth caveating in any Claude answer about influencer numbers.
- **Leaflet**: same log-odds idea, but reach is first rescaled through the CDF of a Poisson(λ=35) distribution before computing `p`, since raw leaflet reach estimates are considered less reliable than influencer reach.
- **Top-5 coupons**: no separate coefficient model — instead, the existing logistic-regression coefficients for Top-5 touchpoints are weighted by how often each one appeared in GA4 sessions over the prior 100 days, then averaged into a single coefficient applied to the artificial Top-5 touchpoint.
- **TV (Top-Level model)**: a wholly separate model (documented externally in Confluence, not in this repo) that estimates what fraction of direct/branded/organic order volume should actually be credited to TV. Because this model works "top-down" from aggregate order counts rather than per-touchpoint, it's structurally different from everything else in this document.
- **Checkout Poll (Radio, Billboards/OOH)**: survey answers at checkout ("how did you hear about us") are used as attribution directly. If the most recent recorded spend for that channel is more than 90 days old, its checkout-poll answers are zeroed out — the assumption is that if no one's spent money on the channel in 3 months, a customer citing it is likely misremembering or citing a channel with no live campaign, so it shouldn't take credit as if a campaign were still running.
- **Paid social (Facebook, YouTube, Pinterest, TikTok)**: NOT modeled by this repo's attribution logic at all — instead, the platform's own reported attributed orders/revenue are pulled directly (with a minimum 30-day query window and AOV-based outlier clipping) and rescaled with a per-country, per-channel scaling factor. Each platform has its own click/view attribution window baked into its own reporting:
  - Facebook Prospecting: 7-day click. Facebook Retargeting: 1-day click.
  - YouTube (Prospecting & Retargeting): 7-day engaged-view, 30-day click, 1-day view-through.
  - Pinterest Prospecting: 7-day click, 1-day view, 1-day engagement. Retargeting: not currently active.
  - TikTok (Prospecting & Retargeting): 7-day click.
  - Snapchat: included in aggregation but attribution-window terms not documented — flag as unconfirmed if asked.
  - **Paid social scaling, in detail**: the "per-country, per-channel scaling factor" above is actually two independent, hand-maintained config constants, not a formula computed from data. First, `top_level_channels[channel].scaling_factor` (a static multiplier per channel — e.g. YouTube 0.5, Meta 1.0, Pinterest 0.36, TikTok Prospecting 0.6/Retargeting 0.36, Snapchat 1.0, DTV 0.46 — with optional per-country overrides, e.g. Austria's DTV factor is 0.23) is applied as `final_orders = platform_reported_orders × (campaign_aov_clipped / direct_aov) × scaling_factor` — the platform's own order count is upscaled by the ratio of its AOV to the direct channel's AOV for that run, then the config constant is applied. None of these constants are derived by code — DTV's has an inline comment tracing it to an offline incrementality-test analysis; the rest have no derivation comment and only change if someone edits the config YAML. Second, a separate pair of static per-country multipliers (`cookie_scaling_factor`, `updated_scaling_factor`) is applied inside the platform data loaders themselves, correcting for cookie-consent-banner-era tracking loss — `cookie_scaling_factor` applies to all rows past a per-country cutoff date, `updated_scaling_factor` applies only to Prospecting rows past its own cutoff. Only the Facebook loader applies both; YouTube/TikTok/Pinterest/Snapchat apply only the cookie one. These two mechanisms don't share a function, but aren't fully independent either — the `direct_aov` used in the first formula is computed *after* TV's redistribution (§3.5) has already adjusted the direct channel's attribution for that run, so a change in TV's redistribution shifts the paid-social ratio too.

### 3.4 TV redistribution scaling, in detail
Two distinct "scaling factor" concepts sit under the TV/`staging_scaling_factors_prod` umbrella (§6.2.2), computed at different stages:
1. **Direct/branded/organic *adjustment* factors**, computed once per country/day and written to `staging_scaling_factors_prod` — nominally the ratio of touchpoints of that type remaining after preprocessing to the original count. In the current code, only `branded_scaling_factor` is actually computed this way; `direct_scaling_factor` and `organic_scaling_factor` are both hardcoded to `1`, with the real ratio computation present in the code but commented out. The table's own name overpromises for two of its three columns today.
2. **Direct/branded/organic *rescaling* factors**, computed from the external Top-Level TV model's output, never written to any table. The Top-Level model supplies `direct_percentage`/`organic_percentage`/`branded_percentage`/`tv_fraction` per country/day, read verbatim from a Redshift table this repo does not compute itself. Those percentages are first multiplied by the adjustment factors from (1); TV's order target is then `total_orders × tv_fraction`. That target is subtracted from direct/branded/organic order counts (each floored so no bucket loses more than 80% of its value), and the ratio of new-to-old order count per bucket becomes the rescaling factor, applied directly to touchpoint-level attribution to produce the TV-adjusted figure.

### 3.5 Why the model is architected this way
The core statistical model needs clean, high-volume tracked session data to learn from — that only exists for GA4-covered digital channels. Every other channel gets a purpose-built heuristic instead, but every heuristic is deliberately rescaled to sit in the same numeric range as the logistic regression's log-odds coefficients, so that "1.0 attributed order" means roughly the same thing regardless of which channel produced it. This is the single most important thing to convey when someone asks "why does channel X get attributed differently than channel Y" — it's not an inconsistency, it's a deliberate design choice driven by what data each channel actually produces.

---

## 4. What happens before attribution runs (preprocessing) — this explains a lot of "why" questions

Several touchpoints are deliberately removed or added to the raw GA4 data *before* the model ever scores anything. This is often the real answer to "why doesn't channel X show up" or "why is channel X's number lower than expected":

### 4.1 Removed
- **Post-conversion touchpoints** — anything happening after the order is dropped from that path.
- **Paths with excess/suspicious conversions** — some paths have data-quality issues causing implausibly many conversions; these are identified by fitting a power-law curve to conversion counts and dropping paths that fall below a probability threshold (with a floor of at least 10 orders per path, chosen heuristically, to avoid over-pruning).
- **(direct)/(none) touchpoints** — removed unless they're the *only* touchpoint in the path, because the source is genuinely unknown. This is intentional: removing them upfront means their credit naturally flows to whatever *other* tracked touchpoints exist in the journey, rather than needing a separate redistribution step later. Redistribution of leftover (direct)/(none) credit only becomes necessary for paths that had no other tracked touchpoint at all.
- **Last branded/trademark touchpoints** — removed because a customer searching your brand name is usually already at the bottom of the funnel and would have converted anyway. Incrementality testing showed organic search can substitute for brand search with little behavior change, i.e. brand search isn't very incremental.
- **Affiliate touchpoints at the end of long journeys (>3 touchpoints)** — for a similar bottom-of-funnel reason.
- **Consecutive newsletter touchpoints and transactional emails** (order confirmation, shipping updates) — these aren't marketing influence, they're operational noise.
- **Last organic-search touchpoints in journeys longer than 1** — treated the same way as branded search, on the belief its incrementality is similarly low.
- **Facebook, YouTube, Pinterest, TikTok touchpoints appearing in GA4** — removed because these channels are already being attributed directly from platform-native data (§3.3); leaving them in GA4 too would double count them.

### 4.2 Added
- **"Previous conversion" marker** — when a customer has multiple orders, their history is split into one path per order, and every path after the first gets an artificial touchpoint marking the prior conversion, enabling "back-attribution" context.
- **Artificial direct touchpoint for CRM-first journeys** — if a customer's first touchpoint is a newsletter/SMS/WhatsApp interaction, an artificial direct touchpoint is inserted before it, since a customer can't organically receive a newsletter without having visited the site first — the model treats the newsletter signup itself as evidence of an untracked prior visit.
- **Direct/none touchpoint for fully untracked orders** — a path with literally no tracked touchpoints (only the conversion) gets a direct touchpoint added so it has something to attribute to.
- **Artificial influencer/leaflet/Top-5 touchpoints** — inserted into any journey where the order used one of these coupon codes, following this priority: if the journey already has a touchpoint of that type, refine it with the more accurate coupon data; else if it has a (direct) touchpoint, replace it; else insert the artificial touchpoint at the start of the journey. (Top-5 differs slightly: if the journey already has a Top-5 touchpoint, it's left alone.)

### 4.3 TV redistribution mechanics (what actually lives in this repo)
The TV Top-Level model itself — the logic that decides what fraction of direct/branded/organic order volume "should" belong to TV — genuinely does not live in this repo; its output (`direct_percentage`/`organic_percentage`/`branded_percentage`/`tv_fraction`) is read as-is from a Redshift table this repo doesn't compute, with only a 28-day rolling-median smoothing step applied for the MMM variant. Nothing under this codebase computes those percentages from raw media/spend data.

What *does* live in this repo:
- **Pulling volume toward TV**: TV's order target (`total_orders × tv_fraction`) is subtracted from direct/branded/organic order counts (each floored at 20% of its original value); the exact amount pulled becomes a synthetic `Offline ## TV ## TV` touchpoint inserted into affected paths, carrying exactly the credit subtracted from the other three buckets — so the path's attribution still sums to 1. This is the TV-redistribution scaling mechanism described in §3.4.
- **Redistributing leftover `(direct)`/`(none)` credit for orphan paths** — the case §4.1 flags as needing explicit redistribution, distinct from the mechanism above. Paths where `(direct)`/`(none)` was the *sole* touchpoint survive preprocessing untouched and become pure-direct conversions. This leftover direct volume — after subtracting whatever non-TV top-level channels (paid social, DTV, OOH, Radio) already independently claimed — is split **proportionally to each remaining channel's current share of attributed net revenue** (channels already handled top-down, like TV/paid social, are excluded from the split). This is not a uniform split. One edge case: if a country's only revenue that day is untracked, all of it goes into a single "other online marketing spend" bucket instead of being split.
- **A third, unrelated redistribution** exists for Top5 coupon touchpoints — proportional to concurrent GA4 session counts by channel. Don't conflate this with the direct/none orphan-path mechanism above; it's Top5-specific.

---

## 5. Attribution windows and the country-cycling schedule

| Run | Lookback | Frequency |
|---|---|---|
| Short run | 7 days | Daily, every country |
| Long run | 100 days | Weekly per country (rotated across weekdays) |
| Train run | ~21 days by default, 7–56 days per country | ~Twice weekly per country |

The long run's 100-day recompute is too expensive to run for every market every day, so it's spread across the week — each weekday processes a different subset of countries, and every country gets its 100-day window refreshed once per week:

| Weekday | Countries |
|---|---|
| Monday | DE, AU, KR, CO |
| Tuesday | FR, PT, IE, CL |
| Wednesday | UK, ES, PH, MX |
| Thursday | NL, AT, JP, CA |
| Friday | BR, IT, IN |
| Saturday | CH-DE, CH-FR, BE-FR, BE-NL |
| Sunday | TW, HK |

This means: if someone asks about a *daily* number, it always reflects the most recent 7-day window regardless of country. If someone asks about a number that depends on the 100-day backfill (e.g. "has this been corrected for late-arriving data"), the answer depends on which day of the week that country's long run last executed.

---

## 6. Output — what's in Redshift and what each thing means

### 6.1 Touchpoint-level table (`refactored_attribution_prod`)
The finest-grained output — one row per touchpoint per converting path. Unlike the other tables, this one is **not overwritten** on each run; every run's results are appended, with a `rank` column added afterward (rank 0 = most recent, based on `attribution_timestamp`). This means the same path can appear multiple times across different runs as the model's estimate for it gets updated (e.g. once more data arrives in the 100-day backfill). **When answering a question against this table, always filter to rank = 0 unless the question is specifically about how an estimate changed over time.**

Also note: `attributed_net_revenue` is deliberately set to null in this table for legacy reasons tied to downstream rescaling logic in the orchestration layer — net_revenue-based questions at touchpoint grain should be answered with caution, or redirected to the daily rollup tables where attributed_net_revenue is populated.

If a run is interrupted partway through, this table can end up with duplicate/unfixed ranks, since the ranking fix-up runs only at the very end of a full run.

### 6.2 Daily rollups
- **`refactored_pre_smad_prod`** (SMAD) — one row per country/day/channel/business unit/customer type/attribution model, with `attributed_orders` and `attributed_net_revenue`. This is the level most dashboards actually query, and the right table for "how much revenue did channel X attribute to new vs. returning customers."
- **`refactored_breakdown_prod`** — one row per country/day/channel, showing what fraction of that channel's credit came from direct tracking vs. TV top-level modeling vs. coupon codes vs. GA4. This is the table to use when someone asks "why does this channel's number look off" — it shows the *composition* of the number, not just the total.

See §6.2.1–6.2.4 below for the four other daily-rollup tables, documented in more depth.

#### 6.2.1 `refactored_total_orders_prod`
One row per `country_store_code`/`conversion_date`. Wide/pivoted: `direct_orders`, `tv_orders`, then per-platform Prospecting/Retargeting/Top5-Prospecting/Top5-Retargeting columns for YouTube, Facebook, Pinterest, TikTok, Snapchat, plus `ooh_orders`, `radio_orders`, `print_orders`, `dtv_orders`. Built once per country/day during TV postprocessing, pushed by the short/long run (long run delegates to short run). Overwrite-by-replace: the existing table is read back, new rows win on `(country_store_code, conversion_date)` collision via dedup, then the whole table is dropped and rebuilt. **Caveat**: `print_orders` is hardcoded to `0` for every row — there's no data source feeding it despite the column existing. A separate MMM-multi-channel variant of this table only gets rows for countries flagged for that treatment.

#### 6.2.2 `staging_scaling_factors_prod`
One row per `country_store_code`/`attribution_date`: `direct_scaling_factor`, `branded_scaling_factor`, `organic_scaling_factor`. Built inline in the short run, pushed the same overwrite-by-replace way as the total-orders table. **Caveat (important for any answer using this table)**: only `branded_scaling_factor` is currently a real computed ratio; `direct_scaling_factor` and `organic_scaling_factor` are both hardcoded to `1` in the current code, with the real ratio calculation present but commented out (see §3.4). A question like "how much was direct/organic rescaled for TV" cannot be answered from this table's `direct_scaling_factor`/`organic_scaling_factor` columns today — they're constants, not live data. Only `branded_scaling_factor` reflects the touchpoint-removal ratio the table's name implies.

#### 6.2.3 `refactored_paid_social_prod`
Intended grain is one row per `country_store_code`/`conversion_date`/`channel_full`/`mmm_campaign_type`, covering adstock vs. non-adstock attributed orders/revenue plus raw platform spend/impressions/clicks and platform-reported orders/revenue. Restricted to Prospecting and Top5-Prospecting paid-social channels only (Retargeting is excluded by design). Overwritten the same way as the other tables above, but the dedup/replace key used only covers `(country_store_code, conversion_date)`, not channel/campaign-type — it relies on each push batch containing the complete set of rows for that country/date rather than keying per-row. **Caveats directly from code comments**: missing MMM or platform data for a country/date is handled by filling with 0 and coercing dtypes, rather than leaving nulls or skipping the row — so a 0 in this table can mean "genuinely zero" or "no MMM/platform output was available," and the table doesn't distinguish the two. The table is skipped entirely (not written) for a run with no MMM-eligible rows at all.

#### 6.2.4 `refactored_attribution_metrics_prod`
**Not currently populated by any run**, despite existing as a real table in the schema. Per its design, it would hold one row per country/model-training run: `country_store_code`, `model_type` (always `"logistic_regression"`), `model_name`, `attribution_date`, `attribution_week`/`attribution_year`, `model_timestamp`, and train/test cross-validation scores (`accuracy`, `balanced_accuracy`, `roc_auc`, `f1`, in train/test pairs). In practice, both call sites needed to populate it are currently commented out in the codebase. **If asked "how good is the current model," the correct answer is that this table is not currently populated — not that it's simply unavailable in this POC** (contrast with the genuinely-not-mocked-but-real-and-live tables above).

### 6.3 What's *not* in Redshift
The trained logistic regression coefficients themselves live in S3 as JSON, one file per country per training date, not in any Redshift table. If someone asks "what are the current model weights for channel X," that's not answerable from the mock/Redshift data — it would require a separate tool reading from S3.

### 6.4 Notification/monitoring
After each run, a summary (and error log, if applicable) is posted to an internal MS Teams channel, and a downstream Matillion job is triggered. Not relevant to the MCP tool itself, but useful context if someone asks "how would I know if today's numbers are wrong" — the answer is the Teams summary, not something queryable in Redshift.

---

## 7. Worked example — how one path gets its attribution

Illustrative only (constructed to match the documented logic, not pulled from real data), useful for explaining the mechanism concretely.

A customer's path after preprocessing: `google/cpc` (first) → `newsletter` (removed — see §4.1, if the model treats it as noise) → `direct` (mid, removed since not the only touchpoint) → `google/organic` (last, but removed as last-organic-in-journey>1 per §4.1) → conversion.

After preprocessing strips the (direct) and last-organic touchpoints, the path reduces to a single touchpoint: `google/cpc`. Since only one touchpoint remains, no coefficient math is needed — it gets **100% of the order's credit** by the single-touchpoint rule (`get_single_touchpoint_attribution`).

Now contrast with a path that survives preprocessing with 3 touchpoints: `google/cpc` (first) → `facebook/paid-social` (removed, §4.1 — attributed separately) → `influencer/coupon` (mid, artificial) → `google/cpc` (last, same campaign as first) → conversion.

After removing the Facebook touchpoint (handled outside this model), the path is: `google/cpc` (first), `influencer/coupon` (mid), `google/cpc` (last).
1. `google/cpc` gets its first-touchpoint coefficient + mid coefficient (since first counts as mid too) + session duration coefficient.
2. `influencer/coupon` gets its (rescaled, per §3.3) influencer coefficient as a mid coefficient.
3. The last `google/cpc` gets its last-touchpoint coefficient + mid coefficient + session duration coefficient.
4. All three raw scores are compared; the lowest is shifted so it floors at 1, then all three are normalized to sum to 1 — e.g. resulting in something like 0.45 / 0.15 / 0.40 attributed order share respectively.

The exact numeric split can't be reproduced without the actual trained coefficients (stored in S3, not in this repo) — but the *mechanism* above is exactly how any real path is scored.

---

## 8. Data-quality caveats worth surfacing proactively

- **Multiple estimates per path**: because the touchpoint table isn't overwritten, a query without a rank filter will double- or triple-count paths that were re-attributed across runs.
- **`attributed_net_revenue` is null at touchpoint grain** — a legacy artifact of downstream rescaling in Matillion, not a data quality bug, but will confuse revenue questions if not called out.
- **Influencer engagement-rate estimation may leak future data** — flagged directly in the model's own docs as a known open issue.
- **90-day cutoffs** apply independently to two different things — checkout-poll-based channels (Radio/OOH) lose their attribution after 90 days of no recorded spend, and Top-5 coefficient weighting looks at a 100-day session window. Don't conflate the two when explaining "why did this channel's number change."
- **Country-cycling means "freshness" varies by question type** — a short-run (7-day) number is always current; a long-run (100-day, backfill-corrected) number is only as fresh as that country's last scheduled weekday (§5).
- **CreatorIQ (influencer) data is scraped**, not an official API — noted in the model's own docs as "not fully reliable."
- **Interrupted runs can leave stale/duplicate ranks** in the touchpoint table (§6.1) — if numbers look duplicated, this is the first thing to check, not a modeling error.
- **`refactored_attribution_metrics_prod` is not currently populated** — the code paths that would write model-quality metrics to it are commented out (§6.2.4). Don't imply this table has live data just because it exists in the schema.
- **Two of `staging_scaling_factors_prod`'s three columns are hardcoded constants, not live computations** — `direct_scaling_factor`/`organic_scaling_factor` are both `1` today; only `branded_scaling_factor` reflects a real ratio (§3.4, §6.2.2).

---

## 9. Question → table cheat sheet (for the MCP tool's query routing)

| Question type | Table(s) |
|---|---|
| "How many orders/how much revenue did channel X get on date Y in country Z?" | `refactored_pre_smad_prod` (has attributed_orders + attributed_net_revenue) or `refactored_total_orders_prod` for the wide per-channel view |
| "Why did channel X's number look the way it did?" (composition) | `refactored_breakdown_prod` |
| "Show me the actual touchpoints in a customer's journey" | `refactored_attribution_prod`, filtered to `rank = 0` |
| "How does new vs. returning customer attribution differ?" | `refactored_pre_smad_prod`, grouped by `customer_type` |
| "How much of TV's number came from direct/branded/organic redistribution?" | `staging_scaling_factors_prod` + `refactored_breakdown_prod`, but `staging_scaling_factors_prod`'s direct/organic columns are hardcoded to 1, not live (§6.2.2) — only branded is real; mechanism itself is §3.4/§4.3 |
| "What's paid social's adstock vs. immediate contribution?" | `refactored_paid_social_prod` |
| "How good is the current model?" | `refactored_attribution_metrics_prod` — but currently not populated by any run (§6.2.4); answer should say so, not just that it's unmocked in this POC |
| "What are the model's actual learned weights?" | Not in Redshift — S3 JSON, out of scope for this POC's mock data unless explicitly added |
| "Why does channel X get treated differently than channel Y methodologically?" | Not a data question — answer from §3 (methodology) directly |
| "Why is a touchpoint missing/removed from a journey?" | Not a data question — answer from §4 (preprocessing rules) directly |

---

## 10. POC scope note

This doc is meant to back two things in the MCP server: (1) query tools over mock tables matching §6's schema, and (2) a "methodology" tool that can quote §2–§5 and §8 directly when a question is about *why*, not *what*. Redshift access itself is a separate, non-blocking parallel track (get schema-scoped read-only access, decide IAM vs. secrets-manager auth, confirm network path) — not covered in depth here since it doesn't affect what Claude needs to know to answer questions.
