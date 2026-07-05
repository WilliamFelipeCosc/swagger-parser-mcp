import os
import sqlite3
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = str(_REPO_ROOT / "data" / "wiki_cache.db")


def _get_db_path() -> str:
    return os.getenv("WIKI_CACHE_DB_PATH", DEFAULT_DB_PATH)


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, coltype: str) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")


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
            git_item_path TEXT,
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
            content_synced_at TEXT,
            content_modified_at TEXT
        )
        """
    )
    # Standalone FTS5 table (no `content=` external-content link): path and content live
    # in two different tables (wiki_structure/wiki_page_content), and external-content FTS5
    # requires a single source table, so this keeps its own copy, inserted with an explicit
    # rowid matching wiki_structure.id.
    conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS wiki_pages_fts USING fts5(path, content)")
    # Tracks the last time we asked Azure "what changed" for a wiki (see
    # check_and_refresh_wiki_cache), separate from structure_synced_at/content_synced_at
    # which track individual page writes.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS wiki_cache_check_state (
            wiki_id TEXT PRIMARY KEY,
            last_checked_at TEXT NOT NULL
        )
        """
    )
    # Idempotent migrations for DBs created before these columns existed; harmless no-ops
    # for fresh DBs, since CREATE TABLE above already includes them.
    _add_column_if_missing(conn, "wiki_structure", "git_item_path", "TEXT")
    _add_column_if_missing(conn, "wiki_page_content", "content_modified_at", "TEXT")
    conn.commit()


def _get_db_connection() -> sqlite3.Connection:
    db_path = _get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    return conn
