from internal.azure_devops import get_pbis, get_tasks

from ..server import mcp


@mcp.prompt(
    name="pbi_breakdown_check",
    description="Build a prompt checking whether a PBI's child Tasks look complete and consistent with the PBI's state.",
)
def pbi_breakdown_check(pbi_id: int) -> str:
    pbis = get_pbis(item_id=pbi_id)
    if not pbis:
        raise ValueError(f"PBI {pbi_id} not found")
    pbi = pbis[0]

    tasks = get_tasks(parent_id=pbi_id)

    lines = [
        "Review whether this PBI's breakdown into Tasks looks complete and consistent. "
        "Flag missing task coverage, tasks left open while the PBI is closed, or any "
        "state mismatch.",
        "",
        f"## PBI #{pbi['id']} [{pbi['state']}] {pbi['title']}",
        pbi.get("description") or "(no description)",
        "",
        f"## Child Tasks ({len(tasks)})",
    ]
    for task in tasks:
        lines.append(f"- #{task['id']} [{task['state']}] {task['title']} (assignee: {task['assigned_to'] or 'unassigned'})")

    return "\n".join(lines)
