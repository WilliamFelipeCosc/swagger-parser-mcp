from typing import Optional
from azure.devops.v7_1.work_item_tracking.models import Wiql, TeamContext
from .shared import _get_connection, _get_project


def _extract_comment_fields(comment) -> dict:
    created_by_raw = comment.created_by
    created_by = created_by_raw.display_name if created_by_raw else None
    return {
        "id": comment.id,
        "text": comment.text,
        "created_by": created_by,
        "created_date": str(comment.created_date) if comment.created_date else None,
    }


def _get_work_item_comments(client, project: str, work_item_id: int) -> list:
    comment_list = client.get_comments(project, work_item_id)
    return [_extract_comment_fields(c) for c in (comment_list.comments or [])]


CHILD_TYPE = {
    "Product Backlog Item": "Task",
    "Feature": "Product Backlog Item",
    "Epic": "Feature",
}

# Azure DevOps only returns the fields a work item's default view includes unless a `fields`
# list is passed explicitly — System.Parent in particular is populated but silently omitted
# without this, even though it's queryable via WIQL. Every field _extract_work_item_fields
# reads must be listed here.
REQUESTED_FIELDS = [
    "System.Id",
    "System.Parent",
    "System.Title",
    "System.State",
    "System.AssignedTo",
    "System.AreaPath",
    "System.IterationPath",
    "Microsoft.VSTS.Common.Priority",
    "Microsoft.VSTS.Scheduling.Effort",
    "Microsoft.VSTS.Common.BusinessValue",
    "Microsoft.VSTS.Common.TimeCriticality",
    "Microsoft.VSTS.Scheduling.StartDate",
    "Microsoft.VSTS.Scheduling.TargetDate",
    "System.CreatedDate",
    "System.ChangedDate",
    "System.Description",
    "System.Tags",
]


def _extract_work_item_fields(item) -> dict:
    fields = item.fields
    assigned_to_raw = fields.get("System.AssignedTo")
    if isinstance(assigned_to_raw, dict):
        assigned_to = assigned_to_raw.get("displayName")
    else:
        assigned_to = assigned_to_raw
    start_date = fields.get("Microsoft.VSTS.Scheduling.StartDate")
    target_date = fields.get("Microsoft.VSTS.Scheduling.TargetDate")
    return {
        "id": item.id,
        "parent_id": fields.get("System.Parent"),
        "title": fields.get("System.Title"),
        "state": fields.get("System.State"),
        "assigned_to": assigned_to,
        "area_path": fields.get("System.AreaPath"),
        "iteration_path": fields.get("System.IterationPath"),
        "priority": fields.get("Microsoft.VSTS.Common.Priority"),
        "effort": fields.get("Microsoft.VSTS.Scheduling.Effort"),
        "business_value": fields.get("Microsoft.VSTS.Common.BusinessValue"),
        "time_criticality": fields.get("Microsoft.VSTS.Common.TimeCriticality"),
        "start_date": str(start_date) if start_date else None,
        "target_date": str(target_date) if target_date else None,
        "created_date": str(fields.get("System.CreatedDate", "")),
        "changed_date": str(fields.get("System.ChangedDate", "")),
        "description": fields.get("System.Description"),
        "tags": fields.get("System.Tags"),
        "url": item.url,
    }


def _get_child_work_items(client, project: str, item_id: int, child_type: str) -> list:
    wiql = Wiql(
        query=(
            "SELECT [System.Id] FROM WorkItems WHERE "
            f"[System.TeamProject] = '{project}' AND "
            f"[System.WorkItemType] = '{child_type}' AND "
            f"[System.Parent] = {item_id} "
            "ORDER BY [System.ChangedDate] DESC"
        )
    )
    query_result = client.query_by_wiql(wiql, top=200)
    work_item_refs = query_result.work_items
    if not work_item_refs:
        return []

    ids = [ref.id for ref in work_item_refs]
    items = []
    for chunk_start in range(0, len(ids), 200):
        chunk = ids[chunk_start:chunk_start + 200]
        batch = client.get_work_items(ids=chunk, fields=REQUESTED_FIELDS, error_policy="omit")
        items.extend([_extract_work_item_fields(i) for i in batch if i is not None])
    return items


def _get_work_items_by_type(
    work_item_type: str,
    item_id: Optional[int] = None,
    parent_id: Optional[int] = None,
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
        item = client.get_work_item(item_id, fields=REQUESTED_FIELDS)
        if not item:
            return []
        fields = _extract_work_item_fields(item)
        fields["comments"] = _get_work_item_comments(client, project, item_id)
        child_type = CHILD_TYPE.get(work_item_type)
        if child_type:
            fields["children"] = _get_child_work_items(client, project, item_id, child_type)
        return [fields]

    conditions = [
        f"[System.TeamProject] = '{project}'",
        f"[System.WorkItemType] = '{work_item_type}'",
    ]
    if parent_id is not None:
        conditions.append(f"[System.Parent] = {parent_id}")
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
        batch = client.get_work_items(ids=chunk, fields=REQUESTED_FIELDS, error_policy="omit")
        items.extend([_extract_work_item_fields(i) for i in batch if i is not None])

    return items


def get_tasks(
    item_id: Optional[int] = None,
    parent_id: Optional[int] = None,
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
        parent_id=parent_id,
        sprint=sprint,
        current_sprint=current_sprint,
        team=team,
        assignee=assignee,
        state=state,
        top=top,
    )


def get_pbis(
    item_id: Optional[int] = None,
    parent_id: Optional[int] = None,
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
        parent_id=parent_id,
        sprint=sprint,
        current_sprint=current_sprint,
        team=team,
        assignee=assignee,
        state=state,
        top=top,
    )


def get_features(
    item_id: Optional[int] = None,
    parent_id: Optional[int] = None,
    sprint: Optional[str] = None,
    current_sprint: bool = False,
    team: Optional[str] = None,
    assignee: Optional[str] = None,
    state: Optional[str] = None,
    top: int = 100,
) -> list:
    return _get_work_items_by_type(
        "Feature",
        item_id=item_id,
        parent_id=parent_id,
        sprint=sprint,
        current_sprint=current_sprint,
        team=team,
        assignee=assignee,
        state=state,
        top=top,
    )


def get_epics(
    item_id: Optional[int] = None,
    sprint: Optional[str] = None,
    current_sprint: bool = False,
    team: Optional[str] = None,
    assignee: Optional[str] = None,
    state: Optional[str] = None,
    top: int = 100,
) -> list:
    return _get_work_items_by_type(
        "Epic",
        item_id=item_id,
        sprint=sprint,
        current_sprint=current_sprint,
        team=team,
        assignee=assignee,
        state=state,
        top=top,
    )
