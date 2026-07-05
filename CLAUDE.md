# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the server (HTTP + MCP combined on localhost:9876)
python main.py

# Run with uvicorn directly
uvicorn services.app:combined_app --host localhost --port 9876 --reload
```

There are no tests or lint commands configured.

## Architecture

This project exposes Swagger/OpenAPI parsing and Azure DevOps integration through two independent surfaces on the same port: a pure MCP (Model Context Protocol) server (Tools/Resources/Prompts) and a hand-written REST API. Neither is derived from the other.

**Entry point:** `main.py` → runs `services.app:combined_app` on `localhost:9876`

**Layer breakdown:**

- `services/params.py` — defines `swagger_version` enum (`v1`, `v2`), the only shared type
- `internal/swagger/` — core Swagger logic, split by concern:
  - `client.py` — `get_swagger_json_url` (reads the version's URL from env vars), `load_json` (fetches + resolves `$ref`s via `jsonref`)
  - `parser.py` — `show_enums`, `show_paths`, `get_module_names` (pure functions over already-resolved Swagger JSON)
  - `__init__.py` composes the two into the three public functions: `get_enums`, `get_paths`, `get_modules`
- `internal/azure_devops/` — Azure DevOps integration using the `azure-devops` Python SDK, split by concern:
  - `shared.py` — `_get_connection`/`_get_project`, used by both submodules below
  - `tasks.py` — Tasks/PBIs (board) integration; exposes `get_tasks` (accepts an optional `parent_id` filter), `get_pbis`
  - `wiki.py` — live Wiki API calls; exposes `get_wiki_pages`, `get_wiki_page_by_path`, `get_wiki_page_by_id`
  - `wiki_sync.py` — orchestrates cache rebuilds and staleness checks: fetches pages/content from the Azure API (via `wiki.py`'s `_get_pages_batch_page`) and persists them via `internal.db.replace_wiki_pages`; exposes `sync_wiki_cache` (full/bootstrap resync), `check_and_refresh_wiki_cache` (TTL-gated incremental refresh), `ensure_wiki_cache_fresh` (best-effort wrapper called before cache reads), and `sync_all_wikis_on_startup`. This is the only module that talks to both the Azure API and the SQLite cache — `wiki.py` never touches SQLite and `internal/db/` never calls Azure. See [Wiki Cache Internals](docs/wiki-cache.md) for the full incremental-sync algorithm.
  - `__init__.py` re-exports `get_tasks`, `get_pbis`, `get_wiki_pages`, `get_wiki_page_by_path`, `get_wiki_page_by_id`, `sync_wiki_cache`, `check_and_refresh_wiki_cache`, `ensure_wiki_cache_fresh`, `sync_all_wikis_on_startup`
- `internal/db/` — generic SQLite+FTS5 persistence layer for the wiki cache, with zero Azure API knowledge:
  - `connection.py` — `_get_db_connection` (path from `WIKI_CACHE_DB_PATH` env var, default `data/wiki_cache.db`), schema creation (idempotent migrations for `git_item_path`/`content_modified_at` columns added after the initial release)
  - `wiki_repository.py` — `replace_wiki_pages` (bulk replace for one wiki, sorts shallowest-first internally to resolve `parent_id`), `search_wiki_cache`, `get_wiki_tree`, `get_wiki_subtree`, `get_wiki_cache_status`, `get_cached_wiki_pages`, `get_all_cached_wiki_ids`, `get_wiki_cache_last_checked_at`, `record_wiki_cache_check`
  - `__init__.py` re-exports all nine functions, so callers do `from internal.db import ...`
- `services/mcp/` — the pure FastMCP server (see below), built with `fastmcp.FastMCP` directly (no `FastMCP.from_fastapi()`)
- `services/rest/app.py` — independent, hand-written FastAPI app with the REST endpoints (`/{version}/enums`, `/{version}/modules`, `/{version}/paths/{module_name}`, plus `/azure/*`); not introspected for MCP generation
- `services/app.py` — composes `services.mcp.mcp_app` (at `/mcp`) and `services.rest.app`'s routes (at their existing paths, e.g. `/azure/tasks`) into the single `combined_app` served by `main.py`; its lifespan also kicks off `internal.azure_devops.sync_all_wikis_on_startup()` as a non-blocking background task on every server start

**Environment variables** (`.env`):
- `SWAGGER_JSON_V1_URL` — URL to v1 Swagger JSON
- `SWAGGER_JSON_V2_URL` — URL to v2 Swagger JSON
- `AZURE_DEVOPS_ORG_URL` — Azure DevOps organization URL (e.g. `https://dev.azure.com/YOURORG`)
- `AZURE_DEVOPS_PAT` — Personal Access Token for authentication
- `AZURE_DEVOPS_PROJECT` — Project name or ID
- `WIKI_CACHE_DB_PATH` — override for the wiki cache SQLite file (default `data/wiki_cache.db`)
- `WIKI_CACHE_STALE_SECONDS` — default staleness threshold for automatic wiki cache refresh (default `86400`, 1 day); overridable per-call via `stale_after_seconds`

**Module name extraction** (`get_module_names`): paths are parsed as `/{prefix}/{version}/{module}/...`; if the third segment is `admin`, the module name becomes `admin/{fourth_segment}`.

**MCP transport:** served over HTTP at `/mcp` (streamable HTTP, not stdio).

## MCP Server (`services/mcp/`)

`services/mcp/server.py` creates a single `FastMCP(name="swagger_parser")` instance, then imports `resources`, `tools`, and `prompts` submodules for their registration side effects (each decorates the shared `mcp` instance with `@mcp.tool`/`@mcp.resource`/`@mcp.prompt` at import time). `mcp_app = mcp.http_app(path="/mcp")` is what `services/app.py` mounts.

**Resources** (`services/mcp/resources/`) — read-only, no side effects, addressed by URI. Query-string template params (`{?param}`) must have defaults in the function signature (a FastMCP requirement); "required" ones default to `None` and raise `ValueError` if omitted. Resource functions must return `str`/`bytes`, so all of these `json.dumps()` their result (declared `mime_type="application/json"`):
- `swagger.py` — `swagger://{version}/enums`, `swagger://{version}/modules`, `swagger://{version}/paths/{module_name}`
- `wiki_live.py` — `wiki://pages{?top}` (all wikis), `wiki://{wiki_id}/pages{?top,continuation_token}`, `wiki://page-by-path{?path}` / `wiki://{wiki_id}/page-by-path{?path}`, `wiki://page-by-id/{page_id}` / `wiki://{wiki_id}/page-by-id/{page_id}` — the no-`wiki_id` variants default to the project's default wiki
- `wiki_cache.py` — `wiki-cache://tree{?wiki_id,stale_after_seconds}`, `wiki-cache://{wiki_id}/structure{?root_page_id,root_path,stale_after_seconds}`, `wiki-cache://status{?wiki_id,stale_after_seconds}`, `wiki-cache://search{?q,wiki_id,limit,stale_after_seconds}` — each calls `ensure_wiki_cache_fresh` before reading (see Wiki Cache Internals)

**Tools** (`services/mcp/tools/`) — actions and queries with many dynamic filters:
- `azure_work_items.py` — `get_azure_devops_tasks` (filters: `id`, `parent_id`, `assignee`, `team`, `current_sprint`, `sprint`, `state`, `top`), `get_azure_devops_pbis` (same minus `parent_id`). When `get_azure_devops_pbis` is called with `id` (i.e. exactly one PBI returned), it takes a `ctx: Context` param and uses MCP **elicitation** (`ctx.elicit(message, response_type=None)`) to ask whether to also search the wiki cache for context, using the PBI's title (sanitized of FTS5 syntax chars) as the query; if accepted, adds a `wiki_context` field (a `search_wiki_cache` result list, capped at 5) to that PBI. Silently skipped — no `wiki_context` key at all — if more than one PBI is returned, or if the client doesn't support elicitation (`ctx.elicit` raises; caught and ignored).
- `wiki_cache_sync.py` — `sync_azure_devops_wiki_cache(wiki_id, fetch_content=True)`, the only mutating operation (rewrites the SQLite cache)

**Prompts** (`services/mcp/prompts/`):
- `sprint_status_report(team?, sprint?, current_sprint=True)` — builds a report prompt from `get_tasks`/`get_pbis`, grouped by assignee/state
- `wiki_page_digest(path? | page_id, wiki_id?)` — builds a summarization prompt from a wiki page and all its subpages' content
- `pbi_breakdown_check(pbi_id)` — builds a prompt checking a PBI's child Tasks (via `get_tasks(parent_id=pbi_id)`) for completeness/state consistency

## REST API (`services/rest/app.py`)

Independent FastAPI app; same endpoints as before, calling the same `internal/` functions the MCP layer uses. Not exposed as MCP tools (that auto-derivation was removed — see MCP Server section above for the native equivalents).

| Endpoint | Operation ID | Description |
|---|---|---|
| `GET /azure/tasks` | `get_azure_devops_tasks` | Fetch Tasks |
| `GET /azure/pbis` | `get_azure_devops_pbis` | Fetch Product Backlog Items |
| `GET /azure/wiki` | `get_azure_devops_wiki_pages` | List wiki pages (metadata only: `page_id`, `path` — no content) |
| `GET /azure/wiki/page` | `get_azure_devops_wiki_page_by_path` | Fetch a wiki page's content by `path` |
| `GET /azure/wiki/page/{page_id}` | `get_azure_devops_wiki_page_by_id` | Fetch a wiki page's content by `page_id` |
| `POST /azure/wiki/cache/sync` | `sync_azure_devops_wiki_cache` | Rebuild the local cache for one wiki (structure + content) |
| `GET /azure/wiki/cache/search` | `search_azure_devops_wiki_cache` | Full-text search over the cached wiki (FTS5); results include full content, breadcrumb, matched_in |
| `GET /azure/wiki/cache/tree` | `get_azure_devops_wiki_cache_tree` | Get the cached page hierarchy as a nested tree (no API calls) |
| `GET /azure/wiki/cache/structure` | `get_azure_devops_wiki_cache_structure` | Get the cached folder/path subtree rooted at one page (no content, no API calls) |
| `GET /azure/wiki/cache/status` | `get_azure_devops_wiki_cache_status` | Get cache stats (page count, last sync) per wiki |

**Shared query params for `/azure/tasks` and `/azure/pbis`:**
- `id` — fetch a single item by work item ID
- `parent_id` — filter by parent PBI's work item ID (`/azure/tasks` only)
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

**Wiki cache** (`internal/azure_devops/wiki_sync.py` orchestrating `internal/db/`): a local SQLite database (`data/wiki_cache.db` by default; override with `WIKI_CACHE_DB_PATH`) caching wiki structure and content for full-text search, entirely separate from the live `/azure/wiki*` endpoints above (those still always hit the API — the cache is purely additive). Full details and the incremental-sync algorithm: [docs/wiki-cache.md](docs/wiki-cache.md).

- `sync_azure_devops_wiki_cache` (`wiki_id` required, `fetch_content` default `true`) — full/bootstrap resync, fully replacing that wiki's cached rows. Only needed for a wiki's first-ever sync or to force a full reset: every wiki in the project is also resynced automatically (in the background, non-blocking) on every server startup (`sync_all_wikis_on_startup`, wired into `services/app.py`'s lifespan), and reads auto-refresh incrementally once stale (see below). The cache starts empty; nothing else here works until a sync — manual or startup — has completed for a wiki at least once.
- **Automatic staleness refresh**: every wiki-cache read (REST `/azure/wiki/cache/*` GETs, MCP `wiki-cache://*` resources) calls `ensure_wiki_cache_fresh(wiki_id, stale_after_seconds)` first. If the wiki was checked more recently than `stale_after_seconds` (default `WIKI_CACHE_STALE_SECONDS`, 1 day), this is a no-op (zero Azure calls). Otherwise it calls `check_and_refresh_wiki_cache`, which:
  1. Lists current pages via `GetPagesBatch` (cheap, ~0.4s for 417 pages) and fetches every page's live last-modified date in **one bulk call** — `GitClient.get_items(repository_id, scope_path="/", recursion_level="full", latest_processed_change=True)` against the wiki's backing git repo (`WikiV2.repository_id`) — matched back to pages via each page's `git_item_path` (~3s total for 417 pages, regardless of size, vs. one API call per page for content).
  2. For each live page: if it's new, or its live modified date is newer than the cached `content_modified_at`, re-fetches that page's content via `get_page_by_id` (which also returns `git_item_path`, needed to look up its date next time). Otherwise reuses the cached content untouched — no Azure content call.
  3. Pages that no longer exist live are dropped. The reconciled page set (mix of reused + freshly-fetched) is written via `replace_wiki_pages`, and `record_wiki_cache_check` stamps `last_checked_at` for the gate above.
  - `ensure_wiki_cache_fresh` is best-effort: failures are logged and swallowed, so a read always falls back to serving the last-known-good cache rather than failing outright.
- Schema is normalized into structure vs. content, confirmed empirically that every `parent_path` in this wiki corresponds to a real page (no synthetic "folder" rows needed):
  - `wiki_structure` — `wiki_id`, `page_id`, `path`, `name` (last path segment), `parent_id` (self-referencing FK, resolved at sync time by inserting pages shallowest-first so each parent's row already exists), `depth`, `git_item_path` (the page's file path in the wiki's backing git repo, used to correlate with `GitClient.get_items` results).
  - `wiki_page_content` — one row per `wiki_structure.id` (`structure_id` FK/PK), `content` (nullable if never synced), `content_synced_at` (when we last fetched it), `content_modified_at` (the actual git commit date behind that content — what staleness checks compare against).
  - `wiki_pages_fts` — a standalone FTS5 table over `(path, content)` (not an external-content table, since path/content live in two different source tables), inserted with an explicit `rowid` matching `wiki_structure.id` so search results can join back to it.
  - `wiki_cache_check_state` — `wiki_id` (PK), `last_checked_at`: when `check_and_refresh_wiki_cache` last ran for that wiki, gating the staleness check above.
- `search_azure_devops_wiki_cache` takes an FTS5 `MATCH` query (phrases in quotes, `AND`/`OR`/`NOT`, `prefix*`; accent-insensitive by default, e.g. `adesao` also matches `adesão`) and returns ranked results, each with a `snippet`, the page's full `content`, a `breadcrumb` (ancestor chain from the wiki root, via a `parent_id`-walking CTE), and `matched_in` (`["path"]`/`["content"]`/both, via FTS5's `{column}: (query)` filter syntax — always parenthesized, since `{path}: a OR b` would otherwise leave `b` unscoped).
- `get_azure_devops_wiki_cache_tree` rebuilds the full hierarchy from `wiki_structure.parent_id` with zero API calls — reflects the state as of the last check/sync.
- `get_azure_devops_wiki_cache_structure` / `get_wiki_subtree` returns just the subtree rooted at one page (structure only, no content) via a `WITH RECURSIVE` CTE walking `parent_id` — e.g. `root_page_id=589` for `/Wiki Nivello/Produto & Agilidade` returns that page plus all 197 descendants nested as `sub_pages`. Pass exactly one of `root_page_id`/`root_path`.
- `get_azure_devops_wiki_cache_status` reports page count / pages-with-content / last sync time per wiki.
