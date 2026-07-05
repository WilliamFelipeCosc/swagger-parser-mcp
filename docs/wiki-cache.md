# Wiki Cache Internals

A local SQLite database (`data/wiki_cache.db` by default; override with
`WIKI_CACHE_DB_PATH`) caching wiki structure and content for full-text search. It's
consumed both by MCP Resources (`wiki-cache://...`, see [MCP Reference](mcp-reference.md))
and REST endpoints (`/azure/wiki/cache/*`, see [REST API Reference](rest-api.md)) — both
call the exact same `internal/` functions.

Freshness is automatic: every read checks (cheaply) whether the cache is stale and
incrementally refreshes only what changed, so there's no need to manually decide when to
resync. A full/bootstrap resync is still available and runs automatically for every wiki
in the project on server startup.

## Ownership split

- `internal/db/` — pure SQLite. Knows the schema and how to read/write it. **Never**
  calls the Azure DevOps API.
- `internal/azure_devops/wiki_sync.py` — orchestration. Fetches from Azure (via
  `internal/azure_devops/wiki.py`, plus the Git API for modification dates) and calls
  into `internal/db/` to persist. This is the **only** module that knows about both
  sides.

This split means the persistence layer can be exercised/tested with plain Python dicts,
with no Azure credentials or network access required.

## Getting a page's last-modified date

Wiki pages don't carry a modification date themselves — a `WikiPage` has no such field.
But every wiki is backed by a git repository (`WikiV2.repository_id`), where each page is
a markdown file (`WikiPage.git_item_path`), so its last-modified date is that file's last
commit date.

Fetching this **per page** would cost one API call per page — as expensive as fetching
content. Instead, `GitClient.get_items(repository_id, scope_path="/", recursion_level="full",
latest_processed_change=True)` returns every file in the repo, each with its
`latest_processed_change.committer.date`, **in one bulk call**. Measured against a
417-page wiki: ~3 seconds for the whole wiki, vs. 20-120s to fetch all page content
individually. This is the mechanism the staleness check below is built on.

## Two sync paths

### 1. Full/bootstrap resync — `sync_wiki_cache(wiki_id, fetch_content=True)`

1. Paginates through every page in the wiki via `GetPagesBatch`
   (`wiki.py::_get_pages_batch_page`, called directly against the low-level SDK
   transport since the high-level wrapper discards the `x-ms-continuationtoken`
   response header).
2. If `fetch_content=True`, also fetches the bulk git modification-date map (see above),
   then fetches each page's content individually with `get_page_by_id(...,
   include_content=True)` — there's no bulk-content API, so this is one call per page.
   The response also carries `git_item_path`, which combined with the modification-date
   map gives `content_modified_at` for that page. Failures are swallowed per-page
   (content stays `None`) rather than aborting the whole sync.
3. Hands the assembled pages to `internal.db.replace_wiki_pages(wiki_id, pages)`, which
   fully **replaces** that wiki's cached rows, and stamps `wiki_cache_check_state` via
   `record_wiki_cache_check`.

This is unconditional — it always touches every page — and is now reserved for a wiki's
first-ever sync or an explicit forced reset. It runs automatically, for every wiki in the
configured Azure DevOps project, as a **non-blocking background task** on server startup
(`sync_all_wikis_on_startup`, scheduled from `services/app.py`'s lifespan) — the server
starts accepting requests immediately; the cache fills in shortly after. It's also still
exposed directly as the `sync_azure_devops_wiki_cache` tool/endpoint for a manual forced
resync.

### 2. Incremental staleness check — `check_and_refresh_wiki_cache(wiki_id, stale_after_seconds=None)`

Called automatically by `ensure_wiki_cache_fresh` before every wiki-cache read (see
below). `stale_after_seconds` defaults to the `WIKI_CACHE_STALE_SECONDS` env var (1 day).

1. **Gate:** reads `wiki_cache_check_state.last_checked_at` for the wiki. If it's newer
   than `stale_after_seconds` ago, returns immediately — **zero Azure calls**.
2. Otherwise, fetches the current page list (`GetPagesBatch`, ~0.4s for 417 pages) and the
   bulk git modification-date map (~3s) described above.
3. For each **live** page:
   - Not in the cache → **new** page. Fetch its content (`get_page_by_id`).
   - In the cache, and its live modified date (looked up via its cached
     `git_item_path`) is newer than the cached `content_modified_at` (or either is
     missing) → **changed**. Re-fetch its content.
   - Otherwise → **unchanged**. Reuse the cached content as-is — no Azure content call.
4. Any cached page **not** present in the live listing is dropped.
5. The reconciled set (a mix of reused and freshly-fetched pages) is written via
   `replace_wiki_pages` — the same full-replace as the bootstrap path, just with mostly
   reused content — and `record_wiki_cache_check` stamps `last_checked_at`.

Net effect: the expensive per-page content fetch only happens for pages that are
genuinely new or changed; checking "is anything stale" costs a constant ~3.5s regardless
of wiki size once the gate lets a check through.

### `ensure_wiki_cache_fresh(wiki_id=None, stale_after_seconds=None)`

The function every read actually calls. If `wiki_id` is given, checks just that wiki; if
omitted, checks every wiki currently in the cache (`get_all_cached_wiki_ids`). **Best
effort** — any failure (e.g. Azure DevOps temporarily unreachable) is logged and
swallowed, so a read always falls back to serving the last-known-good cached data rather
than failing outright.

## Schema (`internal/db/connection.py`)

Normalized into structure vs. content (confirmed empirically that every `parent_path` in
this wiki corresponds to a real page — no synthetic "folder" rows needed):

```sql
CREATE TABLE wiki_structure (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wiki_id TEXT NOT NULL,
    page_id INTEGER NOT NULL,
    path TEXT NOT NULL,
    name TEXT NOT NULL,               -- last path segment
    parent_id INTEGER REFERENCES wiki_structure(id),
    depth INTEGER NOT NULL,
    structure_synced_at TEXT NOT NULL,
    git_item_path TEXT,               -- this page's file path in the backing git repo
    UNIQUE(wiki_id, page_id)
);

