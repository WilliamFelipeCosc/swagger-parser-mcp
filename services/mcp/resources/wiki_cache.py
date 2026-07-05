import json
from typing import Optional

from internal.db import (
    get_wiki_cache_status,
    get_wiki_subtree,
    get_wiki_tree,
    search_wiki_cache,
)

from ..server import mcp


@mcp.resource(
    "wiki-cache://tree{?wiki_id}",
    name="WikiCacheTree",
    description=(
        "Get the cached wiki page hierarchy as a nested tree (no Azure DevOps API calls, "
        "reflects the last sync). Requires a prior sync via sync_azure_devops_wiki_cache. "
        "Omit wiki_id to get trees for all cached wikis."
    ),
    mime_type="application/json",
)
def wiki_cache_tree(wiki_id: Optional[str] = None) -> str:
    return json.dumps(get_wiki_tree(wiki_id=wiki_id))


@mcp.resource(
    "wiki-cache://{wiki_id}/structure{?root_page_id,root_path}",
    name="WikiCacheStructure",
    description=(
        "Get the cached folder/path structure (no content) of the subtree rooted at a "
        "specific page in one wiki — e.g. root_page_id=589 for '/Wiki Nivello/Produto & "
        "Agilidade' returns that page plus every descendant path underneath it, nested as "
        "sub_pages. No Azure DevOps API calls; reflects the last sync. Pass exactly one of "
        "root_page_id or root_path."
    ),
    mime_type="application/json",
)
def wiki_cache_structure(wiki_id: str, root_page_id: Optional[int] = None, root_path: Optional[str] = None) -> str:
    if root_page_id is None and root_path is None:
        raise ValueError("root_page_id or root_path is required")
    subtree = get_wiki_subtree(wiki_id=wiki_id, root_page_id=root_page_id, root_path=root_path)
    if subtree is None:
        raise ValueError("Page not found in cache. Has this wiki been synced?")
    return json.dumps(subtree)


@mcp.resource(
    "wiki-cache://status{?wiki_id}",
    name="WikiCacheStatus",
    description=(
        "Get cache stats per wiki: page count, pages with content cached, and the last "
        "sync timestamp. Useful for checking staleness before relying on the tree, "
        "structure, or search resources. Omit wiki_id for stats on all cached wikis."
    ),
    mime_type="application/json",
)
def wiki_cache_status(wiki_id: Optional[str] = None) -> str:
    return json.dumps(get_wiki_cache_status(wiki_id=wiki_id))


@mcp.resource(
    "wiki-cache://search{?q,wiki_id,limit}",
    name="WikiCacheSearch",
    description=(
        "Full-text search over the cached wiki pages (path + content) using SQLite FTS5. "
        "Requires a prior sync via sync_azure_devops_wiki_cache. `q` (required) supports "
        "FTS5 syntax (phrases in quotes, AND/OR/NOT, prefix*). Omit wiki_id to search "
        "across all cached wikis."
    ),
    mime_type="application/json",
)
def wiki_cache_search(q: Optional[str] = None, wiki_id: Optional[str] = None, limit: int = 20) -> str:
    if not q:
        raise ValueError("q is required")
    return json.dumps(search_wiki_cache(query=q, wiki_id=wiki_id, limit=limit))
