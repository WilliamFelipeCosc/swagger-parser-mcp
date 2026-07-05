from datetime import datetime, timezone
from typing import Optional

from .connection import _get_db_connection


def _path_depth(path: str) -> int:
    return len([segment for segment in path.strip("/").split("/") if segment])


def _path_name(path: str) -> str:
    return path.rstrip("/").rsplit("/", 1)[-1]


def _parent_path(path: str) -> Optional[str]:
    trimmed = path.rstrip("/")
    if trimmed.count("/") <= 1:
        return None
    return trimmed.rsplit("/", 1)[0]


def replace_wiki_pages(wiki_id: str, pages: list) -> dict:
    """Replaces all cached rows for `wiki_id`. `pages` is a list of
    {"page_id": int, "path": str, "content": Optional[str]}; this function sorts them
    shallowest-first internally so each page's parent_id (an in-memory path -> structure_id
    map) is always already known by the time its children are inserted."""
    sorted_pages = sorted(pages, key=lambda page: _path_depth(page["path"]))
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
        for page in sorted_pages:
            parent_id = path_to_id.get(_parent_path(page["path"]))
            cursor = db.execute(
                """
                INSERT INTO wiki_structure (wiki_id, page_id, path, name, parent_id, depth, structure_synced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (wiki_id, page["page_id"], page["path"], _path_name(page["path"]), parent_id, _path_depth(page["path"]), synced_at),
            )
            structure_id = cursor.lastrowid
            path_to_id[page["path"]] = structure_id

            content = page.get("content")
            content_synced_at = synced_at if content is not None else None
            if content is not None:
                content_fetched += 1

            db.execute(
                "INSERT INTO wiki_page_content (structure_id, content, content_synced_at) VALUES (?, ?, ?)",
                (structure_id, content, content_synced_at),
            )
            db.execute(
                "INSERT INTO wiki_pages_fts (rowid, path, content) VALUES (?, ?, ?)",
                (structure_id, page["path"], content or ""),
            )

        db.commit()
    finally:
        db.close()

    return {
        "wiki_id": wiki_id,
        "pages_synced": len(sorted_pages),
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


def get_wiki_subtree(wiki_id: str, root_page_id: Optional[int] = None, root_path: Optional[str] = None) -> Optional[dict]:
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
