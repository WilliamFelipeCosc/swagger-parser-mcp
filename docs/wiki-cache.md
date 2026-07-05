# Wiki Cache Internals

A local SQLite database (`data/wiki_cache.db` by default; override with
`WIKI_CACHE_DB_PATH`) caching wiki structure and content for full-text search. It's
consumed both by MCP Resources (`wiki-cache://...`, see [MCP Reference](mcp-reference.md))
and REST endpoints (`/azure/wiki/cache/*`, see [REST API Reference](rest-api.md)) — both
call the exact same `internal/db/` functions.

## Ownership split

- `internal/db/` — pure SQLite. Knows the schema and how to read/write it. **Never**
  calls the Azure DevOps API.
- `internal/azure_devops/wiki_sync.py` — orchestration. Fetches from Azure (via
  `internal/azure_devops/wiki.py`) and calls into `internal/db/` to persist. This is the
  **only** module that knows about both sides.

This split means the persistence layer can be exercised/tested with plain Python dicts,
with no Azure credentials or network access required.

## Sync flow (`sync_wiki_cache`)

`internal/azure_devops/wiki_sync.py::sync_wiki_cache(wiki_id, fetch_content=True)`:

1. Paginates through every page in the wiki via `GetPagesBatch`
   (`wiki.py::_get_pages_batch_page`, called directly against the low-level SDK
   transport since the high-level wrapper discards the `x-ms-continuationtoken`
   response header).
2. If `fetch_content=True`, fetches each page's content individually with
   `get_page_by_id(..., include_content=True)` — there's no bulk-content API, so this is
   one call per page. Failures are swallowed per-page (content stays `None`) rather than
   aborting the whole sync.
3. Hands the assembled `[{"page_id", "path", "content"}, ...]` list to
   `internal.db.replace_wiki_pages(wiki_id, pages)`, which does the actual persistence
   (see below) and returns `{"wiki_id", "pages_synced", "content_fetched", "synced_at"}`.

This fully **replaces** that wiki's cached rows each time — there's no incremental/delta
sync.

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
    UNIQUE(wiki_id, page_id)
);

CREATE TABLE wiki_page_content (
    structure_id INTEGER PRIMARY KEY REFERENCES wiki_structure(id),
    content TEXT,                     -- nullable if never synced
    content_synced_at TEXT
);

CREATE VIRTUAL TABLE wiki_pages_fts USING fts5(path, content);
```

- `wiki_structure` — one row per page. `parent_id` is a self-referencing FK, resolved at
  sync time by inserting pages shallowest-first (`replace_wiki_pages` sorts by path depth
  internally) so each page's parent row already exists by the time it's inserted.
- `wiki_page_content` — one row per `wiki_structure.id`.
- `wiki_pages_fts` — a **standalone** FTS5 table (not an external-content table), since
  `path`/`content` live in two different source tables and external-content FTS5 requires
  a single source table. It keeps its own copy of both columns, inserted with an explicit
  `rowid` matching `wiki_structure.id` so search results can join back to the structure
  table.

## Query functions (`internal/db/wiki_repository.py`)

| Function | Behavior |
|---|---|
| `replace_wiki_pages(wiki_id, pages)` | Deletes all existing rows for `wiki_id` (structure, content, FTS), then re-inserts `pages` (sorted shallowest-first) across all three tables in one pass |
| `search_wiki_cache(query, wiki_id=None, limit=20)` | FTS5 `MATCH` query against `wiki_pages_fts`, joined back to `wiki_structure`; ranked by `bm25()`, with a `snippet()` excerpt |
| `get_wiki_tree(wiki_id=None)` | Rebuilds the full hierarchy from `wiki_structure.parent_id`, purely in-memory (no recursive SQL) |
| `get_wiki_subtree(wiki_id, root_page_id=None, root_path=None)` | Same tree-building, but scoped via a `WITH RECURSIVE` CTE walking `parent_id` from one root row. Exactly one of `root_page_id`/`root_path` must be given |
| `get_wiki_cache_status(wiki_id=None)` | `GROUP BY wiki_id` aggregate: page count, pages with content, last sync timestamp |

All of these are **read-only, zero Azure API calls** — they reflect the state as of the
last `sync_wiki_cache` run, not live data.
