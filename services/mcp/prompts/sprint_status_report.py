from typing import Optional

from internal.azure_devops import get_pbis, get_tasks

from ..server import mcp


@mcp.prompt(
    name="sprint_status_report",
    description="Build a status-report prompt for a sprint, grouping Tasks and PBIs by assignee and state.",
)
def sprint_status_report(
    team: Optional[str] = None,
    sprint: Optional[str] = None,
    current_sprint: bool = True,
) -> str:
    tasks = get_tasks(team=team, sprint=sprint, current_sprint=current_sprint)
    pbis = get_pbis(team=team, sprint=sprint, current_sprint=current_sprint)

    lines = [
        "You are preparing a sprint status report. Group the items below by assignee, "
        "then by state, and call out any item that looks stalled or unassigned.",
        "",
        f"## Product Backlog Items ({len(pbis)})",
    ]
    for pbi in pbis:
        lines.append(f"- #{pbi['id']} [{pbi['state']}] {pbi['title']} (assignee: {pbi['assigned_to'] or 'unassigned'})")

    lines.append("")
    lines.append(f"## Tasks ({len(tasks)})")
    for task in tasks:
        lines.append(
            f"- #{task['id']} [{task['state']}] {task['title']} "
            f"(parent: {task['parent_id'] or 'none'}, assignee: {task['assigned_to'] or 'unassigned'})"
        )

    return "\n".join(lines)
