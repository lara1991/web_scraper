"""Tests for web_scraping.linkedin.scraper.LinkedInScraper.

All tests are fully offline: _fetch_search_html and _fetch_detail_html are
monkeypatched to return canned HTML strings — no network calls are made.
"""

from datetime import date, timedelta
from unittest.mock import patch

import pytest

from web_scraping.linkedin.scraper import LinkedInScraper, _PAGE_SIZE
from web_scraping.linkedin.filters import (
    LinkedInFilters,
    ExperienceLevelFilter,
    EmploymentTypeFilter,
    WorkplaceTypeFilter,
    TimeFilter,
    days_to_time_filter,
)
from web_scraping.models import LinkedInJobListing
from tests.conftest import LINKEDIN_CONFIG, make_raw_li_job, NOW_DATE, OLD_DATE


# ---------------------------------------------------------------------------
# Helpers — canned HTML generators
# ---------------------------------------------------------------------------

def _search_card_html(
    job_id: str,
    title: str = "Python Developer",
    company: str = "TechCorp",
    location: str = "San Francisco, CA",
    publish_date: str = NOW_DATE,
    url: str = "",
) -> str:
    url = url or f"https://www.linkedin.com/jobs/view/{job_id}"
    return f"""
<li>
  <div class="base-card" data-entity-urn="urn:li:jobPosting:{job_id}">
    <a class="base-card__full-link" href="{url}?trackingId=xyz"></a>
    <div class="base-search-card__info">
      <h3 class="base-search-card__title">{title}</h3>
      <h4 class="base-search-card__subtitle">
        <a class="hidden-nested-link">{company}</a>
      </h4>
      <div class="base-search-card__metadata">
        <span class="job-search-card__location">{location}</span>
        <time class="job-search-card__listdate" datetime="{publish_date}">1 day ago</time>
      </div>
    </div>
  </div>
</li>
"""


def _make_search_html(*cards: str) -> str:
    return "<ul>" + "".join(cards) + "</ul>"


def _detail_html(
    description: str = "We need a Python developer.",
    seniority: str = "Mid-Senior level",
    employment_type: str = "Full-time",
    job_function: str = "Software Engineering",
    industries: str = "Technology",
    applicant_count: str = "Over 25 applicants",
    workplace_type: str = "",
) -> str:
    workplace_badge = (
        f'<span class="workplace-type">{workplace_type}</span>' if workplace_type else ""
    )
    return f"""
<div class="show-more-less-html__markup">
  <p>{description}</p>
</div>
{workplace_badge}
<ul class="description__job-criteria-list">
  <li class="description__job-criteria-item">
    <h3 class="description__job-criteria-subheader">Seniority level</h3>
    <span class="description__job-criteria-text--criteria">{seniority}</span>
  </li>
  <li class="description__job-criteria-item">
    <h3 class="description__job-criteria-subheader">Employment type</h3>
    <span class="description__job-criteria-text--criteria">{employment_type}</span>
  </li>
  <li class="description__job-criteria-item">
    <h3 class="description__job-criteria-subheader">Job function</h3>
    <span class="description__job-criteria-text--criteria">{job_function}</span>
  </li>
  <li class="description__job-criteria-item">
    <h3 class="description__job-criteria-subheader">Industries</h3>
    <span class="description__job-criteria-text--criteria">{industries}</span>
  </li>
</ul>
<span class="num-applicants__caption">{applicant_count}</span>
"""


def _scraper(**kwargs) -> LinkedInScraper:
    cfg = dict(LINKEDIN_CONFIG, **kwargs)
    return LinkedInScraper(cfg)


# ---------------------------------------------------------------------------
# Filter helpers
# ---------------------------------------------------------------------------

class TestDaysToTimeFilter:
    def test_1_day_maps_to_day(self):
        assert days_to_time_filter(1) == TimeFilter.DAY

    def test_7_days_maps_to_week(self):
        assert days_to_time_filter(7) == TimeFilter.WEEK

    def test_30_days_maps_to_month(self):
        assert days_to_time_filter(30) == TimeFilter.MONTH

    def test_2_days_maps_to_week(self):
        assert days_to_time_filter(2) == TimeFilter.WEEK


