from typing import Optional

from internal.azure_devops import get_wiki_page_by_id, get_wiki_page_by_path

from ..server import mcp


def _flatten(page: dict, acc: list) -> None:
    if page.get("content"):
        acc.append(f"### {page['path']}\n\n{page['content']}")
    for sub_page in page.get("sub_pages") or []:
        _flatten(sub_page, acc)


@mcp.prompt(
    name="wiki_page_digest",
    description="Build a prompt asking for a digest/summary of a wiki page and all its subpages.",
)
def wiki_page_digest(
    path: Optional[str] = None,
    page_id: Optional[int] = None,
    wiki_id: Optional[str] = None,
) -> str:
    if page_id is not None:
        page = get_wiki_page_by_id(page_id=page_id, wiki_id=wiki_id)
    elif path is not None:
        page = get_wiki_page_by_path(path=path, wiki_id=wiki_id)
    else:
        raise ValueError("path or page_id is required")

    sections = []
    _flatten(page, sections)

    return (
        "Summarize the following wiki page and its subpages into a concise digest. Call "
        "out anything that looks outdated or contradictory across sections.\n\n"
        + "\n\n".join(sections)
    )
