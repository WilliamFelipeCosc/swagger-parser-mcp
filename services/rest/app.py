from fastapi import FastAPI, HTTPException, Query
from typing import Optional
from services.params import swagger_version
from internal.swagger import get_enums, get_modules, get_paths
from internal.azure_devops import (
    get_tasks,
    get_pbis,
    get_wiki_pages,
    get_wiki_page_by_path,
    get_wiki_page_by_id,
    sync_wiki_cache,
)
from internal.db import (
    search_wiki_cache,
    get_wiki_tree,
    get_wiki_subtree,
    get_wiki_cache_status,
)

app = FastAPI(
    title="Swagger REST API",
    description="REST API for the Swagger MCP project (Swagger parsing + Azure DevOps). Independent of the MCP server at /mcp.",
)

@app.get("/{version}/enums", operation_id="get_enums", description="Get all enums defined in the Swagger JSON for the specified version.")
async def get_enums_endpoint(version: swagger_version):
    enums = get_enums(version)
    return enums

@app.get("/{version}/paths/{module_name}", operation_id="get_paths_by_module", description="Get all paths for a specified module in the Swagger JSON for the specified version.")
async def get_paths_endpoint(version: swagger_version, module_name: str):
    paths = get_paths(version, module_name)
    return paths

@app.get("/{version}/modules", operation_id="get_all_modules", description="Get all modules defined in the Swagger JSON for the specified version.")
async def get_modules_endpoint(version: swagger_version):
    modules = get_modules(version)
    return modules


@app.get(
    "/azure/tasks",
    operation_id="get_azure_devops_tasks",
    description="Get Azure DevOps Tasks. Filter by id (exact), parent_id (exact), assignee (substring), team/sprint board, current sprint (@CurrentIteration), sprint name (substring), or state.",
)
async def get_tasks_endpoint(
    id: Optional[int] = Query(default=None, description="Fetch a single task by its work item ID"),
    parent_id: Optional[int] = Query(default=None, description="Filter by parent PBI's work item ID"),
    assignee: Optional[str] = Query(default=None, description="Filter by assignee display name (substring match)"),
    team: Optional[str] = Query(default=None, description="Sprint board team name (scopes @CurrentIteration and board context)"),
    current_sprint: bool = Query(default=False, description="Return only items in the team's current sprint (@CurrentIteration)"),
    sprint: Optional[str] = Query(default=None, description="Filter by sprint/iteration path (substring match); ignored when current_sprint=true"),
    state: Optional[str] = Query(default=None, description="Filter by work item state, e.g. 'Active', 'New', 'Closed'"),
    top: int = Query(default=100, description="Maximum number of items to return"),
):
    return get_tasks(item_id=id, parent_id=parent_id, sprint=sprint, current_sprint=current_sprint, team=team, assignee=assignee, state=state, top=top)


@app.get(
    "/azure/pbis",
    operation_id="get_azure_devops_pbis",
    description="Get Azure DevOps Product Backlog Items (PBIs). Filter by id (exact), assignee (substring), team/sprint board, current sprint (@CurrentIteration), sprint name (substring), or state.",
)
async def get_pbis_endpoint(
    id: Optional[int] = Query(default=None, description="Fetch a single PBI by its work item ID"),
    assignee: Optional[str] = Query(default=None, description="Filter by assignee display name (substring match)"),
    team: Optional[str] = Query(default=None, description="Sprint board team name (scopes @CurrentIteration and board context)"),
    current_sprint: bool = Query(default=False, description="Return only items in the team's current sprint (@CurrentIteration)"),
    sprint: Optional[str] = Query(default=None, description="Filter by sprint/iteration path (substring match); ignored when current_sprint=true"),
    state: Optional[str] = Query(default=None, description="Filter by work item state, e.g. 'Active', 'New', 'Closed'"),
    top: int = Query(default=100, description="Maximum number of items to return"),
):
    return get_pbis(item_id=id, sprint=sprint, current_sprint=current_sprint, team=team, assignee=assignee, state=state, top=top)


@app.get(
    "/azure/wiki",
    operation_id="get_azure_devops_wiki_pages",
    description=(
        "List wiki pages from Azure DevOps (metadata only: page_id, path). Returns "
        "{\"pages\": [...], \"continuation_token\": ...}. Pass wiki_id to target a specific wiki; "
        "pagination (top, continuation_token) only takes effect when wiki_id is set — pass the "
        "returned continuation_token back in to fetch the next page. If wiki_id is omitted, all "
        "wikis in the project are listed (up to `top` pages each, no pagination, continuation_token "
        "is always null). Use get_azure_devops_wiki_page_by_path or get_azure_devops_wiki_page_by_id "
        "to fetch a page's content."
    ),
)
async def get_wiki_pages_endpoint(
    wiki_id: Optional[str] = Query(default=None, description="ID or name of a specific wiki. If omitted, all wikis are returned."),
    top: int = Query(default=100, description="Maximum number of pages to return (per wiki, if wiki_id is omitted)"),
    continuation_token: Optional[str] = Query(default=None, description="Token from a previous response's continuation_token, to fetch the next page. Only effective when wiki_id is set."),
):
    return get_wiki_pages(wiki_id=wiki_id, top=top, continuation_token=continuation_token)


