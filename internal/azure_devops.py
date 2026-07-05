import os
from typing import Optional
from dotenv import load_dotenv
from msrest.authentication import BasicAuthentication
from azure.devops.connection import Connection
from azure.devops.v7_1.work_item_tracking.models import Wiql, TeamContext
from azure.devops.v7_1.wiki.models import WikiPagesBatchRequest

load_dotenv()

MAX_SUBPAGES_FETCHED = 50


def _get_connection() -> Connection:
    org_url = os.getenv("AZURE_DEVOPS_ORG_URL")
    pat = os.getenv("AZURE_DEVOPS_PAT")
    if not org_url or not pat:
        raise ValueError("AZURE_DEVOPS_ORG_URL and AZURE_DEVOPS_PAT must be set")
    credentials = BasicAuthentication("", pat)
    return Connection(base_url=org_url, creds=credentials)


def _get_project() -> str:
    project = os.getenv("AZURE_DEVOPS_PROJECT")
    if not project:
        raise ValueError("AZURE_DEVOPS_PROJECT must be set")
    return project


def _extract_work_item_fields(item) -> dict:
    fields = item.fields
    assigned_to_raw = fields.get("System.AssignedTo")
    if isinstance(assigned_to_raw, dict):
        assigned_to = assigned_to_raw.get("displayName")
    else:
        assigned_to = assigned_to_raw
    return {
        "id": item.id,
        "parent_id": fields.get("System.Parent"),
        "title": fields.get("System.Title"),
        "state": fields.get("System.State"),
        "assigned_to": assigned_to,
        "area_path": fields.get("System.AreaPath"),
        "iteration_path": fields.get("System.IterationPath"),
        "priority": fields.get("Microsoft.VSTS.Common.Priority"),
        "created_date": str(fields.get("System.CreatedDate", "")),
        "changed_date": str(fields.get("System.ChangedDate", "")),
        "description": fields.get("System.Description"),
        "tags": fields.get("System.Tags"),
        "url": item.url,
    }


def _get_work_items_by_type(
    work_item_type: str,
    item_id: Optional[int] = None,
    sprint: Optional[str] = None,
    current_sprint: bool = False,
    team: Optional[str] = None,
    assignee: Optional[str] = None,
    state: Optional[str] = None,
    top: int = 100,
) -> list:
    connection = _get_connection()
    project = _get_project()
    client = connection.clients.get_work_item_tracking_client()

    if item_id is not None:
        item = client.get_work_item(item_id)
        return [_extract_work_item_fields(item)] if item else []

    conditions = [
        f"[System.TeamProject] = '{project}'",
        f"[System.WorkItemType] = '{work_item_type}'",
    ]
    if current_sprint:
        conditions.append("[System.IterationPath] = @CurrentIteration")
    elif sprint:
        conditions.append(f"[System.IterationPath] CONTAINS '{sprint}'")
    if assignee:
        conditions.append(f"[System.AssignedTo] CONTAINS '{assignee}'")
    if state:
        conditions.append(f"[System.State] = '{state}'")

    where_clause = " AND ".join(conditions)
    wiql = Wiql(query=f"SELECT [System.Id] FROM WorkItems WHERE {where_clause} ORDER BY [System.ChangedDate] DESC")

    team_context = TeamContext(project=project, team=team)
    query_result = client.query_by_wiql(wiql, team_context=team_context, top=top)
    work_item_refs = query_result.work_items

    if not work_item_refs:
        return []

    ids = [ref.id for ref in work_item_refs]
    items = []
    for chunk_start in range(0, len(ids), 200):
        chunk = ids[chunk_start:chunk_start + 200]
        batch = client.get_work_items(ids=chunk, error_policy="omit")
        items.extend([_extract_work_item_fields(i) for i in batch if i is not None])

    return items


def get_tasks(
    item_id: Optional[int] = None,
    sprint: Optional[str] = None,
    current_sprint: bool = False,
    team: Optional[str] = None,
    assignee: Optional[str] = None,
    state: Optional[str] = None,
    top: int = 100,
) -> list:
    return _get_work_items_by_type(
        "Task",
        item_id=item_id,
        sprint=sprint,
        current_sprint=current_sprint,
        team=team,
        assignee=assignee,
        state=state,
        top=top,
    )


def get_pbis(
    item_id: Optional[int] = None,
    sprint: Optional[str] = None,
    current_sprint: bool = False,
    team: Optional[str] = None,
    assignee: Optional[str] = None,
    state: Optional[str] = None,
    top: int = 100,
) -> list:
    return _get_work_items_by_type(
        "Product Backlog Item",
        item_id=item_id,
        sprint=sprint,
        current_sprint=current_sprint,
        team=team,
        assignee=assignee,
        state=state,
        top=top,
    )


