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
- `internal/azure_devops/` — Azure DevOps integration using the `azure-devops` Python SDK, split by concern:
  - `shared.py` — `_get_connection`/`_get_project`, used by both submodules below
  - `tasks.py` — Tasks/PBIs (board) integration; exposes `get_tasks`, `get_pbis`
  - `wiki.py` — Wiki integration; exposes `get_wiki_pages`, `get_wiki_page_by_path`, `get_wiki_page_by_id`
  - `cache.py` — local SQLite+FTS5 cache of wiki structure/content; exposes `sync_wiki_cache`, `search_wiki_cache`, `get_wiki_tree`, `get_wiki_cache_status`
  - `__init__.py` re-exports all nine functions, so callers still do `from internal.azure_devops import ...`

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
| `POST /azure/wiki/cache/sync` | `sync_azure_devops_wiki_cache` | Rebuild the local cache for one wiki (structure + content) |
| `GET /azure/wiki/cache/search` | `search_azure_devops_wiki_cache` | Full-text search over the cached wiki (FTS5) |
| `GET /azure/wiki/cache/tree` | `get_azure_devops_wiki_cache_tree` | Get the cached page hierarchy as a nested tree (no API calls) |
| `GET /azure/wiki/cache/status` | `get_azure_devops_wiki_cache_status` | Get cache stats (page count, last sync) per wiki |

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
- Both page-lookup endpoints return `wiki_id`, `wiki_name` (null unless resolved from a listed wiki), `page_id`, `path`, `content`, `is_parent_page`, `order`, `url`, `sub_pages`, and `sub_pages_truncated`.

**Wiki subpages** (`/azure/wiki/page`, `/azure/wiki/page/{page_id}`): if a page has children, `sub_pages` recursively nests every descendant (with its own content and `sub_pages`), mirroring the wiki's hierarchy. Azure DevOps' `recursionLevel=full` only returns descendant paths, not content or IDs, so each descendant's content is fetched with a separate `get_page` call. Capped at `MAX_SUBPAGES_FETCHED` (50, in `internal/azure_devops/wiki.py`) total descendants per request; if the cap is hit, `sub_pages_truncated` is `true` and the remaining descendants at that point in the tree are omitted.

**Wiki pagination** (`/azure/wiki`): response shape is `{"pages": [...], "continuation_token": ...}`. Pass `top` and `continuation_token` (from a previous response) to page through a single wiki's pages — this only works when `wiki_id` is set, since Azure DevOps continuation tokens are per-wiki. When `wiki_id` is omitted (listing all wikis), `continuation_token` is always `null` and each wiki returns up to `top` pages with no further pagination.

**Wiki cache** (`internal/azure_devops/cache.py`): a local SQLite database (`data/wiki_cache.db` by default; override with `WIKI_CACHE_DB_PATH`) caching wiki structure and content for full-text search, entirely separate from the live `/azure/wiki*` endpoints above (those still always hit the API — the cache is purely additive).
- `sync_azure_devops_wiki_cache` (`wiki_id` required, `fetch_content` default `true`) fully replaces that wiki's cached rows: paginates through every page via `GetPagesBatch`, then (if `fetch_content`) fetches each page's content individually — there's no bulk-content API, so this is one call per page and can take minutes on large wikis (417 pages ≈ 2 minutes in testing). The cache starts empty; nothing else here works until this is called at least once.
- Schema: `wiki_pages` (`wiki_id`, `page_id`, `path`, `parent_path`, `depth`, `content`, sync timestamps) plus an external-content `wiki_pages_fts` FTS5 table over `(path, content)`, rebuilt via `INSERT INTO wiki_pages_fts(wiki_pages_fts) VALUES ('rebuild')` after each sync (no triggers — the whole table is replaced per sync, not updated incrementally).
- `search_azure_devops_wiki_cache` takes an FTS5 `MATCH` query (phrases in quotes, `AND`/`OR`/`NOT`, `prefix*`) and returns ranked results with snippets.
- `get_azure_devops_wiki_cache_tree` rebuilds the hierarchy from cached `parent_path` values with zero API calls — reflects the state as of the last sync, not live data.
- `get_azure_devops_wiki_cache_status` reports page count / pages-with-content / last sync time per wiki, useful for checking staleness before relying on search or tree results.
