# Architecture

## Entry point

`main.py` imports `combined_app` from `services/app.py` and runs it with `uvicorn` on
`localhost:9876`.

```
main.py
  └── services/app.py            → combined_app (FastAPI)
        ├── services/mcp/        → mcp_app, mounted at /mcp
        └── services/rest/app.py → REST routes, at their own paths (/azure/*, /{version}/*)
```

`services/app.py` builds `combined_app` by merging `mcp_app.routes` and `rest_app.routes`
into one `FastAPI` instance (not `.mount()`-based nesting), so the REST paths are
unchanged from before this surface split, and the MCP endpoint stays at `/mcp`.

## Design principle: two independent surfaces

The MCP server and the REST API each call the same `internal/` functions directly, but
neither is generated from the other:

- The REST API (`services/rest/app.py`) is a plain FastAPI app, maintained by hand.
- The MCP server (`services/mcp/`) is a plain `fastmcp.FastMCP` instance, with Tools,
  Resources, and Prompts registered natively via decorators — **not** built with
  `FastMCP.from_fastapi()`.

This means the two surfaces can diverge in shape where it makes sense (e.g. the MCP
server exposes read-only Azure DevOps/Swagger data as addressable Resources, while the
REST API exposes everything as query-parameterized `GET` endpoints) without one
constraining the other's design.

## `internal/` layer breakdown

`internal/` contains all business logic; `services/` only adapts that logic to REST or
MCP. Each `internal/` sub-package owns one concern and has a narrow, explicit boundary
with its neighbors.

### `internal/swagger/` — Swagger/OpenAPI parsing

| File | Responsibility |
|---|---|
| `client.py` | `get_swagger_json_url(version)` reads the version's URL from env vars; `load_json(url)` fetches and resolves `$ref`s via `jsonref` |
| `parser.py` | `show_enums`, `show_paths`, `get_module_names` — pure functions over already-resolved Swagger JSON, no I/O |
| `__init__.py` | Composes the two into the public API: `get_enums(version)`, `get_paths(version, module_name)`, `get_modules(version)` |

**Module name extraction** (`get_module_names`): paths are parsed as
`/{prefix}/{version}/{module}/...`; if the third segment is `admin`, the module name
becomes `admin/{fourth_segment}`.

### `internal/azure_devops/` — Azure DevOps API integration

Uses the `azure-devops` Python SDK. Split by concern; only `wiki_sync.py` is allowed to
know about both the Azure API and the SQLite cache.

| File | Responsibility |
|---|---|
| `shared.py` | `_get_connection()` / `_get_project()` — shared connection/project helpers, read from env vars |
| `tasks.py` | `get_tasks(item_id?, parent_id?, sprint?, current_sprint?, team?, assignee?, state?, top?)`, `get_pbis(...)` (same filters minus `parent_id`) — both built on a shared `_get_work_items_by_type` WIQL query helper |
| `wiki.py` | Live Wiki API calls: `get_wiki_pages`, `get_wiki_page_by_path`, `get_wiki_page_by_id`, plus the internal `_get_pages_batch_page` helper (calls `GetPagesBatch` directly via the SDK's low-level `_send`, since the SDK wrapper discards the continuation-token response header) |
| `wiki_sync.py` | `sync_wiki_cache(wiki_id, fetch_content=True)` — orchestrates cache rebuilds: paginates pages via `wiki.py`'s `_get_pages_batch_page`, optionally fetches each page's content, then hands the results to `internal.db.replace_wiki_pages` to persist. **This is the only module that talks to both the Azure API and SQLite.** |
| `__init__.py` | Re-exports `get_tasks`, `get_pbis`, `get_wiki_pages`, `get_wiki_page_by_path`, `get_wiki_page_by_id`, `sync_wiki_cache` |

### `internal/db/` — SQLite+FTS5 persistence

Generic persistence layer for the wiki cache. **Has zero knowledge of the Azure API** —
every function takes already-fetched data and reads/writes SQLite only. See
[Wiki Cache Internals](wiki-cache.md) for the schema and query details.

| File | Responsibility |
|---|---|
| `connection.py` | `_get_db_connection()` (path from `WIKI_CACHE_DB_PATH` env var, default `data/wiki_cache.db`), schema creation |
| `wiki_repository.py` | `replace_wiki_pages`, `search_wiki_cache`, `get_wiki_tree`, `get_wiki_subtree`, `get_wiki_cache_status` |
| `__init__.py` | Re-exports all five functions |

### `services/params.py`

Defines `swagger_version` — a `str` `Enum` with values `v1`/`v2` — the only type shared
between the Swagger internal logic and both `services/` surfaces.

## Environment variables (`.env`)

| Variable | Purpose |
|---|---|
| `SWAGGER_JSON_V1_URL` | URL to v1 Swagger JSON |
| `SWAGGER_JSON_V2_URL` | URL to v2 Swagger JSON |
| `AZURE_DEVOPS_ORG_URL` | Azure DevOps organization URL, e.g. `https://dev.azure.com/YOURORG` |
| `AZURE_DEVOPS_PAT` | Personal Access Token for authentication |
| `AZURE_DEVOPS_PROJECT` | Project name or ID |
| `WIKI_CACHE_DB_PATH` | Override for the wiki cache SQLite file (default `data/wiki_cache.db`) |

## Why the code is shaped this way

- **`internal/db/` never imports `internal/azure_devops/`, and vice versa.** The only
  module that bridges them is `internal/azure_devops/wiki_sync.py`, which fetches from
  Azure and calls into `internal/db/` to persist. This keeps the persistence layer
  reusable/testable without live Azure credentials, and keeps Azure API concerns out of
  SQL code.
- **`services/mcp/` and `services/rest/` never share route/tool definitions** — each
  calls `internal/` directly. This was a deliberate choice over auto-generating one from
  the other, so each surface's shape (Resources vs. query-parameterized endpoints) can
  fit its protocol idiomatically.
