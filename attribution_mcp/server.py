"""MCP server exposing mock attribution model tables + methodology docs.

Mock data stands in for Redshift (see attribution_poc_plan.md, parallel
Redshift-access track). Schema and methodology are pulled from the real
attribution-model-revamp repo and recorded in attribution_model_documentation.md
-- this server should not invent facts about the model beyond that doc.
"""

import json
import re
from pathlib import Path

from mcp.server.fastmcp import FastMCP

DATA_DIR = Path(__file__).parent / "data"
DOC_PATH = Path(__file__).parent.parent / "attribution_model_documentation.md"

mcp = FastMCP("attribution-poc")


def _load_table(name: str) -> list[dict]:
    path = DATA_DIR / f"{name}.json"
    return json.loads(path.read_text())


def _filter_rows(rows: list[dict], filters: dict) -> list[dict]:
    result = []
    for row in rows:
        if all(row.get(k) == v for k, v in filters.items() if v is not None):
            result.append(row)
    return result


@mcp.tool()
def query_touchpoints(
    country: str | None = None,
    date: str | None = None,
    order_id: str | None = None,
    touchpoint_source: str | None = None,
    rank: int = 0,
    limit: int = 50,
) -> list[dict]:
    """Query the touchpoint-level table (refactored_attribution_prod).

    One row per touchpoint per converting path. Defaults to rank=0 (most
    recent estimate per path) -- per the model docs, querying without a
    rank filter will double-count paths that were re-attributed across runs.
    attributed_net_revenue is always null at this grain (see docs section 6.1);
    use query_smad for revenue questions.
    """
    rows = _load_table("refactored_attribution_prod")
    filters = {
        "country": country,
        "order_id": order_id,
        "touchpoint_source": touchpoint_source,
        "rank": rank,
    }
    if date is not None:
        rows = [r for r in rows if r["attribution_timestamp"].startswith(date)]
    return _filter_rows(rows, filters)[:limit]


@mcp.tool()
def query_smad(
    country: str | None = None,
    date: str | None = None,
    channel: str | None = None,
    business_unit: str | None = None,
    customer_type: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Query the SMAD daily rollup table (refactored_pre_smad_prod).

    One row per country/day/channel/business_unit/customer_type/attribution_model,
    with attributed_orders and attributed_net_revenue. This is the table
    most "how many orders/how much revenue did channel X get" questions
    should use (see docs section 9).
    """
    rows = _load_table("refactored_pre_smad_prod")
    filters = {
        "country": country,
        "date": date,
        "channel": channel,
        "business_unit": business_unit,
        "customer_type": customer_type,
    }
    return _filter_rows(rows, filters)[:limit]


@mcp.tool()
def query_breakdown(
    country: str | None = None,
    date: str | None = None,
    channel: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Query the composition/breakdown table (refactored_breakdown_prod).

    One row per country/day/channel, showing what fraction of that
    channel's credit came from direct tracking vs. TV top-level modeling
    vs. coupon codes vs. GA4. Use this for "why does this channel's number
    look off" questions (see docs section 6.2).
    """
    rows = _load_table("refactored_breakdown_prod")
    filters = {"country": country, "date": date, "channel": channel}
    return _filter_rows(rows, filters)[:limit]


@mcp.tool()
def list_methodology_sections() -> list[str]:
    """List the section headings available in the attribution model methodology doc."""
    text = DOC_PATH.read_text()
    return re.findall(r"^##\s+(.+)$", text, flags=re.MULTILINE)


@mcp.tool()
def get_methodology(section: str | None = None) -> str:
    """Get the attribution model's methodology documentation.

    Pass a section heading (e.g. "3. Core attribution method", or a
    substring like "preprocessing") to get just that section, verbatim
    from attribution_model_documentation.md. Omit to get the full doc.
    Use this for "how does the model work" / "why" questions -- these are
    not answerable from the data tables alone.
    """
    text = DOC_PATH.read_text()
    if section is None:
        return text

    headings = list(re.finditer(r"^##\s+(.+)$", text, flags=re.MULTILINE))
    match_idx = None
    for i, h in enumerate(headings):
        if section.lower() in h.group(1).lower():
            match_idx = i
            break
    if match_idx is None:
        return f"No section matching '{section}' found. Use list_methodology_sections to see available sections."

    start = headings[match_idx].start()
    end = headings[match_idx + 1].start() if match_idx + 1 < len(headings) else len(text)
    return text[start:end].strip()


if __name__ == "__main__":
    mcp.run()
