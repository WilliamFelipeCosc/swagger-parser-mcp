import logging
import os
from datetime import datetime, timezone
from typing import Optional

from internal.db import (
    get_all_cached_wiki_ids,
    get_cached_wiki_pages,
    get_wiki_cache_last_checked_at,
    record_wiki_cache_check,
    replace_wiki_pages,
)

from .shared import _get_connection, _get_project
from .wiki import _get_pages_batch_page

logger = logging.getLogger(__name__)

DEFAULT_STALE_SECONDS = 24 * 60 * 60  # 1 day


def _get_default_stale_seconds() -> int:
    return int(os.getenv("WIKI_CACHE_STALE_SECONDS", DEFAULT_STALE_SECONDS))


def _fetch_git_modified_dates(git_client, repository_id: str, project: str) -> dict:
    """Returns {git_item_path: iso_date_str} for every markdown file in the wiki's backing
    git repository, via a single bulk GetItems call (with latest_processed_change=True) —
    much cheaper than asking Azure DevOps for each page's history individually."""
    items = git_client.get_items(
        repository_id=repository_id,
        project=project,
        scope_path="/",
        recursion_level="full",
        latest_processed_change=True,
    )
    modified_dates = {}
    for item in items or []:
        if not item.path.endswith(".md"):
            continue
        change = item.latest_processed_change
        committer = getattr(change, "committer", None) if change else None
        if committer and committer.date:
            modified_dates[item.path] = committer.date.isoformat()
    return modified_dates


def _fetch_page_content(wiki_client, project: str, wiki_id: str, page_id: int, modified_dates: dict) -> dict:
    try:
        page_response = wiki_client.get_page_by_id(
            project=project, wiki_identifier=wiki_id, id=page_id, include_content=True
        )
        page = page_response.page
        git_item_path = getattr(page, "git_item_path", None)
        return {
            "content": getattr(page, "content", None),
            "git_item_path": git_item_path,
            "content_modified_at": modified_dates.get(git_item_path),
        }
    except Exception:
        return {"content": None, "git_item_path": None, "content_modified_at": None}


def sync_wiki_cache(wiki_id: str, fetch_content: bool = True) -> dict:
    """Full/bootstrap resync: paginates through every page via GetPagesBatch, optionally
    fetches each page's content individually (Azure DevOps has no bulk-content endpoint),
    then replaces that wiki's cached rows via internal.db.replace_wiki_pages. When
    fetching content, also captures each page's git_item_path and live modification date
    (one bulk GetItems call) so check_and_refresh_wiki_cache has a baseline to diff
    against afterwards."""
    connection = _get_connection()
    project = _get_project()
    wiki_client = connection.clients.get_wiki_client()
    git_client = connection.clients.get_git_client()

    all_pages = []
    continuation_token = None
    while True:
        pages, continuation_token = _get_pages_batch_page(wiki_client, project, wiki_id, 100, continuation_token)
        all_pages.extend(pages)
        if not continuation_token:
            break

    modified_dates = {}
    if fetch_content:
        wiki = wiki_client.get_wiki(project=project, wiki_identifier=wiki_id)
        modified_dates = _fetch_git_modified_dates(git_client, wiki.repository_id, project)

    pages_payload = []
    for page in all_pages:
        metadata = {"content": None, "git_item_path": None, "content_modified_at": None}
        if fetch_content:
            metadata = _fetch_page_content(wiki_client, project, wiki_id, page.id, modified_dates)
        pages_payload.append({"page_id": page.id, "path": page.path, **metadata})

    result = replace_wiki_pages(wiki_id, pages_payload)
    record_wiki_cache_check(wiki_id)
    return result


