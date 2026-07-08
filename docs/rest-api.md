# REST API Reference

Defined by hand in `services/rest/app.py`. Independent from the MCP server — it calls the
same `internal/` functions, but is not introspected to generate MCP tools.

## Swagger endpoints

| Endpoint | Operation ID | Description |
|---|---|---|
| `GET /{version}/enums` | `get_enums` | All enums defined in the Swagger JSON for the specified version (`v1`\|`v2`) |
| `GET /{version}/modules` | `get_all_modules` | All modules defined in the Swagger JSON for the specified version |
| `GET /{version}/paths/{module_name}` | `get_paths_by_module` | All paths for a specified module in the Swagger JSON for the specified version |

## Azure DevOps endpoints

All under `/azure/`.

| Endpoint | Operation ID | Description |
|---|---|---|
| `GET /azure/tasks` | `get_azure_devops_tasks` | Fetch Tasks |
| `GET /azure/pbis` | `get_azure_devops_pbis` | Fetch Product Backlog Items |
| `GET /azure/wiki` | `get_azure_devops_wiki_pages` | List wiki pages (metadata only: `page_id`, `path` — no content) |
| `GET /azure/wiki/page` | `get_azure_devops_wiki_page_by_path` | Fetch a wiki page's content by `path` |
| `GET /azure/wiki/page/{page_id}` | `get_azure_devops_wiki_page_by_id` | Fetch a wiki page's content by `page_id` |
| `POST /azure/wiki/cache/sync` | `sync_azure_devops_wiki_cache` | Rebuild the local cache for one wiki (structure + content) |
| `GET /azure/wiki/cache/search` | `search_azure_devops_wiki_cache` | Full-text search over the cached wiki (FTS5); each result includes full content, breadcrumb, and matched_in |
| `GET /azure/wiki/cache/tree` | `get_azure_devops_wiki_cache_tree` | Get the cached page hierarchy as a nested tree (no API calls) |
| `GET /azure/wiki/cache/structure` | `get_azure_devops_wiki_cache_structure` | Get the cached folder/path subtree rooted at one page (no content, no API calls) |
| `GET /azure/wiki/cache/status` | `get_azure_devops_wiki_cache_status` | Get cache stats (page count, last sync) per wiki |

### Shared query params for `/azure/tasks` and `/azure/pbis`

| Param | Notes |
|---|---|
| `id` | Fetch a single item by work item ID |
| `parent_id` | Filter by parent PBI's work item ID (`/azure/tasks` only) |
| `assignee` | Substring match on display name |
| `team` | Sprint board team name (scopes `@CurrentIteration` to the right team) |
| `current_sprint` | Boolean; filters by `@CurrentIteration` (takes priority over `sprint`) |
| `sprint` | Substring match on iteration path |
| `state` | e.g. `Active`, `New`, `Closed` |
| `top` | Max results (default 100) |

Task responses include `parent_id` (`System.Parent`) — the ID of the parent PBI, or `null`
if unset.

### Wiki endpoints

- `/azure/wiki` accepts an optional `wiki_id` (ID or name); if omitted, all wikis in the
  project are listed.
- `/azure/wiki/page` and `/azure/wiki/page/{page_id}` accept an optional `wiki_id`; if
  omitted, it defaults to the project's default wiki (name == project name, the standard
  Azure DevOps convention).
- Both page-lookup endpoints return `wiki_id`, `wiki_name` (`null` unless resolved from a
  listed wiki), `page_id`, `path`, `content`, `is_parent_page`, `order`, `url`,
  `sub_pages`, and `sub_pages_truncated`.

**Wiki subpages** (`/azure/wiki/page`, `/azure/wiki/page/{page_id}`): if a page has
children, `sub_pages` recursively nests every descendant (with its own content and
`sub_pages`), mirroring the wiki's hierarchy. Azure DevOps' `recursionLevel=full` only
returns descendant paths, not content or IDs, so each descendant's content is fetched
with a separate `get_page` call. Capped at `MAX_SUBPAGES_FETCHED` (50, in
`internal/azure_devops/wiki.py`) total descendants per request; if the cap is hit,
`sub_pages_truncated` is `true` and the remaining descendants at that point in the tree
are omitted.

**Wiki pagination** (`/azure/wiki`): response shape is `{"pages": [...], "continuation_token": ...}`.
Pass `top` and `continuation_token` (from a previous response) to page through a single
wiki's pages — this only works when `wiki_id` is set, since Azure DevOps continuation
tokens are per-wiki. When `wiki_id` is omitted (listing all wikis), `continuation_token`
is always `null` and each wiki returns up to `top` pages with no further pagination.

### Wiki cache endpoints

Entirely separate from the live `/azure/wiki*` endpoints above (those always hit the
API — the cache is purely additive). See [Wiki Cache Internals](wiki-cache.md) for the
schema and sync/staleness flow behind these.

Freshness is automatic: every `GET` below calls `ensure_wiki_cache_fresh` first, which
incrementally refreshes the cache (fetching content only for pages that are new or
changed, via one cheap bulk "what changed" call) if it's older than
`stale_after_seconds` (query param on each endpoint; defaults to the
`WIKI_CACHE_STALE_SECONDS` env var, 1 day). A wiki still needs a first sync — manual or
the automatic one on server startup — before it has anything to serve.

- `POST /azure/wiki/cache/sync` (`wiki_id` required, `fetch_content` default `true`) —
  forces a full bootstrap/reset resync, unconditionally replacing that wiki's cached
  rows. Can be slow for large wikis (one API call per page when `fetch_content=true`;
  e.g. ~0.4s structure-only vs. ~20-120s with content for 417 pages, depending on API
  latency). Every wiki in the project is also resynced this way automatically, in the
  background, every time the server starts — this endpoint is for a wiki's first-ever
  sync (if you don't want to wait for the next restart) or an explicit forced reset.
- `GET /azure/wiki/cache/search?q=...` — `q` supports FTS5 syntax (phrases in quotes,
  `AND`/`OR`/`NOT`, `prefix*`) and is accent-insensitive; optional `wiki_id`, `limit`
  (default 20), `stale_after_seconds`. Each result includes the page's full `content`, a
  `breadcrumb` (ancestor page chain), and `matched_in` (`["path"]`/`["content"]`/both) —
  see [Wiki Cache Internals](wiki-cache.md#search-result-shape).
- `GET /azure/wiki/cache/tree` — optional `wiki_id` (omit for trees across all cached
  wikis), `stale_after_seconds`.
- `GET /azure/wiki/cache/structure` — requires `wiki_id`, and exactly one of
  `root_page_id`/`root_path`; optional `stale_after_seconds`. Returns `400` if neither
  `root_page_id` nor `root_path` is given, `404` if the page isn't in the cache.
- `GET /azure/wiki/cache/status` — optional `wiki_id` (omit for stats across all cached
  wikis), `stale_after_seconds`.