class TestLinkedInFiltersUrlParams:
    def test_empty_filters_returns_empty_dict(self):
        filters = LinkedInFilters()
        assert filters.to_url_params() == {}

    def test_location_included(self):
        filters = LinkedInFilters(location="United States")
        params = filters.to_url_params()
        assert params["location"] == "United States"

    def test_experience_levels_joined(self):
        filters = LinkedInFilters(
            experience_levels=[ExperienceLevelFilter.ENTRY, ExperienceLevelFilter.MID_SENIOR]
        )
        params = filters.to_url_params()
        assert params["f_E"] == "2,4"

    def test_employment_types_joined(self):
        filters = LinkedInFilters(
            employment_types=[EmploymentTypeFilter.FULL_TIME, EmploymentTypeFilter.CONTRACT]
        )
        assert filters.to_url_params()["f_JT"] == "F,C"

    def test_workplace_types_joined(self):
        filters = LinkedInFilters(
            workplace_types=[WorkplaceTypeFilter.REMOTE, WorkplaceTypeFilter.HYBRID]
        )
        assert filters.to_url_params()["f_WT"] == "2,3"

    def test_time_filter_included(self):
        filters = LinkedInFilters(time_filter=TimeFilter.WEEK.value)
        assert filters.to_url_params()["f_TPR"] == "r604800"

    def test_from_config_parses_all_fields(self):
        cfg = {
            "location": "Germany",
            "experience_levels": ["2", "4"],
            "employment_types":  ["F"],
            "workplace_types":   ["2"],
            "time_filter":       "r86400",
        }
        f = LinkedInFilters.from_config(cfg)
        assert f.location == "Germany"
        assert ExperienceLevelFilter.ENTRY in f.experience_levels
        assert ExperienceLevelFilter.MID_SENIOR in f.experience_levels
        assert f.employment_types == [EmploymentTypeFilter.FULL_TIME]
        assert f.workplace_types == [WorkplaceTypeFilter.REMOTE]
        assert f.time_filter == "r86400"

    def test_from_config_empty_dict(self):
        f = LinkedInFilters.from_config({})
        assert f.location == ""
        assert f.experience_levels == []
        assert f.employment_types == []


# ---------------------------------------------------------------------------
# HTML parsing — search results
# ---------------------------------------------------------------------------

class TestParseSearchHtml:
    def test_parses_single_job(self):
        html = _make_search_html(_search_card_html("12345", "Python Dev", "Acme", "NYC"))
        jobs = LinkedInScraper._parse_search_html(html)
        assert len(jobs) == 1
        assert jobs[0]["job_id"] == "12345"
        assert jobs[0]["title"] == "Python Dev"
        assert jobs[0]["company"] == "Acme"
        assert jobs[0]["location"] == "NYC"
        assert jobs[0]["publish_time"] == NOW_DATE

    def test_parses_multiple_jobs(self):
        html = _make_search_html(
            _search_card_html("1", "Job A"),
            _search_card_html("2", "Job B"),
            _search_card_html("3", "Job C"),
        )
        jobs = LinkedInScraper._parse_search_html(html)
        assert len(jobs) == 3
        assert [j["job_id"] for j in jobs] == ["1", "2", "3"]

    def test_strips_tracking_from_url(self):
        html = _make_search_html(
            _search_card_html("42", url="https://www.linkedin.com/jobs/view/42?trackingId=abc")
        )
        jobs = LinkedInScraper._parse_search_html(html)
        assert "?" not in jobs[0]["url"]
        assert jobs[0]["url"] == "https://www.linkedin.com/jobs/view/42"

    def test_empty_html_returns_empty_list(self):
        assert LinkedInScraper._parse_search_html("") == []
        assert LinkedInScraper._parse_search_html("<ul></ul>") == []

    def test_missing_fields_default_to_empty_strings(self):
        html = """<li>
          <div class="base-card" data-entity-urn="urn:li:jobPosting:99">
          </div></li>"""
        jobs = LinkedInScraper._parse_search_html(html)
        assert len(jobs) == 1
        assert jobs[0]["title"] == ""
        assert jobs[0]["company"] == ""


# ---------------------------------------------------------------------------
# HTML parsing — job details
# ---------------------------------------------------------------------------

