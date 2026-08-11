from typing import Optional

from internal.azure_devops import get_pbis, get_tasks

from ..server import mcp


@mcp.tool(
    name="get_azure_devops_tasks",
    description=(
        "Get Azure DevOps Tasks. Filter by id (exact), parent_id (exact, the parent PBI's "
        "work item ID), assignee (substring), team/sprint board, current sprint "
        "(@CurrentIteration), sprint name (substring), or state. When id is set, the result "
        "also includes a comments list (id, text, created_by, created_date) — omitted for "
        "multi-result queries to avoid one extra API call per item."
    ),
)
def get_azure_devops_tasks(
    id: Optional[int] = None,
    parent_id: Optional[int] = None,
    assignee: Optional[str] = None,
    team: Optional[str] = None,
    current_sprint: bool = False,
    sprint: Optional[str] = None,
    state: Optional[str] = None,
    top: int = 100,
) -> list:
    return get_tasks(
        item_id=id,
        parent_id=parent_id,
        sprint=sprint,
        current_sprint=current_sprint,
        team=team,
        assignee=assignee,
        state=state,
        top=top,
    )


@mcp.tool(
    name="get_azure_devops_pbis",
    description=(
        "Get Azure DevOps Product Backlog Items (PBIs). Filter by id (exact), assignee "
        "(substring), team/sprint board, current sprint (@CurrentIteration), sprint name "
        "(substring), or state. When id is set, the result also includes a comments list "
        "(id, text, created_by, created_date) — omitted for multi-result queries to avoid "
        "one extra API call per item."
    ),
)
def get_azure_devops_pbis(
    id: Optional[int] = None,
    assignee: Optional[str] = None,
    team: Optional[str] = None,
    current_sprint: bool = False,
    sprint: Optional[str] = None,
    state: Optional[str] = None,
    top: int = 100,
) -> list:
    return get_pbis(
        item_id=id,
        sprint=sprint,
        current_sprint=current_sprint,
        team=team,
        assignee=assignee,
        state=state,
        top=top,
    )