CREATE TABLE wiki_page_content (
    structure_id INTEGER PRIMARY KEY REFERENCES wiki_structure(id),
    content TEXT,                     -- nullable if never synced
    content_synced_at TEXT,           -- when we last fetched this content
    content_modified_at TEXT          -- the git commit date behind that content
);

CREATE VIRTUAL TABLE wiki_pages_fts USING fts5(path, content);

CREATE TABLE wiki_cache_check_state (
    wiki_id TEXT PRIMARY KEY,
    last_checked_at TEXT NOT NULL     -- gates check_and_refresh_wiki_cache
);
```

- `wiki_structure` — one row per page. `parent_id` is a self-referencing FK, resolved at
  sync time by inserting pages shallowest-first (`replace_wiki_pages` sorts by path depth
  internally) so each page's parent row already exists by the time it's inserted.
  `git_item_path` is what correlates a cached page with an entry in the bulk
  `GetItems`/modification-date map on the next staleness check.
- `wiki_page_content` — one row per `wiki_structure.id`. `content_synced_at` (when *we*
  fetched it) and `content_modified_at` (the actual last-edit date, from git) are
  distinct — the latter is what staleness comparisons use.
- `wiki_pages_fts` — a **standalone** FTS5 table (not an external-content table), since
  `path`/`content` live in two different source tables and external-content FTS5 requires
  a single source table. It keeps its own copy of both columns, inserted with an explicit
  `rowid` matching `wiki_structure.id` so search results can join back to the structure
  table.
- `wiki_cache_check_state` — one row per wiki, tracking when `check_and_refresh_wiki_cache`
  last actually ran (as opposed to being skipped by the freshness gate).
- `git_item_path`/`content_modified_at` are added via an idempotent migration
  (`_add_column_if_missing`) so existing databases from before this feature upgrade
  in place.

## Query functions (`internal/db/wiki_repository.py`)

| Function | Behavior |
|---|---|
| `replace_wiki_pages(wiki_id, pages)` | Deletes all existing rows for `wiki_id` (structure, content, FTS), then re-inserts `pages` (sorted shallowest-first) across all three tables in one pass. `pages` items may include `git_item_path`/`content_modified_at` |
| `search_wiki_cache(query, wiki_id=None, limit=20)` | FTS5 `MATCH` query against `wiki_pages_fts`, joined back to `wiki_structure`; ranked by `bm25()`, with a `snippet()` excerpt |
| `get_wiki_tree(wiki_id=None)` | Rebuilds the full hierarchy from `wiki_structure.parent_id`, purely in-memory (no recursive SQL) |
| `get_wiki_subtree(wiki_id, root_page_id=None, root_path=None)` | Same tree-building, but scoped via a `WITH RECURSIVE` CTE walking `parent_id` from one root row. Exactly one of `root_page_id`/`root_path` must be given |
| `get_wiki_cache_status(wiki_id=None)` | `GROUP BY wiki_id` aggregate: page count, pages with content, last sync timestamp |
| `get_cached_wiki_pages(wiki_id)` | Returns `{page_id: {path, git_item_path, content, content_modified_at}}` for a wiki — the shape `check_and_refresh_wiki_cache` diffs against a live listing |
| `get_all_cached_wiki_ids()` | Distinct `wiki_id`s currently in the cache — used by `ensure_wiki_cache_fresh` when no specific wiki is targeted |
| `get_wiki_cache_last_checked_at(wiki_id)` / `record_wiki_cache_check(wiki_id)` | Read/write `wiki_cache_check_state` — the staleness gate's clock |

All of these are **read-only, zero Azure API calls** — they reflect the state as of the
last check/sync, not necessarily this instant (though in practice at most
`stale_after_seconds` old).