def _extract_wiki_page_fields(page, wiki_id: str, wiki_name: Optional[str] = None) -> dict:
    return {
        "wiki_id": wiki_id,
        "wiki_name": wiki_name,
        "page_id": page.id,
        "path": page.path,
        "content": getattr(page, "content", None),
        "is_parent_page": page.is_parent_page,
        "order": page.order,
        "url": page.remote_url,
    }


def _get_pages_batch_page(wiki_client, project: str, wiki_identifier: str, top: int, continuation_token: Optional[str] = None):
    """Calls the GetPagesBatch REST API directly (instead of the SDK wrapper) so the
    `x-ms-continuationtoken` response header can be read; the SDK wrapper discards it."""
    request_body = WikiPagesBatchRequest(top=top, continuation_token=continuation_token)
    route_values = {
        "project": wiki_client._serialize.url("project", project, "str"),
        "wikiIdentifier": wiki_client._serialize.url("wiki_identifier", wiki_identifier, "str"),
    }
    content = wiki_client._serialize.body(request_body, "WikiPagesBatchRequest")
    response = wiki_client._send(
        http_method="POST",
        location_id="71323c46-2592-4398-8771-ced73dd87207",
        version="7.1-preview.1",
        route_values=route_values,
        query_parameters={},
        content=content,
    )
    pages = wiki_client._deserialize("[WikiPageDetail]", wiki_client._unwrap_collection(response))
    next_token = response.headers.get("x-ms-continuationtoken")
    return pages or [], next_token


def get_wiki_pages(wiki_id: Optional[str] = None, top: int = 100, continuation_token: Optional[str] = None) -> dict:
    connection = _get_connection()
    project = _get_project()
    wiki_client = connection.clients.get_wiki_client()

    if wiki_id:
        pages, next_token = _get_pages_batch_page(wiki_client, project, wiki_id, top, continuation_token)
        return {
            "pages": [
                {"wiki_id": wiki_id, "wiki_name": None, "page_id": page.id, "path": page.path}
                for page in pages
            ],
            "continuation_token": next_token,
        }

    wikis = wiki_client.get_all_wikis(project=project)
    if not wikis:
        return {"pages": [], "continuation_token": None}

    results = []
    for wiki in wikis:
        try:
            pages, _ = _get_pages_batch_page(wiki_client, project, wiki.id, top)
            for page in pages:
                results.append({
                    "wiki_id": wiki.id,
                    "wiki_name": wiki.name,
                    "page_id": page.id,
                    "path": page.path,
                })
        except Exception:
            pass

    return {"pages": results, "continuation_token": None}


def _build_subpage_tree(wiki_client, project: str, wiki_identifier: str, node, counter: list) -> tuple:
    """`node` comes from a recursion_level='full' response: it has the full descendant
    path tree, but each descendant is missing `id`/`content` (only the requested page
    itself gets those populated), so each descendant's content is fetched individually
    by path. `counter` is a single-element list shared across the whole recursion so the
    MAX_SUBPAGES_FETCHED cap applies to the total, not per branch."""
    children = []
    truncated = False
    for child in (node.sub_pages or []):
        if counter[0] >= MAX_SUBPAGES_FETCHED:
            return children, True
        counter[0] += 1
        child_response = wiki_client.get_page(
            project=project,
            wiki_identifier=wiki_identifier,
            path=child.path,
            include_content=True,
        )
        entry = _extract_wiki_page_fields(child_response.page, wiki_identifier)
        entry["sub_pages"], grandchild_truncated = _build_subpage_tree(wiki_client, project, wiki_identifier, child, counter)
        truncated = truncated or grandchild_truncated
        children.append(entry)

    return children, truncated


def get_wiki_page_by_path(path: str, wiki_id: Optional[str] = None) -> dict:
    connection = _get_connection()
    project = _get_project()
    wiki_client = connection.clients.get_wiki_client()

    wiki_identifier = wiki_id or project
    response = wiki_client.get_page(
        project=project,
        wiki_identifier=wiki_identifier,
        path=path,
        include_content=True,
        recursion_level="full",
    )
    result = _extract_wiki_page_fields(response.page, wiki_identifier)
    result["sub_pages"], result["sub_pages_truncated"] = _build_subpage_tree(wiki_client, project, wiki_identifier, response.page, [0])
    return result


def get_wiki_page_by_id(page_id: int, wiki_id: Optional[str] = None) -> dict:
    connection = _get_connection()
    project = _get_project()
    wiki_client = connection.clients.get_wiki_client()

    wiki_identifier = wiki_id or project
    response = wiki_client.get_page_by_id(
        project=project,
        wiki_identifier=wiki_identifier,
        id=page_id,
        include_content=True,
        recursion_level="full",
    )
    result = _extract_wiki_page_fields(response.page, wiki_identifier)
    result["sub_pages"], result["sub_pages_truncated"] = _build_subpage_tree(wiki_client, project, wiki_identifier, response.page, [0])
    return result
