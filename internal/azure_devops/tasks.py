from typing import Optional
from azure.devops.v7_1.work_item_tracking.models import Wiql, TeamContext
from .shared import _get_connection, _get_project


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
