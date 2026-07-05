import re
from typing import Optional

from fastmcp import Context

from internal.azure_devops import ensure_wiki_cache_fresh, get_pbis, get_tasks
from internal.db import search_wiki_cache

from ..server import mcp

_FTS5_SPECIAL_CHARS = re.compile(r'["():*^{}]')


def _sanitize_fts5_query(text: str) -> str:
    """Strips FTS5 query-syntax characters from free text (e.g. a PBI title) so it can
    be used as a search term without risking a MATCH syntax error (an unbalanced quote
    or paren) or unintended operators."""
    cleaned = _FTS5_SPECIAL_CHARS.sub(" ", text)
    return " ".join(cleaned.split())


@mcp.tool(
    name="get_azure_devops_tasks",
    description=(
        "Get Azure DevOps Tasks. Filter by id (exact), parent_id (exact, the parent PBI's "
        "work item ID), assignee (substring), team/sprint board, current sprint "
        "(@CurrentIteration), sprint name (substring), or state."
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
        "(substring), or state. When fetching a single PBI by id, asks (via MCP "
        "elicitation) for a search term to look up additional context in the wiki cache "
        "— if one is provided, adds a wiki_context field (see "
        "search_azure_devops_wiki_cache's result shape) to that PBI. Skipped entirely if "
        "the client doesn't support elicitation, if more than one PBI is returned, or if "
        "the user declines/cancels/leaves the term blank."
    ),
)
async def get_azure_devops_pbis(
    id: Optional[int] = None,
    assignee: Optional[str] = None,
    team: Optional[str] = None,
    current_sprint: bool = False,
    sprint: Optional[str] = None,
    state: Optional[str] = None,
    top: int = 100,
    ctx: Context = None,
) -> list:
    pbis = get_pbis(
        item_id=id,
        sprint=sprint,
        current_sprint=current_sprint,
        team=team,
        assignee=assignee,
        state=state,
        top=top,
    )

    if ctx is not None and id is not None and len(pbis) == 1:
        pbi = pbis[0]
        try:
            elicitation = await ctx.elicit(
                message=(
                    f"Deseja pesquisar a wiki por contexto adicional sobre a PBI "
                    f"#{pbi['id']} ({pbi['title']})? Digite o termo de busca."
                ),
                response_type=str,
                response_title="Termo de busca",
            )
        except Exception:
            elicitation = None

        if elicitation is not None and elicitation.action == "accept":
            query = _sanitize_fts5_query(elicitation.data or "")
            if query:
                ensure_wiki_cache_fresh()
                pbi["wiki_context"] = search_wiki_cache(query=query, limit=5)

    return pbis
