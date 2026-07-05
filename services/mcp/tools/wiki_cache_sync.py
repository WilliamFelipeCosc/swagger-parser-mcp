from internal.azure_devops import sync_wiki_cache

from ..server import mcp


@mcp.tool(
    name="sync_azure_devops_wiki_cache",
    description=(
        "Rebuilds the local SQLite+FTS5 cache for one wiki: paginates through every page "
        "and (by default) fetches each page's content individually, then replaces that "
        "wiki's cached rows. Can be slow for large wikis (one API call per page when "
        "fetch_content=true). Call this before using the wiki-cache resources — the cache "
        "starts empty."
    ),
)
def sync_azure_devops_wiki_cache(wiki_id: str, fetch_content: bool = True) -> dict:
    return sync_wiki_cache(wiki_id=wiki_id, fetch_content=fetch_content)
