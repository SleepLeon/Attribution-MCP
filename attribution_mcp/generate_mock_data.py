"""Generates mock fixtures for the POC's three core Redshift tables.

Schema/grain for each table is taken from attribution_model_documentation.md
section 6 (refactored_attribution_prod, refactored_pre_smad_prod,
refactored_breakdown_prod), not invented independently. This is mock data
standing in for real Redshift exports, not a simulation of the model itself
-- numbers are randomly generated, not run through the actual logistic
regression.
"""

import json
import random
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

# A representative sample of countries, one per weekday-cycling group (see
# doc section 5), so the mock data exercises the country-cycling schedule.
COUNTRIES = ["DE", "FR", "UK", "NL", "BR", "CH-DE", "TW"]

CHANNELS = [
    "direct",
    "google_organic",
    "google_cpc",
    "branded_search",
    "affiliate",
    "newsletter",
    "influencer",
    "leaflet",
    "top5_coupon",
    "tv",
    "youtube_prospecting",
    "youtube_retargeting",
    "facebook",
    "pinterest",
    "tiktok",
    "snapchat",
    "radio",
    "ooh",
    "print",
    "dtv",
]

BUSINESS_UNITS = ["mattresses", "bed_frames", "accessories"]
CUSTOMER_TYPES = ["new", "returning"]

DATES = [f"2026-06-{d:02d}" for d in range(1, 31)]

random.seed(42)


def gen_touchpoint_table():
    rows = []
    path_id_counter = 0
    for country in COUNTRIES:
        for date in DATES[-7:]:  # short-run 7-day lookback
            n_paths = random.randint(15, 40)
            for _ in range(n_paths):
                path_id_counter += 1
                path_id = f"{country}-{path_id_counter:06d}"
                order_id = f"ORD-{country}-{path_id_counter:06d}"
                n_touchpoints = random.choice([1, 1, 2, 3, 3, 4])
                touchpoints = []
                for i in range(n_touchpoints):
                    if i == 0:
                        position = "first"
                    elif i == n_touchpoints - 1:
                        position = "last"
                    else:
                        position = "mid"
                    channel = random.choice(CHANNELS)
                    is_artificial = channel in ("influencer", "leaflet", "top5_coupon", "direct") and random.random() < 0.3
                    touchpoints.append(
                        {
                            "position": position,
                            "channel": channel,
                            "is_artificial_touchpoint": is_artificial,
                        }
                    )
                # Random raw scores -> normalize to sum to 1, floored at a
                # small epsilon to mimic the "floor at 1 in log-odds space"
                # behavior described in doc section 3.2 (approximated here,
                # not reproducing real log-odds math).
                raw_scores = [max(0.05, random.gauss(1.0, 0.4)) for _ in touchpoints]
                total = sum(raw_scores)
                shares = [round(s / total, 4) for s in raw_scores]
                # fix rounding drift on the last share
                shares[-1] = round(1.0 - sum(shares[:-1]), 4)

                for tp, share in zip(touchpoints, shares):
                    rows.append(
                        {
                            "path_id": path_id,
                            "order_id": order_id,
                            "country": country,
                            "touchpoint_position": tp["position"],
                            "touchpoint_source": tp["channel"],
                            "touchpoint_medium": "paid" if "cpc" in tp["channel"] or tp["channel"] in ("facebook", "pinterest", "tiktok", "youtube_prospecting", "youtube_retargeting", "tv", "radio", "ooh", "print", "dtv") else "organic",
                            "touchpoint_campaign": f"{tp['channel']}_campaign_{random.randint(1, 5)}",
                            "is_artificial_touchpoint": tp["is_artificial_touchpoint"],
                            "attributed_order_share": share,
                            "attributed_net_revenue": None,  # null at touchpoint grain, see doc section 6.1
                            "attribution_timestamp": f"{date}T03:00:00Z",
                            "rank": 0,
                        }
                    )
    return rows


def gen_smad_table():
    rows = []
    for country in COUNTRIES:
        for date in DATES:
            for channel in CHANNELS:
                for bu in BUSINESS_UNITS:
                    for customer_type in CUSTOMER_TYPES:
                        if random.random() < 0.6:
                            continue  # sparsity: not every combo has volume every day
                        orders = round(random.gauss(20, 8), 2)
                        orders = max(0, orders)
                        aov = random.uniform(350, 900)
                        rows.append(
                            {
                                "country": country,
                                "date": date,
                                "channel": channel,
                                "business_unit": bu,
                                "customer_type": customer_type,
                                "attribution_model": "top_level" if channel == "tv" else "core_mta",
                                "attributed_orders": orders,
                                "attributed_net_revenue": round(orders * aov, 2),
                            }
                        )
    return rows


def gen_breakdown_table():
    rows = []
    for country in COUNTRIES:
        for date in DATES:
            for channel in CHANNELS:
                # Composition of a channel's credit source, per doc section 6.2:
                # direct tracking (GA4) vs TV top-level modeling vs coupon
                # codes vs GA4-derived. Weighted toward the mechanism that
                # actually produces that channel per doc section 3.3.
                if channel == "tv":
                    weights = [0.0, 0.95, 0.0, 0.05]
                elif channel in ("influencer", "leaflet", "top5_coupon"):
                    weights = [0.1, 0.0, 0.85, 0.05]
                elif channel in ("facebook", "pinterest", "tiktok", "youtube_prospecting", "youtube_retargeting", "snapchat"):
                    weights = [0.9, 0.0, 0.0, 0.1]
                else:
                    weights = [0.05, 0.0, 0.05, 0.9]
                noise = [max(0, w + random.uniform(-0.05, 0.05)) for w in weights]
                total = sum(noise) or 1.0
                pct_direct_tracking, pct_tv_topline, pct_coupon, pct_ga4 = [round(n / total, 4) for n in noise]
                rows.append(
                    {
                        "country": country,
                        "date": date,
                        "channel": channel,
                        "pct_direct_tracking": pct_direct_tracking,
                        "pct_tv_topline": pct_tv_topline,
                        "pct_coupon": pct_coupon,
                        "pct_ga4": pct_ga4,
                    }
                )
    return rows


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tables = {
        "refactored_attribution_prod": gen_touchpoint_table(),
        "refactored_pre_smad_prod": gen_smad_table(),
        "refactored_breakdown_prod": gen_breakdown_table(),
    }
    for name, rows in tables.items():
        path = DATA_DIR / f"{name}.json"
        path.write_text(json.dumps(rows, indent=2))
        print(f"wrote {len(rows)} rows to {path}")


if __name__ == "__main__":
    main()
