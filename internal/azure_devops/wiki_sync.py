from internal.db import replace_wiki_pages

from .shared import _get_connection, _get_project
from .wiki import _get_pages_batch_page


def sync_wiki_cache(wiki_id: str, fetch_content: bool = True) -> dict:
    """Rebuilds the local cache for a single wiki: paginates through every page via
    GetPagesBatch, optionally fetches each page's content individually (Azure DevOps has
    no bulk-content endpoint), then replaces that wiki's cached rows via
    internal.db.replace_wiki_pages."""
    connection = _get_connection()
    project = _get_project()
    wiki_client = connection.clients.get_wiki_client()

    all_pages = []
    continuation_token = None
    while True:
        pages, continuation_token = _get_pages_batch_page(wiki_client, project, wiki_id, 100, continuation_token)
        all_pages.extend(pages)
        if not continuation_token:
            break

    pages_payload = []
    for page in all_pages:
        content = None
        if fetch_content:
            try:
                page_response = wiki_client.get_page_by_id(
                    project=project, wiki_identifier=wiki_id, id=page.id, include_content=True
                )
                content = getattr(page_response.page, "content", None)
            except Exception:
                pass
        pages_payload.append({"page_id": page.id, "path": page.path, "content": content})

    return replace_wiki_pages(wiki_id, pages_payload)