class TestParseDetailHtml:
    def test_parses_all_criteria(self):
        html = _detail_html(
            description="Build APIs.",
            seniority="Entry level",
            employment_type="Contract",
            job_function="Engineering",
            applicant_count="10 applicants",
            workplace_type="Remote",
        )
        detail = LinkedInScraper._parse_detail_html(html)
        assert detail["description"] == "Build APIs."
        assert detail["experience_level"] == "Entry level"
        assert detail["employment_type"] == "Contract"
        assert detail["skills"] == "Engineering"
        assert detail["applicant_count"] == "10 applicants"
        assert detail["workplace_type"] == "Remote"

    def test_empty_html_returns_empty_dict(self):
        assert LinkedInScraper._parse_detail_html("") == {}

    def test_description_truncated_to_500_chars(self):
        html = _detail_html(description="x" * 600)
        detail = LinkedInScraper._parse_detail_html(html)
        assert len(detail["description"]) == 500

    def test_missing_criteria_return_empty_strings(self):
        html = """<div class="show-more-less-html__markup"><p>Hi</p></div>"""
        detail = LinkedInScraper._parse_detail_html(html)
        assert detail["experience_level"] == ""
        assert detail["employment_type"] == ""
        assert detail["applicant_count"] == ""


# ---------------------------------------------------------------------------
# _to_listing
# ---------------------------------------------------------------------------

class TestToListing:
    def test_maps_all_fields(self):
        raw = make_raw_li_job("li-1", title="ML Engineer", company="DeepAI",
                              location="Remote", publish_time=NOW_DATE)
        listing = LinkedInScraper._to_listing(raw)

        assert isinstance(listing, LinkedInJobListing)
        assert listing.job_id == "li-1"
        assert listing.source == "linkedin"
        assert listing.title == "ML Engineer"
        assert listing.company == "DeepAI"
        assert listing.location == "Remote"
        assert listing.publish_time == NOW_DATE

    def test_source_is_always_linkedin(self):
        listing = LinkedInScraper._to_listing(make_raw_li_job("x"))
        assert listing.source == "linkedin"

    def test_empty_raw_dict_gives_empty_strings(self):
        listing = LinkedInScraper._to_listing({})
        assert listing.job_id == ""
        assert listing.title == ""
        assert listing.company == ""


# ---------------------------------------------------------------------------
# _collect_raw — pagination, deduplication (no network)
# ---------------------------------------------------------------------------

class TestCollectRaw:
    def _scraper_with_pages(self, pages: list[list[str]]) -> LinkedInScraper:
        """Return a scraper whose _fetch_search_html returns canned HTML pages."""
        s = _scraper(fetch_details=False)

        def fake_fetch(query, offset, days):
            idx = offset // _PAGE_SIZE
            return _make_search_html(*pages[idx]) if idx < len(pages) else ""

        s._fetch_search_html = fake_fetch
        return s

    def test_returns_requested_count(self):
        cards = [_search_card_html(str(i)) for i in range(_PAGE_SIZE)]
        s = self._scraper_with_pages([cards])
        result = s._collect_raw("python", count=5, days=None)
        assert len(result) == 5

    def test_stops_when_api_exhausted(self):
        cards = [_search_card_html("a"), _search_card_html("b")]
        s = self._scraper_with_pages([cards])
        result = s._collect_raw("python", count=10, days=None)
        assert len(result) == 2

    def test_paginates_for_more_results(self):
        page1 = [_search_card_html(str(i)) for i in range(_PAGE_SIZE)]
        page2 = [_search_card_html(str(i)) for i in range(_PAGE_SIZE, _PAGE_SIZE + 5)]
        s = self._scraper_with_pages([page1, page2])
        result = s._collect_raw("python", count=_PAGE_SIZE + 3, days=None)
        assert len(result) == _PAGE_SIZE + 3

    def test_deduplication_within_page(self):
        cards = [_search_card_html("A"), _search_card_html("B"), _search_card_html("A")]
        s = self._scraper_with_pages([cards])
        result = s._collect_raw("q", count=10, days=None)
        ids = [r["job_id"] for r in result]
        assert ids == ["A", "B"]

    def test_cross_page_deduplication(self):
        page1 = [_search_card_html(str(i)) for i in range(_PAGE_SIZE)]
        page2 = [
            _search_card_html("0"),       # duplicate from page1
            _search_card_html("new-1"),
        ]
        s = self._scraper_with_pages([page1, page2])
        result = s._collect_raw("q", count=_PAGE_SIZE + 1, days=None)
        ids = [r["job_id"] for r in result]
        assert len(ids) == len(set(ids))
        assert "new-1" in ids

    def test_empty_page_stops_immediately(self):
        call_count = [0]

        def fake_fetch(query, offset, days):
            call_count[0] += 1
            return ""

        s = _scraper(fetch_details=False)
        s._fetch_search_html = fake_fetch
        s._collect_raw("q", count=10, days=None)
        assert call_count[0] == 1


