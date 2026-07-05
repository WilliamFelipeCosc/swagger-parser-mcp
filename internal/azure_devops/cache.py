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
        CREATE TABLE IF NOT EXISTS wiki_structure (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wiki_id TEXT NOT NULL,
            page_id INTEGER NOT NULL,
            path TEXT NOT NULL,
            name TEXT NOT NULL,
            parent_id INTEGER REFERENCES wiki_structure(id),
            depth INTEGER NOT NULL,
            structure_synced_at TEXT NOT NULL,
            UNIQUE(wiki_id, page_id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_wiki_structure_parent ON wiki_structure(parent_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_wiki_structure_wiki_path ON wiki_structure(wiki_id, path)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS wiki_page_content (
            structure_id INTEGER PRIMARY KEY REFERENCES wiki_structure(id),
            content TEXT,
            content_synced_at TEXT
        )
        """
    )
    # Standalone FTS5 table (no `content=` external-content link): path and content live
    # in two different tables (wiki_structure/wiki_page_content), and external-content FTS5
    # requires a single source table, so this keeps its own copy, inserted with an explicit
    # rowid matching wiki_structure.id.
    conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS wiki_pages_fts USING fts5(path, content)")
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


def _path_name(path: str) -> str:
    return path.rstrip("/").rsplit("/", 1)[-1]


def _parent_path(path: str) -> Optional[str]:
    trimmed = path.rstrip("/")
    if trimmed.count("/") <= 1:
        return None
    return trimmed.rsplit("/", 1)[0]


def sync_wiki_cache(wiki_id: str, fetch_content: bool = True) -> dict:
    """Rebuilds the local cache for a single wiki: paginates through every page via
    GetPagesBatch, optionally fetches each page's content individually (Azure DevOps has
    no bulk-content endpoint), then replaces that wiki's structure/content/FTS rows.

    Pages are inserted shallowest-first so each page's parent_id (an in-memory
    path -> structure_id map) is always already known by the time its children are
    inserted — no separate linking pass needed."""
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
    all_pages.sort(key=lambda page: _path_depth(page.path))

    synced_at = datetime.now(timezone.utc).isoformat()
    content_fetched = 0

    db = _get_db_connection()
    try:
        old_ids = [row[0] for row in db.execute("SELECT id FROM wiki_structure WHERE wiki_id = ?", (wiki_id,)).fetchall()]
        if old_ids:
            placeholders = ",".join("?" for _ in old_ids)
            db.execute(f"DELETE FROM wiki_pages_fts WHERE rowid IN ({placeholders})", old_ids)
            db.execute(f"DELETE FROM wiki_page_content WHERE structure_id IN ({placeholders})", old_ids)
        db.execute("DELETE FROM wiki_structure WHERE wiki_id = ?", (wiki_id,))

        path_to_id = {}
        for page in all_pages:
            parent_id = path_to_id.get(_parent_path(page.path))
            cursor = db.execute(
                """
                INSERT INTO wiki_structure (wiki_id, page_id, path, name, parent_id, depth, structure_synced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (wiki_id, page.id, page.path, _path_name(page.path), parent_id, _path_depth(page.path), synced_at),
            )
            structure_id = cursor.lastrowid
            path_to_id[page.path] = structure_id

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

            db.execute(
                "INSERT INTO wiki_page_content (structure_id, content, content_synced_at) VALUES (?, ?, ?)",
                (structure_id, content, content_synced_at),
            )
            db.execute(
                "INSERT INTO wiki_pages_fts (rowid, path, content) VALUES (?, ?, ?)",
                (structure_id, page.path, content or ""),
            )

        db.commit()
    finally:
        db.close()

    return {
        "wiki_id": wiki_id,
        "pages_synced": len(all_pages),
        "content_fetched": content_fetched,
        "synced_at": synced_at,
    }


def search_wiki_cache(query: str, wiki_id: Optional[str] = None, limit: int = 20) -> list:
    """Full-text search over cached paths/content. `query` is an FTS5 MATCH expression
    (supports phrases in quotes, AND/OR/NOT, prefix* etc.)."""
    db = _get_db_connection()
    try:
        sql = """
            SELECT ws.wiki_id, ws.page_id, ws.path,
                   snippet(wiki_pages_fts, 1, '[', ']', '...', 10) AS snippet,
                   bm25(wiki_pages_fts) AS rank
            FROM wiki_pages_fts
            JOIN wiki_structure ws ON ws.id = wiki_pages_fts.rowid
            WHERE wiki_pages_fts MATCH ?
        """
        params = [query]
        if wiki_id:
            sql += " AND ws.wiki_id = ?"
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


def _rows_to_tree(rows) -> list:
    nodes = {
        row["id"]: {"wiki_id": row["wiki_id"], "page_id": row["page_id"], "path": row["path"], "sub_pages": []}
        for row in rows
    }
    roots = []
    for row in rows:
        node = nodes[row["id"]]
        parent = nodes.get(row["parent_id"]) if row["parent_id"] is not None else None
        (parent["sub_pages"] if parent else roots).append(node)
    return roots


def get_wiki_tree(wiki_id: Optional[str] = None) -> list:
    """Rebuilds the full page hierarchy purely from cached rows (no API calls) using the
    parent_id links set at sync time."""
    db = _get_db_connection()
    try:
        sql = "SELECT id, wiki_id, page_id, path, parent_id FROM wiki_structure"
        params = []
        if wiki_id:
            sql += " WHERE wiki_id = ?"
            params.append(wiki_id)
        sql += " ORDER BY path"
        rows = db.execute(sql, params).fetchall()
    finally:
        db.close()

    return _rows_to_tree(rows)


def get_wiki_subtree(wiki_id: str, root_page_id: Optional[int] = None, root_path: Optional[str] = None) -> dict:
    """Returns the folder/path subtree rooted at a specific page (e.g. root_page_id=589 for
    "/Wiki Nivello/Produto & Agilidade"), walking parent_id links via a recursive CTE.
    Exactly one of root_page_id/root_path must be given to identify the root."""
    if root_page_id is None and root_path is None:
        raise ValueError("root_page_id or root_path is required")

    db = _get_db_connection()
    try:
        if root_page_id is not None:
            root = db.execute(
                "SELECT id FROM wiki_structure WHERE wiki_id = ? AND page_id = ?", (wiki_id, root_page_id)
            ).fetchone()
        else:
            root = db.execute(
                "SELECT id FROM wiki_structure WHERE wiki_id = ? AND path = ?", (wiki_id, root_path)
            ).fetchone()

        if root is None:
            return None

        rows = db.execute(
            """
            WITH RECURSIVE subtree(id) AS (
                SELECT id FROM wiki_structure WHERE id = :root_id
                UNION ALL
                SELECT ws.id FROM wiki_structure ws JOIN subtree s ON ws.parent_id = s.id
            )
            SELECT ws.id, ws.wiki_id, ws.page_id, ws.path, ws.parent_id
            FROM wiki_structure ws
            JOIN subtree ON subtree.id = ws.id
            ORDER BY ws.path
            """,
            {"root_id": root["id"]},
        ).fetchall()
    finally:
        db.close()

    tree = _rows_to_tree(rows)
    return tree[0] if tree else None


def get_wiki_cache_status(wiki_id: Optional[str] = None) -> list:
    db = _get_db_connection()
    try:
        sql = """
            SELECT ws.wiki_id,
                   COUNT(*) AS page_count,
                   MAX(ws.structure_synced_at) AS last_synced_at,
                   SUM(CASE WHEN wpc.content IS NOT NULL THEN 1 ELSE 0 END) AS pages_with_content
            FROM wiki_structure ws
            LEFT JOIN wiki_page_content wpc ON wpc.structure_id = ws.id
        """
        params = []
        if wiki_id:
            sql += " WHERE ws.wiki_id = ?"
            params.append(wiki_id)
        sql += " GROUP BY ws.wiki_id"
        rows = db.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        db.close()
