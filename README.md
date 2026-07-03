# Attribution-MCP
POC for attribution connection to Claude

See [attribution_poc_plan.md](attribution_poc_plan.md) for the overall plan and
[attribution_model_documentation.md](attribution_model_documentation.md) for the
real methodology/schema this POC is grounded in.

## Setup

```
poetry install
poetry run python attribution_mcp/generate_mock_data.py  # regenerate mock fixtures
```

## Run standalone (sanity check)

```
poetry run python -m attribution_mcp.server
```

This starts the MCP server on stdio and will just sit waiting for a client —
that's expected, it's not meant to print anything on its own.

## Connect to Claude Desktop

Add to your Claude Desktop config
(`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "attribution-poc": {
      "command": "poetry",
      "args": ["run", "--directory", "/Users/leonbrochmann/Documents/Code/Attribution-MCP", "python", "-m", "attribution_mcp.server"]
    }
  }
}
```

Restart Claude Desktop, then ask questions like:
- "How many orders did influencer marketing attribute in Germany last month?"
- "Why does TV get attributed differently than paid search?"
- "Show me the touchpoints for a specific converting path in France."
- "Why might a channel's attributed orders look lower than expected?"

## Tools exposed

- `query_touchpoints` — touchpoint-level table (`refactored_attribution_prod`)
- `query_smad` — daily channel/business-unit/customer-type rollup (`refactored_pre_smad_prod`)
- `query_breakdown` — composition of a channel's credit sources (`refactored_breakdown_prod`)
- `list_methodology_sections` / `get_methodology` — surfaces the real methodology doc for "why" questions

## Known POC limitations

- Data is randomly generated to match the real schema's *shape*, not run through the actual model — numbers are not meaningful, only structurally realistic.
- Only 3 of the 7 real output tables are covered (see `attribution_model_documentation.md` §6 for the rest).
- Redshift access itself is a separate, non-blocking track — see `attribution_poc_plan.md`.
