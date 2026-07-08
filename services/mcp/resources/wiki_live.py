import json
from typing import Optional

from internal.azure_devops import get_wiki_page_by_id, get_wiki_page_by_path, get_wiki_pages

from ..server import mcp


@mcp.resource(
    "wiki://pages{?top}",
    name="AllWikisPages",
    description=(
        "List wiki pages from every wiki in the project (metadata only: page_id, path). "
        "Up to `top` pages per wiki, no cross-wiki pagination."
    ),
    mime_type="application/json",
)
def all_wikis_pages(top: int = 100) -> str:
    return json.dumps(get_wiki_pages(wiki_id=None, top=top))


@mcp.resource(
    "wiki://{wiki_id}/pages{?top,continuation_token}",
    name="WikiPages",
    description=(
        "List wiki pages from a specific wiki (metadata only: page_id, path). Returns "
        "{pages, continuation_token}; pass the returned continuation_token back in the "
        "query string to fetch the next page."
    ),
    mime_type="application/json",
)
def wiki_pages(wiki_id: str, top: int = 100, continuation_token: Optional[str] = None) -> str:
    return json.dumps(get_wiki_pages(wiki_id=wiki_id, top=top, continuation_token=continuation_token))


@mcp.resource(
    "wiki://page-by-path{?path}",
    name="DefaultWikiPageByPath",
    description="Get a wiki page's content (and subpages) by path (required), from the project's default wiki.",
    mime_type="application/json",
)
def default_wiki_page_by_path(path: Optional[str] = None) -> str:
    if not path:
        raise ValueError("path is required")
    return json.dumps(get_wiki_page_by_path(path=path, wiki_id=None))


@mcp.resource(
    "wiki://{wiki_id}/page-by-path{?path}",
    name="WikiPageByPath",
    description="Get a wiki page's content (and subpages) by path (required), from a specific wiki.",
    mime_type="application/json",
)
def wiki_page_by_path(wiki_id: str, path: Optional[str] = None) -> str:
    if not path:
        raise ValueError("path is required")
    return json.dumps(get_wiki_page_by_path(path=path, wiki_id=wiki_id))


@mcp.resource(
    "wiki://page-by-id/{page_id}",
    name="DefaultWikiPageById",
    description="Get a wiki page's content (and subpages) by page ID, from the project's default wiki.",
    mime_type="application/json",
)
def default_wiki_page_by_id(page_id: int) -> str:
    return json.dumps(get_wiki_page_by_id(page_id=page_id, wiki_id=None))


@mcp.resource(
    "wiki://{wiki_id}/page-by-id/{page_id}",
    name="WikiPageById",
    description="Get a wiki page's content (and subpages) by page ID, from a specific wiki.",
    mime_type="application/json",
)
def wiki_page_by_id(wiki_id: str, page_id: int) -> str:
    return json.dumps(get_wiki_page_by_id(page_id=page_id, wiki_id=wiki_id))