def check_and_refresh_wiki_cache(wiki_id: str, stale_after_seconds: Optional[int] = None) -> dict:
    """Cheap staleness check + incremental refresh for one wiki. Skips all Azure calls if
    the cache was checked more recently than `stale_after_seconds` ago (default
    WIKI_CACHE_STALE_SECONDS, 1 day). Otherwise: lists current pages (GetPagesBatch) and
    their live modification dates (one bulk GetItems call), reuses cached content for
    pages that haven't changed, and only re-fetches content for pages that are new or
    whose live modification date is newer than what's cached. Also drops pages that no
    longer exist live. Returns {"checked": False} without touching Azure if the cache was
    still fresh."""
    stale_after = stale_after_seconds if stale_after_seconds is not None else _get_default_stale_seconds()

    last_checked = get_wiki_cache_last_checked_at(wiki_id)
    if last_checked is not None:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(last_checked)).total_seconds()
        if age < stale_after:
            return {"wiki_id": wiki_id, "checked": False, "reason": "fresh", "age_seconds": age}

    connection = _get_connection()
    project = _get_project()
    wiki_client = connection.clients.get_wiki_client()
    git_client = connection.clients.get_git_client()

    wiki = wiki_client.get_wiki(project=project, wiki_identifier=wiki_id)
    modified_dates = _fetch_git_modified_dates(git_client, wiki.repository_id, project)

    live_pages = []
    continuation_token = None
    while True:
        pages, continuation_token = _get_pages_batch_page(wiki_client, project, wiki_id, 100, continuation_token)
        live_pages.extend(pages)
        if not continuation_token:
            break
    live_page_ids = {page.id for page in live_pages}

    cached_pages = get_cached_wiki_pages(wiki_id)
    removed = len(set(cached_pages) - live_page_ids)

    result_pages = []
    added = 0
    changed = 0
    for page in live_pages:
        cached = cached_pages.get(page.id)

        if cached is None:
            metadata = _fetch_page_content(wiki_client, project, wiki_id, page.id, modified_dates)
            result_pages.append({"page_id": page.id, "path": page.path, **metadata})
            added += 1
            continue

        live_modified_at = modified_dates.get(cached["git_item_path"]) if cached["git_item_path"] else None
        needs_refetch = (
            cached["git_item_path"] is None
            or live_modified_at is None
            or cached["content_modified_at"] is None
            or live_modified_at > cached["content_modified_at"]
        )
        if needs_refetch:
            metadata = _fetch_page_content(wiki_client, project, wiki_id, page.id, modified_dates)
            result_pages.append({"page_id": page.id, "path": page.path, **metadata})
            changed += 1
        else:
            result_pages.append(
                {
                    "page_id": page.id,
                    "path": page.path,
                    "content": cached["content"],
                    "git_item_path": cached["git_item_path"],
                    "content_modified_at": cached["content_modified_at"],
                }
            )

    replace_wiki_pages(wiki_id, result_pages)
    record_wiki_cache_check(wiki_id)

    return {
        "wiki_id": wiki_id,
        "checked": True,
        "pages_total": len(result_pages),
        "added": added,
        "changed": changed,
        "removed": removed,
    }


def ensure_wiki_cache_fresh(wiki_id: Optional[str] = None, stale_after_seconds: Optional[int] = None) -> None:
    """Best-effort staleness check to call before serving a wiki-cache read. If `wiki_id`
    is omitted, checks every wiki currently in the cache. Never raises — a failed refresh
    just means the read below falls back to serving the last-known-good cached data."""
    wiki_ids = [wiki_id] if wiki_id else get_all_cached_wiki_ids()
    for wid in wiki_ids:
        try:
            check_and_refresh_wiki_cache(wid, stale_after_seconds=stale_after_seconds)
        except Exception:
            logger.exception("wiki cache staleness check failed for wiki_id=%s", wid)


def sync_all_wikis_on_startup() -> list:
    """Runs a full resync (bootstrap) for every wiki in the configured project. Intended
    to be scheduled as a background task at app startup — swallows and logs per-wiki
    errors rather than raising, since a slow/unreachable Azure DevOps instance shouldn't
    prevent the server from starting."""
    connection = _get_connection()
    project = _get_project()
    wiki_client = connection.clients.get_wiki_client()

    wikis = wiki_client.get_all_wikis(project=project) or []
    results = []
    for wiki in wikis:
        try:
            results.append(sync_wiki_cache(wiki.id, fetch_content=True))
        except Exception:
            logger.exception("startup wiki cache sync failed for wiki_id=%s", wiki.id)
            results.append({"wiki_id": wiki.id, "error": True})
    return results
