# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the server (HTTP + MCP combined on localhost:9876)
python main.py

# Run with uvicorn directly
uvicorn services.mcp:combined_app --host localhost --port 9876 --reload
```

There are no tests or lint commands configured.

## Architecture

This project exposes a Swagger/OpenAPI parser as both a REST API and an MCP (Model Context Protocol) server on the same port.

**Entry point:** `main.py` → runs `services.mcp:combined_app` on `localhost:9876`

**Layer breakdown:**

- `services/params.py` — defines `swagger_version` enum (`v1`, `v2`), the only shared type
- `internal/main.py` — core logic: fetches Swagger JSON URLs from env vars, resolves `$ref`s via `jsonref`, and exposes three functions: `get_enums`, `get_paths`, `get_modules`
- `services/main.py` — FastAPI app wrapping the three internal functions as REST endpoints (`/{version}/enums`, `/{version}/modules`, `/{version}/paths/{module_name}`), plus Azure DevOps endpoints
- `services/mcp.py` — uses `FastMCP.from_fastapi()` to auto-generate an MCP server from the FastAPI app, then merges both into a single `combined_app` (FastAPI with both route sets and the MCP lifespan)
- `internal/azure_devops.py` — Azure DevOps integration using the `azure-devops` Python SDK; exposes `get_tasks`, `get_pbis`, `get_wiki_pages`, `get_wiki_page_by_path`, and `get_wiki_page_by_id`

**Environment variables** (`.env`):
- `SWAGGER_JSON_V1_URL` — URL to v1 Swagger JSON
- `SWAGGER_JSON_V2_URL` — URL to v2 Swagger JSON
- `AZURE_DEVOPS_ORG_URL` — Azure DevOps organization URL (e.g. `https://dev.azure.com/YOURORG`)
- `AZURE_DEVOPS_PAT` — Personal Access Token for authentication
- `AZURE_DEVOPS_PROJECT` — Project name or ID

**Module name extraction** (`get_module_names`): paths are parsed as `/{prefix}/{version}/{module}/...`; if the third segment is `admin`, the module name becomes `admin/{fourth_segment}`.

**MCP transport:** served over HTTP at `/mcp` (streamable HTTP, not stdio).

## Azure DevOps Endpoints

All endpoints are under `/azure/` and auto-exposed as MCP tools.

| Endpoint | Operation ID | Description |
|---|---|---|
| `GET /azure/tasks` | `get_azure_devops_tasks` | Fetch Tasks |
| `GET /azure/pbis` | `get_azure_devops_pbis` | Fetch Product Backlog Items |
| `GET /azure/wiki` | `get_azure_devops_wiki_pages` | List wiki pages (metadata only: `page_id`, `path` — no content) |
| `GET /azure/wiki/page` | `get_azure_devops_wiki_page_by_path` | Fetch a wiki page's content by `path` |
| `GET /azure/wiki/page/{page_id}` | `get_azure_devops_wiki_page_by_id` | Fetch a wiki page's content by `page_id` |

**Shared query params for `/azure/tasks` and `/azure/pbis`:**
- `id` — fetch a single item by work item ID
- `assignee` — substring match on display name
- `team` — sprint board team name (scopes `@CurrentIteration` to the right team)
- `current_sprint` — boolean; filters by `@CurrentIteration` (takes priority over `sprint`)
- `sprint` — substring match on iteration path
- `state` — e.g. `Active`, `New`, `Closed`
- `top` — max results (default 100)

**Task response fields include `parent_id`** (`System.Parent`) — the ID of the parent PBI, or `null` if unset.

**Wiki endpoints:**
- `/azure/wiki` accepts an optional `wiki_id` (ID or name); if omitted, all wikis in the project are listed.
- `/azure/wiki/page` and `/azure/wiki/page/{page_id}` accept an optional `wiki_id`; if omitted, it defaults to the project's default wiki (name == project name, the standard Azure DevOps convention).
- Both page-lookup endpoints return `wiki_id`, `wiki_name` (null unless resolved from a listed wiki), `page_id`, `path`, `content`, `is_parent_page`, `order`, and `url`.
