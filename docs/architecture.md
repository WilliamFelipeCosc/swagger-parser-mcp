# Architecture

## Entry point

`services/cli.py:main` — installed as the `swagger-parser-mcp` console script by
`pyproject.toml`'s `[project.scripts]`. `main.py` is a dev shim that calls it, so
`python main.py` from a checkout behaves identically.

It runs the MCP server over **stdio** — the only transport. There is no HTTP surface, no
port and no ASGI app.

```
services/cli.py:main
  ├── load_env()                        → .env, anchored (see internal/env.py)
  ├── sync_all_wikis_on_startup()       → background daemon thread, non-blocking
  └── services/mcp/server.py            → mcp.run(transport="stdio")
```

Because there is no ASGI lifespan to hook into, the startup resync runs in a plain daemon
thread: the server starts serving immediately and every wiki in the configured project
gets a full resync shortly after. See [Wiki Cache Internals](wiki-cache.md).

`main.py` also re-exports `mcp` at module level, so `fastmcp run main.py:mcp` and
`fastmcp.json`'s `source.entrypoint` resolve. That path loads the `mcp` object directly
and never calls `main()`, so it skips the background startup wiki sync.

## Design principle: one surface, native MCP

`services/mcp/` is a plain `fastmcp.FastMCP` instance with Tools, Resources and Prompts
registered natively via decorators — **not** built with `FastMCP.from_fastapi()`. It calls
`internal/` functions directly.

The project previously served a second, hand-written FastAPI/REST surface alongside MCP on
one port. That was removed: every REST endpoint already had an MCP equivalent, so the
FastAPI app, its uvicorn/`--http` entry point and the `fastapi`/`uvicorn` dependencies were
all dead weight for a server that MCP clients launch over stdio.

## `internal/` layer breakdown

`internal/` contains all business logic; `services/` only adapts that logic to MCP. Each
`internal/` sub-package owns one concern and has a narrow, explicit boundary with its
neighbors.

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
| `wiki_sync.py` | `sync_wiki_cache(wiki_id, fetch_content=True)` — full/bootstrap resync. `check_and_refresh_wiki_cache(wiki_id, stale_after_seconds?)` — TTL-gated incremental refresh (only re-fetches new/changed pages, using a bulk Git API call for modification dates). `ensure_wiki_cache_fresh(wiki_id?, stale_after_seconds?)` — best-effort wrapper called before every cache read. `sync_all_wikis_on_startup()` — resyncs every wiki in the project, used by the startup background task. **This is the only module that talks to both the Azure API and SQLite.** |
| `__init__.py` | Re-exports `get_tasks`, `get_pbis`, `get_wiki_pages`, `get_wiki_page_by_path`, `get_wiki_page_by_id`, `sync_wiki_cache`, `check_and_refresh_wiki_cache`, `ensure_wiki_cache_fresh`, `sync_all_wikis_on_startup` |

### `internal/db/` — SQLite+FTS5 persistence

Generic persistence layer for the wiki cache. **Has zero knowledge of the Azure API** —
every function takes already-fetched data and reads/writes SQLite only. See
[Wiki Cache Internals](wiki-cache.md) for the schema and query details.

| File | Responsibility |
|---|---|
| `connection.py` | `_get_db_connection()` (path from `_get_db_path()`: `WIKI_CACHE_DB_PATH` if set, else an existing `<repo>/data/wiki_cache.db`, else `platformdirs.user_data_dir("swagger-parser-mcp")/wiki_cache.db`), schema creation |
| `wiki_repository.py` | `replace_wiki_pages`, `search_wiki_cache`, `get_wiki_tree`, `get_wiki_subtree`, `get_wiki_cache_status`, `get_cached_wiki_pages`, `get_all_cached_wiki_ids`, `get_wiki_cache_last_checked_at`, `record_wiki_cache_check` |
| `__init__.py` | Re-exports all nine functions |

### `services/params.py`

Defines `swagger_version` — a `str` `Enum` with values `v1`/`v2` — the only type shared
between the Swagger internal logic and the `services/` layer.

## Environment variables (`.env`)

| Variable | Purpose |
|---|---|
| `SWAGGER_JSON_V1_URL` | URL to v1 Swagger JSON |
| `SWAGGER_JSON_V2_URL` | URL to v2 Swagger JSON |
| `AZURE_DEVOPS_ORG_URL` | Azure DevOps organization URL, e.g. `https://dev.azure.com/YOURORG` |
| `AZURE_DEVOPS_PAT` | Personal Access Token for authentication |
| `AZURE_DEVOPS_PROJECT` | Project name or ID |
| `WIKI_CACHE_DB_PATH` | Override for the wiki cache SQLite file (default: existing `<repo>/data/wiki_cache.db` if present, else the per-user data dir via `platformdirs`) |
| `WIKI_CACHE_STALE_SECONDS` | Default staleness threshold for automatic wiki cache refresh (default `86400`, 1 day); overridable per-call via `stale_after_seconds` |

## Why the code is shaped this way

- **`internal/db/` never imports `internal/azure_devops/`, and vice versa.** The only
  module that bridges them is `internal/azure_devops/wiki_sync.py`, which fetches from
  Azure and calls into `internal/db/` to persist. This keeps the persistence layer
  reusable/testable without live Azure credentials, and keeps Azure API concerns out of
  SQL code.
- **`services/mcp/` registers its Tools/Resources/Prompts by hand and calls `internal/`
  directly** — deliberately, rather than auto-deriving them from an OpenAPI spec via
  `FastMCP.from_fastapi()`. That keeps each Resource URI and Tool signature shaped for
  the protocol instead of inheriting the shape of an HTTP endpoint.
