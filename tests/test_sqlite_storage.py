"""Tests for storage.sqlite_storage.SqliteStorage."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from storage.sqlite_storage import SqliteStorage
from web_scraping.models import JobListing, LinkedInJobListing
from tests.conftest import make_listing, make_linkedin_listing, NOW_ISO


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_storage(tmp_path: Path, cache_ttl_days: int = 2) -> SqliteStorage:
    return SqliteStorage(tmp_path / "test.db", cache_ttl_days=cache_ttl_days)


# ===========================================================================
# Schema / initialisation
# ===========================================================================

class TestInit:
    def test_creates_db_file(self, tmp_path):
        db = tmp_path / "sub" / "jobs.db"
        SqliteStorage(db)
        assert db.exists()

    def test_creates_parent_dirs(self, tmp_path):
        db = tmp_path / "a" / "b" / "c" / "jobs.db"
        SqliteStorage(db)
        assert db.exists()

    def test_idempotent_second_init(self, tmp_path):
        """Re-opening the same DB must not raise."""
        storage = make_storage(tmp_path)
        storage2 = SqliteStorage(tmp_path / "test.db")
        assert storage2 is not None


# ===========================================================================
# load_ids
# ===========================================================================

class TestLoadIds:
    def test_empty_database(self, tmp_path):
        assert make_storage(tmp_path).load_ids() == set()

    def test_returns_upwork_ids(self, tmp_path):
        s = make_storage(tmp_path)
        s.save([make_listing(job_id="u1"), make_listing(job_id="u2")])
        assert {"u1", "u2"}.issubset(s.load_ids())

    def test_returns_linkedin_ids(self, tmp_path):
        s = make_storage(tmp_path)
        s.save([make_linkedin_listing(job_id="l1"), make_linkedin_listing(job_id="l2")])
        assert {"l1", "l2"}.issubset(s.load_ids())

    def test_returns_ids_from_both_sources(self, tmp_path):
        s = make_storage(tmp_path)
        s.save([make_listing(job_id="u1")])
        s.save([make_linkedin_listing(job_id="l1")])
        assert s.load_ids() == {"u1", "l1"}

    def test_load_ids_for_source_upwork(self, tmp_path):
        s = make_storage(tmp_path)
        s.save([make_listing(job_id="u1")])
        s.save([make_linkedin_listing(job_id="l1")])
        assert s.load_ids_for_source("upwork") == {"u1"}

    def test_load_ids_for_source_linkedin(self, tmp_path):
        s = make_storage(tmp_path)
        s.save([make_listing(job_id="u1")])
        s.save([make_linkedin_listing(job_id="l1")])
        assert s.load_ids_for_source("linkedin") == {"l1"}


# ===========================================================================
# save — Upwork
# ===========================================================================

class TestSaveUpwork:
    def test_returns_count_of_new_records(self, tmp_path):
        s = make_storage(tmp_path)
        assert s.save([make_listing(job_id="a"), make_listing(job_id="b")]) == 2

    def test_deduplicates_within_batch(self, tmp_path):
        s = make_storage(tmp_path)
        # Two listings with the same job_id — only one should be stored
        n = s.save([make_listing(job_id="dup"), make_listing(job_id="dup")])
        assert n == 1

    def test_deduplicates_across_saves(self, tmp_path):
        s = make_storage(tmp_path)
        s.save([make_listing(job_id="x")])
        n = s.save([make_listing(job_id="x")])
        assert n == 0

    def test_persists_all_fields(self, tmp_path):
        s = make_storage(tmp_path)
        listing = make_listing(
            job_id="field-check",
            title="My Title",
            job_type="HOURLY",
            budget="$30/hr",
            skills="Python, FastAPI",
            client_country="Germany",
            scraped_at=NOW_ISO,
        )
        s.save([listing])
        rows = s.load_all("upwork")
        assert len(rows) == 1
        row = rows[0]
        assert row["job_id"] == "field-check"
        assert row["title"] == "My Title"
        assert row["job_type"] == "HOURLY"
        assert row["budget"] == "$30/hr"
        assert row["skills"] == "Python, FastAPI"
        assert row["client_country"] == "Germany"

    def test_returns_zero_for_empty_list(self, tmp_path):
        assert make_storage(tmp_path).save([]) == 0


# ===========================================================================
# save — LinkedIn
# ===========================================================================

class TestSaveLinkedIn:
    def test_returns_count_of_new_records(self, tmp_path):
        s = make_storage(tmp_path)
        assert s.save([make_linkedin_listing(job_id="l1"), make_linkedin_listing(job_id="l2")]) == 2

    def test_deduplicates_within_batch(self, tmp_path):
        s = make_storage(tmp_path)
        n = s.save([make_linkedin_listing(job_id="dup"), make_linkedin_listing(job_id="dup")])
        assert n == 1

    def test_deduplicates_across_saves(self, tmp_path):
        s = make_storage(tmp_path)
        s.save([make_linkedin_listing(job_id="l1")])
        n = s.save([make_linkedin_listing(job_id="l1")])
        assert n == 0

    def test_persists_all_fields(self, tmp_path):
        s = make_storage(tmp_path)
        listing = make_linkedin_listing(
            job_id="li-fields",
            title="Data Engineer",
            company="ACME",
            location="Berlin, Germany",
            workplace_type="Hybrid",
            employment_type="Contract",
            applicant_count="42 applicants",
            scraped_at=NOW_ISO,
        )
        s.save([listing])
        rows = s.load_all("linkedin")
        assert len(rows) == 1
        row = rows[0]
        assert row["job_id"] == "li-fields"
        assert row["title"] == "Data Engineer"
        assert row["company"] == "ACME"
        assert row["location"] == "Berlin, Germany"
        assert row["workplace_type"] == "Hybrid"
        assert row["employment_type"] == "Contract"
        assert row["applicant_count"] == "42 applicants"


# ===========================================================================
# load_all
# ===========================================================================

class TestLoadAll:
    def test_returns_empty_list_when_no_records(self, tmp_path):
        assert make_storage(tmp_path).load_all("upwork") == []

    def test_returns_all_upwork_records(self, tmp_path):
        s = make_storage(tmp_path)
        s.save([make_listing(job_id="a"), make_listing(job_id="b")])
        rows = s.load_all("upwork")
        assert len(rows) == 2
        assert {r["job_id"] for r in rows} == {"a", "b"}

    def test_returns_only_requested_source(self, tmp_path):
        s = make_storage(tmp_path)
        s.save([make_listing(job_id="u1")])
        s.save([make_linkedin_listing(job_id="l1")])
        upwork_rows = s.load_all("upwork")
        linkedin_rows = s.load_all("linkedin")
        assert all(r["job_id"] == "u1" for r in upwork_rows)
        assert all(r["job_id"] == "l1" for r in linkedin_rows)

    def test_rows_are_dicts(self, tmp_path):
        s = make_storage(tmp_path)
        s.save([make_listing(job_id="d1")])
        rows = s.load_all("upwork")
        assert isinstance(rows[0], dict)


# ===========================================================================
# delete_by_ids
# ===========================================================================

class TestDeleteByIds:
    def test_deletes_specified_ids(self, tmp_path):
        s = make_storage(tmp_path)
        s.save([make_listing(job_id="keep"), make_listing(job_id="del")])
        deleted = s.delete_by_ids("upwork", ["del"])
        assert deleted == 1
        ids = s.load_ids_for_source("upwork")
        assert "keep" in ids
        assert "del" not in ids

    def test_returns_zero_for_nonexistent_ids(self, tmp_path):
        s = make_storage(tmp_path)
        assert s.delete_by_ids("upwork", ["does-not-exist"]) == 0

    def test_returns_zero_for_empty_list(self, tmp_path):
        s = make_storage(tmp_path)
        assert s.delete_by_ids("upwork", []) == 0

    def test_delete_multiple(self, tmp_path):
        s = make_storage(tmp_path)
        s.save([make_listing(job_id=f"j{i}") for i in range(5)])
        deleted = s.delete_by_ids("upwork", ["j0", "j2", "j4"])
        assert deleted == 3
        assert s.load_ids_for_source("upwork") == {"j1", "j3"}

    def test_delete_does_not_affect_other_source(self, tmp_path):
        s = make_storage(tmp_path)
        s.save([make_listing(job_id="u1")])
        s.save([make_linkedin_listing(job_id="u1")])
        s.delete_by_ids("upwork", ["u1"])
        assert "u1" in s.load_ids_for_source("linkedin")


# ===========================================================================
# clear_all
# ===========================================================================

class TestClearAll:
    def test_clear_single_source(self, tmp_path):
        s = make_storage(tmp_path)
        s.save([make_listing(job_id="u1")])
        s.save([make_linkedin_listing(job_id="l1")])
        s.clear_all("upwork")
        assert s.load_ids_for_source("upwork") == set()
        assert "l1" in s.load_ids_for_source("linkedin")

    def test_clear_all_sources(self, tmp_path):
        s = make_storage(tmp_path)
        s.save([make_listing(job_id="u1")])
        s.save([make_linkedin_listing(job_id="l1")])
        s.clear_all()
        assert s.load_ids() == set()

    def test_clear_then_re_insert(self, tmp_path):
        s = make_storage(tmp_path)
        s.save([make_listing(job_id="u1")])
        s.clear_all("upwork")
        n = s.save([make_listing(job_id="u1")])
        assert n == 1   # not a duplicate any more after clear


# ===========================================================================
# Cache
# ===========================================================================

class TestCache:
    def test_cache_put_and_get(self, tmp_path):
        s = make_storage(tmp_path)
        payload = {"job_id": "c1", "title": "Cached Job"}
        s.cache_put("linkedin", "python", "c1", payload)
        results = s.cache_get("linkedin", "python")
        assert len(results) == 1
        assert results[0]["job_id"] == "c1"

    def test_cache_has_returns_true_when_fresh(self, tmp_path):
        s = make_storage(tmp_path)
        s.cache_put("upwork", "django", "j1", {})
        assert s.cache_has("upwork", "django") is True

    def test_cache_has_returns_false_when_empty(self, tmp_path):
        s = make_storage(tmp_path)
        assert s.cache_has("upwork", "django") is False

    def test_cache_get_returns_empty_for_unknown_query(self, tmp_path):
        s = make_storage(tmp_path)
        assert s.cache_get("linkedin", "unknown-query-xyz") == []

    def test_cache_get_isolates_by_source(self, tmp_path):
        s = make_storage(tmp_path)
        s.cache_put("upwork",   "python", "u1", {"x": 1})
        s.cache_put("linkedin", "python", "l1", {"y": 2})
        upwork_results   = s.cache_get("upwork",   "python")
        linkedin_results = s.cache_get("linkedin", "python")
        assert len(upwork_results)   == 1
        assert len(linkedin_results) == 1

    def test_cache_get_isolates_by_query(self, tmp_path):
        s = make_storage(tmp_path)
        s.cache_put("upwork", "python",  "j1", {"q": "python"})
        s.cache_put("upwork", "fastapi", "j2", {"q": "fastapi"})
        assert len(s.cache_get("upwork", "python"))  == 1
        assert len(s.cache_get("upwork", "fastapi")) == 1

    def test_purge_expired_cache(self, tmp_path):
        # Use ttl=0 so everything is immediately expired
        s = SqliteStorage(tmp_path / "cache_test.db", cache_ttl_days=0)
        s.cache_put("upwork", "python", "j1", {})
        # Manually force old timestamp via direct SQL
        import sqlite3
        old_ts = (
            datetime.now(tz=timezone.utc) - timedelta(days=3)
        ).isoformat(timespec="seconds")
        with sqlite3.connect(tmp_path / "cache_test.db") as con:
            con.execute("UPDATE scrape_cache SET cached_at = ?", (old_ts,))
        deleted = s.purge_expired_cache()
        assert deleted >= 1
        assert s.cache_get("upwork", "python") == []

    def test_cache_put_replace_existing(self, tmp_path):
        s = make_storage(tmp_path)
        s.cache_put("upwork", "python", "j1", {"v": 1})
        s.cache_put("upwork", "python", "j1", {"v": 2})
        results = s.cache_get("upwork", "python")
        assert len(results) == 1
        assert results[0]["v"] == 2

    def test_expired_entries_not_returned_by_get(self, tmp_path):
        import sqlite3
        s = make_storage(tmp_path)
        s.cache_put("linkedin", "ml", "j1", {"title": "ML Engineer"})
        old_ts = (
            datetime.now(tz=timezone.utc) - timedelta(days=5)
        ).isoformat(timespec="seconds")
        with sqlite3.connect(tmp_path / "test.db") as con:
            con.execute("UPDATE scrape_cache SET cached_at = ?", (old_ts,))
        assert s.cache_get("linkedin", "ml") == []
        assert s.cache_has("linkedin", "ml") is False
