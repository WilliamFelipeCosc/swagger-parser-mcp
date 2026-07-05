import json
from typing import Optional

from internal.azure_devops import ensure_wiki_cache_fresh
from internal.db import (
    get_wiki_cache_status,
    get_wiki_subtree,
    get_wiki_tree,
    search_wiki_cache,
)

from ..server import mcp


@mcp.resource(
    "wiki-cache://tree{?wiki_id,stale_after_seconds}",
    name="WikiCacheTree",
    description=(
        "Get the cached wiki page hierarchy as a nested tree. Before reading, checks "
        "whether the cache is older than stale_after_seconds (default "
        "WIKI_CACHE_STALE_SECONDS, 1 day) and — only if so — refreshes it incrementally "
        "from Azure DevOps (cheap: one bulk 'what changed' call, content re-fetched only "
        "for new/changed pages). Omit wiki_id to get trees for all cached wikis. Still "
        "requires a first sync_azure_devops_wiki_cache call for wikis never seen before."
    ),
    mime_type="application/json",
)
def wiki_cache_tree(wiki_id: Optional[str] = None, stale_after_seconds: Optional[int] = None) -> str:
    ensure_wiki_cache_fresh(wiki_id=wiki_id, stale_after_seconds=stale_after_seconds)
    return json.dumps(get_wiki_tree(wiki_id=wiki_id))


@mcp.resource(
    "wiki-cache://{wiki_id}/structure{?root_page_id,root_path,stale_after_seconds}",
    name="WikiCacheStructure",
    description=(
        "Get the cached folder/path structure (no content) of the subtree rooted at a "
        "specific page in one wiki — e.g. root_page_id=589 for '/Wiki Nivello/Produto & "
        "Agilidade' returns that page plus every descendant path underneath it, nested as "
        "sub_pages. Refreshes the cache first if it's older than stale_after_seconds (see "
        "WikiCacheTree). Pass exactly one of root_page_id or root_path."
    ),
    mime_type="application/json",
)
def wiki_cache_structure(
    wiki_id: str,
    root_page_id: Optional[int] = None,
    root_path: Optional[str] = None,
    stale_after_seconds: Optional[int] = None,
) -> str:
    if root_page_id is None and root_path is None:
        raise ValueError("root_page_id or root_path is required")
    ensure_wiki_cache_fresh(wiki_id=wiki_id, stale_after_seconds=stale_after_seconds)
    subtree = get_wiki_subtree(wiki_id=wiki_id, root_page_id=root_page_id, root_path=root_path)
    if subtree is None:
        raise ValueError("Page not found in cache. Has this wiki been synced?")
    return json.dumps(subtree)


@mcp.resource(
    "wiki-cache://status{?wiki_id,stale_after_seconds}",
    name="WikiCacheStatus",
    description=(
        "Get cache stats per wiki: page count, pages with content cached, and the last "
        "sync timestamp. Refreshes the cache first if it's older than stale_after_seconds "
        "(see WikiCacheTree) — so a fresh read always reflects what was just checked. "
        "Omit wiki_id for stats on all cached wikis."
    ),
    mime_type="application/json",
)
def wiki_cache_status(wiki_id: Optional[str] = None, stale_after_seconds: Optional[int] = None) -> str:
    ensure_wiki_cache_fresh(wiki_id=wiki_id, stale_after_seconds=stale_after_seconds)
    return json.dumps(get_wiki_cache_status(wiki_id=wiki_id))


@mcp.resource(
    "wiki-cache://search{?q,wiki_id,limit,stale_after_seconds}",
    name="WikiCacheSearch",
    description=(
        "Full-text search over the cached wiki pages (path + content) using SQLite FTS5. "
        "`q` (required) supports FTS5 syntax (phrases in quotes, AND/OR/NOT, prefix*) and "
        "is accent-insensitive by default (e.g. 'adesao' also matches 'adesão'). Each "
        "result includes the page's full content, its breadcrumb (ancestor page chain "
        "from the wiki root), and matched_in ('path' and/or 'content', showing where the "
        "query hit). Refreshes the cache first if it's older than stale_after_seconds "
        "(see WikiCacheTree). Omit wiki_id to search across all cached wikis."
    ),
    mime_type="application/json",
)
def wiki_cache_search(
    q: Optional[str] = None,
    wiki_id: Optional[str] = None,
    limit: int = 20,
    stale_after_seconds: Optional[int] = None,
) -> str:
    if not q:
        raise ValueError("q is required")
    ensure_wiki_cache_fresh(wiki_id=wiki_id, stale_after_seconds=stale_after_seconds)
    return json.dumps(search_wiki_cache(query=q, wiki_id=wiki_id, limit=limit))
