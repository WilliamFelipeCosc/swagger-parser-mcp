from fastapi import FastAPI, Query
from typing import Optional
from services.params import swagger_version
from internal.main import get_enums, get_modules, get_paths
from internal.azure_devops import get_tasks, get_pbis, get_wiki_pages, get_wiki_page_by_path, get_wiki_page_by_id

app = FastAPI()

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
    description="Get Azure DevOps Tasks. Filter by id (exact), assignee (substring), team/sprint board, current sprint (@CurrentIteration), sprint name (substring), or state.",
)
async def get_tasks_endpoint(
    id: Optional[int] = Query(default=None, description="Fetch a single task by its work item ID"),
    assignee: Optional[str] = Query(default=None, description="Filter by assignee display name (substring match)"),
    team: Optional[str] = Query(default=None, description="Sprint board team name (scopes @CurrentIteration and board context)"),
    current_sprint: bool = Query(default=False, description="Return only items in the team's current sprint (@CurrentIteration)"),
    sprint: Optional[str] = Query(default=None, description="Filter by sprint/iteration path (substring match); ignored when current_sprint=true"),
    state: Optional[str] = Query(default=None, description="Filter by work item state, e.g. 'Active', 'New', 'Closed'"),
    top: int = Query(default=100, description="Maximum number of items to return"),
):
    return get_tasks(item_id=id, sprint=sprint, current_sprint=current_sprint, team=team, assignee=assignee, state=state, top=top)


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