import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .shared import _get_connection, _get_project
from .wiki import _get_pages_batch_page

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = str(_REPO_ROOT / "data" / "wiki_cache.db")


def _get_db_path() -> str:
    return os.getenv("WIKI_CACHE_DB_PATH", DEFAULT_DB_PATH)


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS wiki_pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wiki_id TEXT NOT NULL,
            page_id INTEGER NOT NULL,
            path TEXT NOT NULL,
            parent_path TEXT,
            depth INTEGER NOT NULL,
            content TEXT,
            content_synced_at TEXT,
            structure_synced_at TEXT NOT NULL,
            UNIQUE(wiki_id, page_id)
        )
        """
    )
    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS wiki_pages_fts USING fts5(
            path, content, content='wiki_pages', content_rowid='id'
        )
        """
    )
    conn.commit()


def _get_db_connection() -> sqlite3.Connection:
    db_path = _get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    return conn


def _path_depth(path: str) -> int:
    return len([segment for segment in path.strip("/").split("/") if segment])


def _parent_path(path: str) -> Optional[str]:
    trimmed = path.rstrip("/")
    if trimmed.count("/") <= 1:
        return None
    return trimmed.rsplit("/", 1)[0]


def sync_wiki_cache(wiki_id: str, fetch_content: bool = True) -> dict:
    """Rebuilds the local cache for a single wiki: paginates through every page via
    GetPagesBatch, optionally fetches each page's content individually (Azure DevOps has
    no bulk-content endpoint), then replaces that wiki's rows and rebuilds the FTS5 index."""
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

    synced_at = datetime.now(timezone.utc).isoformat()
    content_fetched = 0
    rows = []
    for page in all_pages:
        content = None
        content_synced_at = None
        if fetch_content:
            try:
                page_response = wiki_client.get_page_by_id(
                    project=project, wiki_identifier=wiki_id, id=page.id, include_content=True
                )
                content = getattr(page_response.page, "content", None)
                content_synced_at = synced_at
                content_fetched += 1
            except Exception:
                pass
        rows.append((
            wiki_id, page.id, page.path, _parent_path(page.path), _path_depth(page.path),
            content, content_synced_at, synced_at,
        ))

    db = _get_db_connection()
    try:
        db.execute("DELETE FROM wiki_pages WHERE wiki_id = ?", (wiki_id,))
        db.executemany(
            """
            INSERT INTO wiki_pages (wiki_id, page_id, path, parent_path, depth, content, content_synced_at, structure_synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        db.execute("INSERT INTO wiki_pages_fts(wiki_pages_fts) VALUES ('rebuild')")
        db.commit()
    finally:
        db.close()

    return {
        "wiki_id": wiki_id,
        "pages_synced": len(rows),
        "content_fetched": content_fetched,
        "synced_at": synced_at,
    }


def search_wiki_cache(query: str, wiki_id: Optional[str] = None, limit: int = 20) -> list:
    """Full-text search over cached paths/content. `query` is an FTS5 MATCH expression
    (supports phrases in quotes, AND/OR/NOT, prefix* etc.)."""
    db = _get_db_connection()
    try:
        sql = """
            SELECT wp.wiki_id, wp.page_id, wp.path,
                   snippet(wiki_pages_fts, 1, '[', ']', '...', 10) AS snippet,
                   bm25(wiki_pages_fts) AS rank
            FROM wiki_pages_fts
            JOIN wiki_pages wp ON wp.id = wiki_pages_fts.rowid
            WHERE wiki_pages_fts MATCH ?
        """
        params = [query]
        if wiki_id:
            sql += " AND wp.wiki_id = ?"
            params.append(wiki_id)
        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)

        rows = db.execute(sql, params).fetchall()
        return [
            {
                "wiki_id": row["wiki_id"],
                "page_id": row["page_id"],
                "path": row["path"],
                "snippet": row["snippet"],
            }
            for row in rows
        ]
    finally:
        db.close()


def get_wiki_tree(wiki_id: Optional[str] = None) -> list:
    """Rebuilds the page hierarchy purely from cached rows (no API calls) using the
    parent_path derived at sync time."""
    db = _get_db_connection()
    try:
        sql = "SELECT wiki_id, page_id, path, parent_path FROM wiki_pages"
        params = []
        if wiki_id:
            sql += " WHERE wiki_id = ?"
            params.append(wiki_id)
        sql += " ORDER BY path"
        rows = db.execute(sql, params).fetchall()
    finally:
        db.close()

    nodes = {}
    for row in rows:
        nodes[(row["wiki_id"], row["path"])] = {
            "wiki_id": row["wiki_id"],
            "page_id": row["page_id"],
            "path": row["path"],
            "sub_pages": [],
        }

    roots = []
    for row in rows:
        node = nodes[(row["wiki_id"], row["path"])]
        parent_key = (row["wiki_id"], row["parent_path"]) if row["parent_path"] else None
        parent = nodes.get(parent_key) if parent_key else None
        (parent["sub_pages"] if parent else roots).append(node)

    return roots


def get_wiki_cache_status(wiki_id: Optional[str] = None) -> list:
    db = _get_db_connection()
    try:
        sql = """
            SELECT wiki_id, COUNT(*) AS page_count, MAX(structure_synced_at) AS last_synced_at,
                   SUM(CASE WHEN content IS NOT NULL THEN 1 ELSE 0 END) AS pages_with_content
            FROM wiki_pages
        """
        params = []
        if wiki_id:
            sql += " WHERE wiki_id = ?"
            params.append(wiki_id)
        sql += " GROUP BY wiki_id"
        rows = db.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        db.close()
