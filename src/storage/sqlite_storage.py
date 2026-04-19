"""SQLite-backed storage for job listings.

Schema
------
Two permanent tables mirror the two dataclass schemas:

    upwork_jobs   — matches JobListing field names exactly
    linkedin_jobs — matches LinkedInJobListing field names exactly

One cache table stores raw scrape results that auto-expire after
``cache_ttl_days`` (default 2):

    scrape_cache(query TEXT, source TEXT, job_id TEXT,
                 payload TEXT,          -- JSON-serialised raw dict
                 cached_at TEXT,        -- ISO UTC timestamp
                 PRIMARY KEY (source, query, job_id))

All job tables use ``job_id`` as the primary key for deduplication.
Records are never updated — only inserted if absent (INSERT OR IGNORE).
Deletes must be explicit (delete_by_ids / clear_all).

The database file is created automatically if it does not exist.

Later migration path
--------------------
Replace sqlite3 with psycopg2 / asyncpg and adjust the placeholder style
(``?`` → ``%s``).  The rest of the public API stays identical.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, fields
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from storage.base_storage import BaseStorage
from web_scraping.models import JobListing, LinkedInJobListing

# Maps the source string to the dataclass type and table name
_SOURCE_META: dict[str, tuple[type, str]] = {
    "upwork":   (JobListing,          "upwork_jobs"),
    "linkedin": (LinkedInJobListing,  "linkedin_jobs"),
}

_CACHE_TABLE = "scrape_cache"
_DEFAULT_CACHE_TTL_DAYS = 2


def _col_defs(dataclass_type: type) -> str:
    """Return ``CREATE TABLE`` column definitions for a dataclass."""
    cols = []
    for f in fields(dataclass_type):
        if f.name == "job_id":
            cols.append("job_id TEXT PRIMARY KEY")
        else:
            cols.append(f"{f.name} TEXT")
    return ", ".join(cols)


class SqliteStorage(BaseStorage):
    """SQLite-backed storage for Upwork and LinkedIn job listings.

    Parameters
    ----------
    db_path:
        Path to the ``.db`` file.  Created (with parent dirs) on first use.
    cache_ttl_days:
        How many days cached raw scrape results are kept before being purged.
    """

    def __init__(
        self,
        db_path: str | Path,
        cache_ttl_days: int = _DEFAULT_CACHE_TTL_DAYS,
    ) -> None:
        self._path = Path(db_path)
        self._cache_ttl = cache_ttl_days
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        self.purge_expired_cache()

    # ------------------------------------------------------------------
    # BaseStorage interface
    # ------------------------------------------------------------------

    def load_ids(self) -> set[str]:
        """Return all job_ids across both tables."""
        ids: set[str] = set()
        with self._connect() as con:
            for _, table in _SOURCE_META.values():
                try:
                    ids.update(
                        row[0]
                        for row in con.execute(f"SELECT job_id FROM {table}")
                    )
                except sqlite3.OperationalError:
                    pass
        return ids

    def load_ids_for_source(self, source: str) -> set[str]:
        """Return job_ids for a specific source table."""
        _, table = _SOURCE_META[source]
        with self._connect() as con:
            return {
                row[0]
                for row in con.execute(f"SELECT job_id FROM {table}")
            }

    def save(self, listings: list[Any]) -> int:
        """Insert new listings; skip duplicates. Returns new-record count."""
        if not listings:
            return 0

        source = listings[0].source
        _, table = _SOURCE_META[source]
        col_names = [f.name for f in fields(type(listings[0]))]
        placeholders = ", ".join("?" * len(col_names))
        sql = (
            f"INSERT OR IGNORE INTO {table} "
            f"({', '.join(col_names)}) VALUES ({placeholders})"
        )

        rows = [tuple(asdict(l).values()) for l in listings]
        with self._connect() as con:
            before = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            con.executemany(sql, rows)
            after = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

        return after - before

    # ------------------------------------------------------------------
    # Query / load
    # ------------------------------------------------------------------

    def load_all(self, source: str) -> list[dict]:
        """Return all rows for *source* as a list of dicts (newest-scraped first)."""
        _, table = _SOURCE_META[source]
        with self._connect() as con:
            con.row_factory = sqlite3.Row
            rows = con.execute(
                f"SELECT * FROM {table} ORDER BY scraped_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_by_ids(self, source: str, job_ids: list[str]) -> int:
        """Delete specific jobs by id. Returns number of rows deleted."""
        if not job_ids:
            return 0
        _, table = _SOURCE_META[source]
        placeholders = ", ".join("?" * len(job_ids))
        with self._connect() as con:
            cur = con.execute(
                f"DELETE FROM {table} WHERE job_id IN ({placeholders})", job_ids
            )
        return cur.rowcount

    def clear_all(self, source: str | None = None) -> None:
        """Delete all rows.  Pass source='upwork'/'linkedin' to clear one table,
        or None to clear both."""
        sources = [source] if source else list(_SOURCE_META.keys())
        with self._connect() as con:
            for src in sources:
                _, table = _SOURCE_META[src]
                con.execute(f"DELETE FROM {table}")

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def cache_put(self, source: str, query: str, job_id: str, payload: dict) -> None:
        """Store a raw scraped dict in the cache table."""
        now = datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
        with self._connect() as con:
            con.execute(
                f"INSERT OR REPLACE INTO {_CACHE_TABLE} "
                "(source, query, job_id, payload, cached_at) VALUES (?, ?, ?, ?, ?)",
                (source, query, job_id, json.dumps(payload), now),
            )

    def cache_get(self, source: str, query: str) -> list[dict]:
        """Retrieve unexpired cached raw dicts for a (source, query) pair."""
        cutoff = (
            datetime.now(tz=timezone.utc) - timedelta(days=self._cache_ttl)
        ).isoformat(timespec="seconds")
        with self._connect() as con:
            rows = con.execute(
                f"SELECT payload FROM {_CACHE_TABLE} "
                "WHERE source = ? AND query = ? AND cached_at >= ?",
                (source, query, cutoff),
            ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def cache_has(self, source: str, query: str) -> bool:
        """True if there are non-expired cache entries for this (source, query)."""
        return len(self.cache_get(source, query)) > 0

    def purge_expired_cache(self) -> int:
        """Delete all cache entries older than ``cache_ttl_days``. Returns deleted count."""
        cutoff = (
            datetime.now(tz=timezone.utc) - timedelta(days=self._cache_ttl)
        ).isoformat(timespec="seconds")
        with self._connect() as con:
            cur = con.execute(
                f"DELETE FROM {_CACHE_TABLE} WHERE cached_at < ?", (cutoff,)
            )
        return cur.rowcount

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self._path)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA foreign_keys=ON")
        return con

    def _init_schema(self) -> None:
        with self._connect() as con:
            for dataclass_type, table in _SOURCE_META.values():
                con.execute(
                    f"CREATE TABLE IF NOT EXISTS {table} "
                    f"({_col_defs(dataclass_type)})"
                )
            con.execute(
                f"CREATE TABLE IF NOT EXISTS {_CACHE_TABLE} ("
                "source TEXT NOT NULL, "
                "query TEXT NOT NULL, "
                "job_id TEXT NOT NULL, "
                "payload TEXT NOT NULL, "
                "cached_at TEXT NOT NULL, "
                "PRIMARY KEY (source, query, job_id)"
                ")"
            )
            con.execute(
                f"CREATE INDEX IF NOT EXISTS idx_cache_lookup "
                f"ON {_CACHE_TABLE}(source, query, cached_at)"
            )