@app.get(
    "/azure/wiki/page",
    operation_id="get_azure_devops_wiki_page_by_path",
    description="Get a wiki page's content by its path. If wiki_id is omitted, defaults to the project's default wiki.",
)
async def get_wiki_page_by_path_endpoint(
    path: str = Query(description="Path of the wiki page, e.g. '/Home' or '/Folder/Page'"),
    wiki_id: Optional[str] = Query(default=None, description="ID or name of the wiki. Defaults to the project's default wiki if omitted."),
):
    return get_wiki_page_by_path(path=path, wiki_id=wiki_id)


@app.get(
    "/azure/wiki/page/{page_id}",
    operation_id="get_azure_devops_wiki_page_by_id",
    description="Get a wiki page's content by its page ID. If wiki_id is omitted, defaults to the project's default wiki.",
)
async def get_wiki_page_by_id_endpoint(
    page_id: int,
    wiki_id: Optional[str] = Query(default=None, description="ID or name of the wiki. Defaults to the project's default wiki if omitted."),
):
    return get_wiki_page_by_id(page_id=page_id, wiki_id=wiki_id)


@app.post(
    "/azure/wiki/cache/sync",
    operation_id="sync_azure_devops_wiki_cache",
    description=(
        "Rebuilds the local SQLite+FTS5 cache for one wiki: paginates through every page and "
        "(by default) fetches each page's content individually, then replaces that wiki's cached "
        "rows. Can be slow for large wikis (one API call per page when fetch_content=true). Call "
        "this before using search/tree/status — the cache starts empty."
    ),
)
async def sync_wiki_cache_endpoint(
    wiki_id: str = Query(description="ID or name of the wiki to sync"),
    fetch_content: bool = Query(default=True, description="Fetch each page's content for full-text search. If false, only structure (path/hierarchy) is cached."),
):
    return sync_wiki_cache(wiki_id=wiki_id, fetch_content=fetch_content)


@app.get(
    "/azure/wiki/cache/search",
    operation_id="search_azure_devops_wiki_cache",
    description="Full-text search over the cached wiki pages (path + content) using SQLite FTS5. Requires a prior sync via sync_azure_devops_wiki_cache. Query supports FTS5 syntax (phrases in quotes, AND/OR/NOT, prefix*).",
)
async def search_wiki_cache_endpoint(
    q: str = Query(description="FTS5 search query"),
    wiki_id: Optional[str] = Query(default=None, description="Restrict results to a specific wiki. If omitted, searches across all cached wikis."),
    limit: int = Query(default=20, description="Maximum number of results to return"),
):
    return search_wiki_cache(query=q, wiki_id=wiki_id, limit=limit)


@app.get(
    "/azure/wiki/cache/tree",
    operation_id="get_azure_devops_wiki_cache_tree",
    description="Get the cached wiki page hierarchy as a nested tree (no Azure DevOps API calls, reflects the last sync). Requires a prior sync via sync_azure_devops_wiki_cache.",
)
async def get_wiki_cache_tree_endpoint(
    wiki_id: Optional[str] = Query(default=None, description="Restrict to a specific wiki. If omitted, returns trees for all cached wikis."),
):
    return get_wiki_tree(wiki_id=wiki_id)


@app.get(
    "/azure/wiki/cache/structure",
    operation_id="get_azure_devops_wiki_cache_structure",
    description=(
        "Get the cached folder/path structure (no content) of the subtree rooted at a specific "
        "page — e.g. root_page_id=589 for '/Wiki Nivello/Produto & Agilidade' returns that page "
        "plus every descendant path underneath it, nested as sub_pages. No Azure DevOps API calls; "
        "reflects the last sync. Requires a prior sync via sync_azure_devops_wiki_cache. Pass "
        "exactly one of root_page_id or root_path."
    ),
)
async def get_wiki_cache_structure_endpoint(
    wiki_id: str = Query(description="ID or name of the wiki"),
    root_page_id: Optional[int] = Query(default=None, description="Page ID to root the subtree at"),
    root_path: Optional[str] = Query(default=None, description="Page path to root the subtree at (used if root_page_id is omitted)"),
):
    if root_page_id is None and root_path is None:
        raise HTTPException(status_code=400, detail="root_page_id or root_path is required")
    subtree = get_wiki_subtree(wiki_id=wiki_id, root_page_id=root_page_id, root_path=root_path)
    if subtree is None:
        raise HTTPException(status_code=404, detail="Page not found in cache. Has this wiki been synced?")
    return subtree


@app.get(
    "/azure/wiki/cache/status",
    operation_id="get_azure_devops_wiki_cache_status",
    description="Get cache stats per wiki: page count, pages with content cached, and the last sync timestamp.",
)
async def get_wiki_cache_status_endpoint(
    wiki_id: Optional[str] = Query(default=None, description="Restrict to a specific wiki. If omitted, returns stats for all cached wikis."),
):
    return get_wiki_cache_status(wiki_id=wiki_id)
