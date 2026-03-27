"""Tests for web_scraping.upwork_scraping.UpworkScraper.

All tests are fully offline: _fetch_page is monkeypatched to avoid any
network calls, and _get_session is patched to avoid opening a browser.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from web_scraping.upwork_scraping import UpworkScraper
from web_scraping.models import JobListing
from tests.conftest import make_raw_job, UPWORK_CONFIG, NOW_ISO

PAGE_SIZE = UPWORK_CONFIG["page_size"]  # 50


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def scraper() -> UpworkScraper:
    return UpworkScraper(UPWORK_CONFIG)


def _patch_fetch(instance: UpworkScraper, pages: list[list[dict]]) -> None:
    """
    Replace ``_fetch_page`` with a callable that returns ``pages[offset // PAGE_SIZE]``
    (or an empty list when the index is out of range).
    """
    def fake_fetch(cookies, user_agent, query, search_url, offset):
        idx = offset // PAGE_SIZE
        return pages[idx] if idx < len(pages) else []

    instance._fetch_page = fake_fetch


def _patch_session(instance: UpworkScraper, cookies: dict | None = None) -> None:
    """Patch ``_get_session`` to return canned cookies/ua without opening Chrome."""
    cookies = cookies or {"UniversalSearchNuxt_vt": "fake-token"}
    instance._get_session = AsyncMock(return_value=(cookies, "FakeAgent/1.0"))


# ---------------------------------------------------------------------------
# _to_listing  (static – no patching needed)
# ---------------------------------------------------------------------------

class TestToListing:
    def test_fixed_price_job(self):
        raw = make_raw_job("id-1", title="Django Dev", job_type="FIXED", amount=300.0)
        listing = UpworkScraper._to_listing(raw)

        assert isinstance(listing, JobListing)
        assert listing.job_id == "id-1"
        assert listing.source == "upwork"
        assert listing.title == "Django Dev"
        assert listing.job_type == "FIXED"
        assert listing.budget == "$300.0"
        assert listing.url == "https://www.upwork.com/jobs/id-1"
        assert listing.publish_time == NOW_ISO

    def test_hourly_job(self):
        raw = make_raw_job("id-2", title="FastAPI Dev", job_type="HOURLY",
                           hourly_min=25.0, hourly_max=50.0)
        listing = UpworkScraper._to_listing(raw)

        assert listing.job_type == "HOURLY"
        assert listing.budget == "$25.0-$50.0/hr"

    def test_missing_job_tile_handled(self):
        raw = {"id": "bare-id", "title": "Bare Job", "description": "desc", "jobTile": None}
        listing = UpworkScraper._to_listing(raw)
        assert listing.job_id == "bare-id"
        assert listing.job_type == "N/A"
        assert listing.budget == "N/A"

    def test_missing_fixed_price_amount(self):
        raw = make_raw_job("id-3", job_type="FIXED", amount=None)
        raw["jobTile"]["job"]["fixedPriceAmount"] = None
        listing = UpworkScraper._to_listing(raw)
        assert listing.budget == "N/A"

    def test_description_truncated_to_500_chars(self):
        long_desc = "x" * 600
        raw = {
            "id": "long",
            "title": "T",
            "description": long_desc,
            "jobTile": {"job": {
                "ciphertext": "long",
                "jobType": "FIXED",
                "hourlyBudgetMin": None,
                "hourlyBudgetMax": None,
                "fixedPriceAmount": {"amount": 100},
                "publishTime": NOW_ISO,
            }},
        }
        listing = UpworkScraper._to_listing(raw)
        assert len(listing.description) == 500

    def test_url_uses_ciphertext(self):
        raw = make_raw_job("cipher-xyz")
        listing = UpworkScraper._to_listing(raw)
        assert listing.url == "https://www.upwork.com/jobs/cipher-xyz"

    def test_empty_cipher_gives_na_url(self):
        raw = make_raw_job("id-empty")
        raw["jobTile"]["job"]["ciphertext"] = ""
        listing = UpworkScraper._to_listing(raw)
        assert listing.url == "N/A"


# ---------------------------------------------------------------------------
# _collect_raw – pagination & deduplication
# ---------------------------------------------------------------------------

class TestCollectRaw:
    def test_returns_requested_count(self):
        s = scraper()
        _patch_fetch(s, [[make_raw_job(str(i)) for i in range(PAGE_SIZE)]])
        result = s._collect_raw({}, "ua", "python", "http://x", count=5, days=None)
        assert len(result) == 5

    def test_stops_when_api_exhausted(self):
        s = scraper()
        # Only 3 jobs available
        _patch_fetch(s, [[make_raw_job("a"), make_raw_job("b"), make_raw_job("c")]])
        result = s._collect_raw({}, "ua", "q", "http://x", count=10, days=None)
        assert len(result) == 3

    def test_paginates_to_collect_count(self):
        s = scraper()
        page1 = [make_raw_job(str(i)) for i in range(PAGE_SIZE)]
        page2 = [make_raw_job(str(i)) for i in range(PAGE_SIZE, PAGE_SIZE + 10)]
        _patch_fetch(s, [page1, page2])
        result = s._collect_raw({}, "ua", "q", "http://x", count=PAGE_SIZE + 5, days=None)
        assert len(result) == PAGE_SIZE + 5

    def test_within_page_deduplication(self):
        s = scraper()
        _patch_fetch(s, [[make_raw_job("A"), make_raw_job("B"), make_raw_job("A")]])
        result = s._collect_raw({}, "ua", "q", "http://x", count=10, days=None)
        ids = [r["id"] for r in result]
        assert ids == ["A", "B"]
        assert len(ids) == len(set(ids))

    def test_cross_page_deduplication(self):
        s = scraper()
        page1 = [make_raw_job(str(i)) for i in range(PAGE_SIZE)]
        # page2 starts with two IDs from page1, then adds new ones
        page2 = [make_raw_job("0"), make_raw_job("1"), make_raw_job("new-1"), make_raw_job("new-2")]
        _patch_fetch(s, [page1, page2])
        result = s._collect_raw({}, "ua", "q", "http://x", count=PAGE_SIZE + 2, days=None)
        ids = [r["id"] for r in result]
        assert len(ids) == len(set(ids)), "cross-page duplicates found"
        assert "new-1" in ids and "new-2" in ids

    def test_returns_empty_when_no_results(self):
        s = scraper()
        _patch_fetch(s, [[]])
        assert s._collect_raw({}, "ua", "q", "http://x", count=10, days=None) == []

    def test_empty_api_response_terminates_immediately(self):
        s = scraper()
        call_count = [0]
        def counting_fetch(cookies, ua, query, url, offset):
            call_count[0] += 1
            return []
        s._fetch_page = counting_fetch
        s._collect_raw({}, "ua", "q", "http://x", count=10, days=None)
        assert call_count[0] == 1, "Should stop after first empty response"


# ---------------------------------------------------------------------------
# _collect_raw – date filtering
# ---------------------------------------------------------------------------

class TestCollectRawDateFilter:
    @staticmethod
    def _now():
        return datetime.now(tz=timezone.utc)

    def test_excludes_jobs_older_than_days(self):
        now = self._now()
        new_time = (now - timedelta(hours=6)).isoformat()
        old_time = (now - timedelta(days=10)).isoformat()
        s = scraper()
        _patch_fetch(s, [[make_raw_job("new", publish_time=new_time),
                          make_raw_job("old", publish_time=old_time)]])
        result = s._collect_raw({}, "ua", "q", "http://x", count=10, days=3)
        ids = [r["id"] for r in result]
        assert ids == ["new"]

    def test_keeps_jobs_within_days_window(self):
        now = self._now()
        recent = (now - timedelta(hours=12)).isoformat()
        s = scraper()
        _patch_fetch(s, [[make_raw_job("recent", publish_time=recent)]])
        result = s._collect_raw({}, "ua", "q", "http://x", count=10, days=1)
        assert len(result) == 1 and result[0]["id"] == "recent"

    def test_days_none_does_not_filter(self):
        old_time = "2020-01-01T00:00:00+00:00"
        s = scraper()
        _patch_fetch(s, [[make_raw_job("ancient", publish_time=old_time)]])
        result = s._collect_raw({}, "ua", "q", "http://x", count=10, days=None)
        assert len(result) == 1

    def test_stops_paginating_after_cutoff(self):
        now = self._now()
        new_time = (now - timedelta(hours=1)).isoformat()
        old_time = (now - timedelta(days=5)).isoformat()

        call_count = [0]
        def fetch(cookies, ua, query, url, offset):
            call_count[0] += 1
            if offset == 0:
                return (
                    [make_raw_job(str(i), publish_time=new_time) for i in range(PAGE_SIZE - 1)]
                    + [make_raw_job("old", publish_time=old_time)]
                )
            return [make_raw_job("should-not-appear")]

        s = scraper()
        s._fetch_page = fetch
        result = s._collect_raw({}, "ua", "q", "http://x", count=100, days=2)
        assert call_count[0] == 1, "Should stop after hitting cutoff"
        assert all(r["id"] != "should-not-appear" for r in result)

    def test_unparseable_publish_time_is_included(self):
        s = scraper()
        raw = make_raw_job("x")
        raw["jobTile"]["job"]["publishTime"] = "not-a-date"
        _patch_fetch(s, [[raw]])
        result = s._collect_raw({}, "ua", "q", "http://x", count=10, days=1)
        assert len(result) == 1  # unparseable → assume valid, include it


# ---------------------------------------------------------------------------
# scrape() – integration (browser / network both patched)
# ---------------------------------------------------------------------------

class TestScrapeIntegration:
    @pytest.mark.asyncio
    async def test_scrape_returns_job_listings(self):
        s = scraper()
        _patch_session(s)
        _patch_fetch(s, [[make_raw_job(str(i)) for i in range(3)]])
        listings = await s.scrape(query="python", count=3, days=None)
        assert len(listings) == 3
        assert all(isinstance(l, JobListing) for l in listings)

    @pytest.mark.asyncio
    async def test_scrape_respects_count(self):
        s = scraper()
        _patch_session(s)
        _patch_fetch(s, [[make_raw_job(str(i)) for i in range(PAGE_SIZE)]])
        listings = await s.scrape(query="python", count=7, days=None)
        assert len(listings) == 7

    @pytest.mark.asyncio
    async def test_scrape_applies_date_filter(self):
        now = datetime.now(tz=timezone.utc)
        new_time = (now - timedelta(hours=2)).isoformat()
        old_time = (now - timedelta(days=10)).isoformat()
        s = scraper()
        _patch_session(s)
        _patch_fetch(s, [[make_raw_job("new", publish_time=new_time),
                          make_raw_job("old", publish_time=old_time)]])
        listings = await s.scrape(query="python", count=10, days=1)
        ids = [l.job_id for l in listings]
        assert "new" in ids and "old" not in ids

    @pytest.mark.asyncio
    async def test_scrape_returns_upwork_source(self):
        s = scraper()
        _patch_session(s)
        _patch_fetch(s, [[make_raw_job("xyz")]])
        listings = await s.scrape(query="python", count=1, days=None)
        assert all(l.source == "upwork" for l in listings)

    @pytest.mark.asyncio
    async def test_scrape_empty_results(self):
        s = scraper()
        _patch_session(s)
        _patch_fetch(s, [[]])
        listings = await s.scrape(query="nonexistent-xyz", count=10, days=None)
        assert listings == []

    @pytest.mark.asyncio
    async def test_scrape_no_duplicate_job_ids(self):
        s = scraper()
        _patch_session(s)
        page = [make_raw_job("A"), make_raw_job("B"), make_raw_job("A")]  # dup
        _patch_fetch(s, [page])
        listings = await s.scrape(query="python", count=10, days=None)
        ids = [l.job_id for l in listings]
        assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# scrape_many() – multi-query, single browser session
# ---------------------------------------------------------------------------

class TestScrapeMany:
    def _query_aware_fetch(self, data: dict[str, list[dict]]):
        """Return a _fetch_page stub keyed by query string."""
        def fetch(cookies, ua, query, url, offset):
            return data.get(query, []) if offset == 0 else []
        return fetch

    @pytest.mark.asyncio
    async def test_returns_results_for_each_query(self):
        s = scraper()
        _patch_session(s)
        s._fetch_page = self._query_aware_fetch({
            "python": [make_raw_job("py-1"), make_raw_job("py-2")],
            "django": [make_raw_job("dj-1")],
        })
        results = await s.scrape_many(queries=["python", "django"], count=10, days=None)
        assert set(results.keys()) == {"python", "django"}
        assert len(results["python"]) == 2
        assert len(results["django"]) == 1

    @pytest.mark.asyncio
    async def test_all_values_are_job_listings(self):
        s = scraper()
        _patch_session(s)
        s._fetch_page = lambda cookies, ua, query, url, offset: [make_raw_job("x")] if offset == 0 else []
        results = await s.scrape_many(queries=["python"], count=5, days=None)
        assert all(isinstance(l, JobListing) for l in results["python"])

    @pytest.mark.asyncio
    async def test_opens_browser_exactly_once(self):
        s = scraper()
        session_calls = [0]

        async def counting_session(url):
            session_calls[0] += 1
            return ({"UniversalSearchNuxt_vt": "token"}, "ua")

        s._get_session = counting_session
        s._fetch_page = lambda *a, **k: []
        await s.scrape_many(queries=["python", "django", "fastapi"], count=5, days=None)
        assert session_calls[0] == 1

    @pytest.mark.asyncio
    async def test_empty_queries_returns_empty_dict(self):
        s = scraper()
        _patch_session(s)
        results = await s.scrape_many(queries=[], count=10, days=None)
        assert results == {}

    @pytest.mark.asyncio
    async def test_respects_count_per_query(self):
        s = scraper()
        _patch_session(s)
        # Return 20 jobs for every query
        s._fetch_page = lambda cookies, ua, query, url, offset: (
            [make_raw_job(f"{query}-{i}") for i in range(20)] if offset == 0 else []
        )
        results = await s.scrape_many(queries=["python", "django"], count=5, days=None)
        assert len(results["python"]) == 5
        assert len(results["django"]) == 5

    @pytest.mark.asyncio
    async def test_applies_date_filter_to_all_queries(self):
        now = datetime.now(tz=timezone.utc)
        new_time = (now - timedelta(hours=1)).isoformat()
        old_time = (now - timedelta(days=10)).isoformat()

        s = scraper()
        _patch_session(s)
        s._fetch_page = self._query_aware_fetch({
            "python": [make_raw_job("py-new", publish_time=new_time), make_raw_job("py-old", publish_time=old_time)],
            "rust":   [make_raw_job("rs-new", publish_time=new_time), make_raw_job("rs-old", publish_time=old_time)],
        })
        results = await s.scrape_many(queries=["python", "rust"], count=10, days=2)
        assert [l.job_id for l in results["python"]] == ["py-new"]
        assert [l.job_id for l in results["rust"]] == ["rs-new"]

    @pytest.mark.asyncio
    async def test_preserves_query_order(self):
        queries = ["fastapi", "python", "django"]
        s = scraper()
        _patch_session(s)
        s._fetch_page = lambda *a, **k: []
        results = await s.scrape_many(queries=queries, count=5, days=None)
        assert list(results.keys()) == queries

    @pytest.mark.asyncio
    async def test_source_field_is_upwork_for_all(self):
        s = scraper()
        _patch_session(s)
        s._fetch_page = self._query_aware_fetch({
            "python": [make_raw_job("py-1")],
            "django": [make_raw_job("dj-1")],
        })
        results = await s.scrape_many(queries=["python", "django"], count=5, days=None)
        for listings in results.values():
            assert all(l.source == "upwork" for l in listings)

    @pytest.mark.asyncio
    async def test_single_query_behaves_same_as_scrape(self):
        """scrape_many with one query should return same listings as scrape()."""
        raw = [make_raw_job("solo-1"), make_raw_job("solo-2")]
        s1 = scraper()
        _patch_session(s1)
        _patch_fetch(s1, [raw])
        single = await s1.scrape(query="python", count=5, days=None)

        s2 = scraper()
        _patch_session(s2)
        s2._fetch_page = lambda cookies, ua, query, url, offset: raw if offset == 0 else []
        many = await s2.scrape_many(queries=["python"], count=5, days=None)

        assert [l.job_id for l in single] == [l.job_id for l in many["python"]]