# ---------------------------------------------------------------------------
# _collect_raw — date filtering
# ---------------------------------------------------------------------------

class TestCollectRawDateFilter:
    def _today(self) -> str:
        from datetime import datetime, timezone
        return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    def _ago(self, days: int) -> str:
        from datetime import datetime, timezone
        return (datetime.now(tz=timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    def _scraper_with_cards(self, cards: list[str]) -> LinkedInScraper:
        s = _scraper(fetch_details=False)
        s._fetch_search_html = lambda q, offset, days: (
            _make_search_html(*cards) if offset == 0 else ""
        )
        return s

    def test_excludes_jobs_older_than_days(self):
        new_date = self._ago(1)
        old_date = self._ago(10)
        s = self._scraper_with_cards([
            _search_card_html("new", publish_date=new_date),
            _search_card_html("old", publish_date=old_date),
        ])
        result = s._collect_raw("q", count=10, days=3)
        assert [r["job_id"] for r in result] == ["new"]

    def test_days_none_does_not_filter(self):
        old_date = "2020-01-01"
        s = self._scraper_with_cards([_search_card_html("x", publish_date=old_date)])
        result = s._collect_raw("q", count=10, days=None)
        assert len(result) == 1

    def test_unparseable_date_included(self):
        s = self._scraper_with_cards([_search_card_html("x", publish_date="not-a-date")])
        result = s._collect_raw("q", count=10, days=1)
        assert len(result) == 1   # unknown date → include


# ---------------------------------------------------------------------------
# _collect_raw — detail fetching
# ---------------------------------------------------------------------------

class TestCollectRawDetailFetching:
    def test_detail_fetched_when_configured(self):
        fetch_calls: list[str] = []

        s = _scraper(fetch_details=True)
        s._fetch_search_html = lambda q, o, d: (
            _make_search_html(_search_card_html("101")) if o == 0 else ""
        )

        def fake_detail(job_id: str) -> str:
            fetch_calls.append(job_id)
            return _detail_html(seniority="Senior")

        s._fetch_detail_html = fake_detail
        result = s._collect_raw("q", count=1, days=None)
        assert "101" in fetch_calls
        assert result[0]["experience_level"] == "Senior"

    def test_detail_not_fetched_when_disabled(self):
        fetch_calls: list[str] = []

        s = _scraper(fetch_details=False)
        s._fetch_search_html = lambda q, o, d: (
            _make_search_html(_search_card_html("102")) if o == 0 else ""
        )
        s._fetch_detail_html = lambda job_id: fetch_calls.append(job_id) or ""

        s._collect_raw("q", count=1, days=None)
        assert fetch_calls == []


# ---------------------------------------------------------------------------
# scrape() and scrape_many() — integration (all network patched)
# ---------------------------------------------------------------------------

class TestScrapeIntegration:
    def _patch(self, s: LinkedInScraper, cards: list[str]) -> None:
        s._fetch_search_html = lambda q, o, d: (
            _make_search_html(*cards) if o == 0 else ""
        )
        s._fetch_detail_html = lambda job_id: ""

    @pytest.mark.asyncio
    async def test_scrape_returns_linkedin_listings(self):
        s = _scraper(fetch_details=False)
        self._patch(s, [_search_card_html("1"), _search_card_html("2")])
        listings = await s.scrape(query="python", count=2, days=None)
        assert len(listings) == 2
        assert all(isinstance(l, LinkedInJobListing) for l in listings)

    @pytest.mark.asyncio
    async def test_scrape_source_is_linkedin(self):
        s = _scraper(fetch_details=False)
        self._patch(s, [_search_card_html("5")])
        listings = await s.scrape(query="python", count=1, days=None)
        assert listings[0].source == "linkedin"

    @pytest.mark.asyncio
    async def test_scrape_respects_count(self):
        cards = [_search_card_html(str(i)) for i in range(10)]
        s = _scraper(fetch_details=False)
        self._patch(s, cards)
        listings = await s.scrape(query="python", count=3, days=None)
        assert len(listings) == 3

    @pytest.mark.asyncio
    async def test_scrape_empty_results(self):
        s = _scraper(fetch_details=False)
        s._fetch_search_html = lambda q, o, d: ""
        listings = await s.scrape(query="xyz-gibberish", count=10, days=None)
        assert listings == []

    @pytest.mark.asyncio
    async def test_scrape_no_duplicate_ids(self):
        cards = [_search_card_html("A"), _search_card_html("B"), _search_card_html("A")]
        s = _scraper(fetch_details=False)
        self._patch(s, cards)
        listings = await s.scrape(query="python", count=10, days=None)
        ids = [l.job_id for l in listings]
        assert len(ids) == len(set(ids))


class TestScrapeMany:
    def _make_scraper_for_queries(self, data: dict[str, list[str]]) -> LinkedInScraper:
        s = _scraper(fetch_details=False)

        def fake_search(query, offset, days):
            cards = data.get(query, [])
            return _make_search_html(*cards) if offset == 0 else ""

        s._fetch_search_html = fake_search
        return s

    @pytest.mark.asyncio
    async def test_returns_results_for_each_query(self):
        s = self._make_scraper_for_queries({
            "python": [_search_card_html("py-1"), _search_card_html("py-2")],
            "django": [_search_card_html("dj-1")],
        })
        results = await s.scrape_many(queries=["python", "django"], count=10, days=None)
        assert set(results.keys()) == {"python", "django"}
        assert len(results["python"]) == 2
        assert len(results["django"]) == 1

    @pytest.mark.asyncio
    async def test_empty_queries_returns_empty_dict(self):
        s = _scraper(fetch_details=False)
        assert await s.scrape_many(queries=[], count=10, days=None) == {}

    @pytest.mark.asyncio
    async def test_preserves_query_order(self):
        queries = ["python", "fastapi", "django"]
        s = self._make_scraper_for_queries({})
        results = await s.scrape_many(queries=queries, count=5, days=None)
        assert list(results.keys()) == queries

    @pytest.mark.asyncio
    async def test_respects_count_per_query(self):
        cards = [_search_card_html(str(i)) for i in range(10)]
        s = self._make_scraper_for_queries({"python": cards, "django": cards})
        results = await s.scrape_many(queries=["python", "django"], count=3, days=None)
        assert len(results["python"]) == 3
        assert len(results["django"]) == 3

    @pytest.mark.asyncio
    async def test_all_values_are_linkedin_listings(self):
        s = self._make_scraper_for_queries({
            "python": [_search_card_html("1")],
        })
        results = await s.scrape_many(queries=["python"], count=5, days=None)
        assert all(isinstance(l, LinkedInJobListing) for l in results["python"])


# ---------------------------------------------------------------------------
# URL building — verifies filters are encoded correctly
# ---------------------------------------------------------------------------

class TestBuildSearchUrl:
    def test_includes_keywords_and_start(self):
        s = _scraper()
        url = s._build_search_url("python developer", offset=0, days=None)
        assert "keywords=python+developer" in url or "keywords=python%20developer" in url
        assert "start=0" in url

    def test_days_adds_f_tpr(self):
        s = _scraper()
        url = s._build_search_url("q", offset=0, days=7)
        assert "f_TPR=r604800" in url

    def test_config_filter_location_added(self):
        s = _scraper(filters={"location": "Germany"})
        url = s._build_search_url("q", offset=0, days=None)
        assert "location=Germany" in url

    def test_config_time_filter_overrides_days(self):
        s = _scraper(filters={"time_filter": "r86400"})
        url = s._build_search_url("q", offset=0, days=30)
        assert "f_TPR=r86400" in url
        # The days-based filter should NOT be added on top
        assert url.count("f_TPR") == 1

    def test_pagination_offset_increments(self):
        s = _scraper()
        url0 = s._build_search_url("q", offset=0, days=None)
        url25 = s._build_search_url("q", offset=25, days=None)
        assert "start=0" in url0
        assert "start=25" in url25
