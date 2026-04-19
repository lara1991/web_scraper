"""LinkedIn job scraper using the public guest API.

Strategy
--------
LinkedIn exposes a guest (unauthenticated) search endpoint that returns HTML
job cards.  For each job we optionally fetch a second detail page to obtain
the full description and structured criteria (seniority, employment type, …).

Endpoints
---------
Search :  GET https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search
          Returns an HTML fragment: a sequence of <li> job cards.
          25 results per page; paginate via ``start`` parameter.

Detail :  GET https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}
          Returns a standalone HTML page with the full job posting.

Rate limiting
-------------
LinkedIn throttles aggressive scrapers (HTTP 429).  The default config adds a
``request_delay`` (seconds) between paginated search requests and a smaller
``detail_delay`` between individual detail requests.  Reduce concurrency or
increase these values if you hit 429 errors.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

from web_scraping.base_scraper import BaseScraper
from web_scraping.models import LinkedInJobListing
from web_scraping.linkedin.filters import LinkedInFilters, days_to_time_filter

_SEARCH_BASE = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
_DETAIL_BASE = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
_PAGE_SIZE   = 25   # LinkedIn search returns 25 results per page

_DEFAULT_HEADERS = {
    "accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.9",
    "referer":         "https://www.linkedin.com/",
    "user-agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}


class LinkedInScraper(BaseScraper):
    """Scrapes LinkedIn job listings via the public guest API.

    All config keys are read from the ``linkedin`` section of
    ``scraping_configs.yaml``.  Supported keys:

    output_file     : path to the CSV output file
    request_delay   : seconds to sleep between paginated search requests (default 1.0)
    detail_delay    : seconds to sleep between job detail requests (default 0.5)
    fetch_details   : whether to fetch full description / criteria per job (default true)
    filters         : optional sub-section with LinkedIn filter values:
        location          : e.g. "United States"
        experience_levels : list of ExperienceLevelFilter values ("2", "4", …)
        employment_types  : list of EmploymentTypeFilter values ("F", "C", …)
        workplace_types   : list of WorkplaceTypeFilter values ("1", "2", "3")
        time_filter       : a TimeFilter value ("r86400", "r604800", "r2592000")
    defaults        : sub-section with default CLI values
        query   : list of default search queries
        count   : default result count per query
        days    : default date range filter
    """

    SOURCE = "linkedin"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._request_delay: float = float(config.get("request_delay", 1.0))
        self._detail_delay:  float = float(config.get("detail_delay",  0.5))
        self._fetch_details: bool  = bool(config.get("fetch_details",  True))
        self._default_filters = LinkedInFilters.from_config(config.get("filters", {}))

    # ------------------------------------------------------------------
    # BaseScraper interface
    # ------------------------------------------------------------------

    async def scrape(
        self, query: str, count: int, days: int | None
    ) -> list[LinkedInJobListing]:
        raw = self._collect_raw(query, count, days)
        return [self._to_listing(job) for job in raw]

    async def scrape_many(
        self, queries: list[str], count: int, days: int | None
    ) -> dict[str, list[LinkedInJobListing]]:
        """Scrape multiple queries sequentially to respect rate limits."""
        results: dict[str, list[LinkedInJobListing]] = {}
        for query in queries:
            results[query] = await self.scrape(query, count, days)
        return results

    # ------------------------------------------------------------------
    # Private helpers — HTTP
    # ------------------------------------------------------------------

    def _build_search_url(self, query: str, offset: int, days: int | None) -> str:
        params: dict[str, str] = {
            "keywords": query,
            "start":    str(offset),
            "sortBy":   "DD",   # most-recent first
        }
        params.update(self._default_filters.to_url_params())
        # Apply date filter only if not already set via config
        if days is not None and "f_TPR" not in params:
            params["f_TPR"] = days_to_time_filter(days).value
        return f"{_SEARCH_BASE}?{urlencode(params)}"

    def _fetch_search_html(self, query: str, offset: int, days: int | None) -> str:
        """Fetch one page of search results; returns raw HTML."""
        url = _SEARCH_BASE + "?" + urlencode({
            "keywords": query,
            "start":    str(offset),
            "sortBy":   "DD",
            **self._default_filters.to_url_params(),
            **({"f_TPR": days_to_time_filter(days).value}
               if days is not None and "f_TPR" not in self._default_filters.to_url_params()
               else {}),
        })
        session = cffi_requests.Session(impersonate="chrome")
        resp = session.get(url, headers=_DEFAULT_HEADERS, timeout=20)
        resp.raise_for_status()
        return resp.text

    def _fetch_detail_html(self, job_id: str) -> str:
        """Fetch job detail page; returns raw HTML (empty string on failure)."""
        url = _DETAIL_BASE.format(job_id=job_id)
        session = cffi_requests.Session(impersonate="chrome")
        try:
            resp = session.get(url, headers=_DEFAULT_HEADERS, timeout=15)
            if resp.status_code == 200:
                return resp.text
        except Exception:
            pass
        return ""

    # ------------------------------------------------------------------
    # Private helpers — HTML parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_search_html(html: str) -> list[dict]:
        """Parse a search-result HTML fragment into a list of raw job dicts."""
        soup = BeautifulSoup(html, "html.parser")
        jobs: list[dict] = []

        for card in soup.select("li"):
            div = card.find("div", attrs={"data-entity-urn": True})
            if not div:
                continue

            urn    = div.get("data-entity-urn", "")
            job_id = urn.split(":")[-1] if urn else ""
            if not job_id:
                continue

            title_el    = div.select_one("h3.base-search-card__title")
            company_el  = div.select_one("h4.base-search-card__subtitle")
            location_el = div.select_one(".job-search-card__location")
            time_el     = div.select_one("time")
            link_el     = div.select_one("a.base-card__full-link")

            jobs.append({
                "job_id":       job_id,
                "title":        title_el.get_text(strip=True)              if title_el    else "",
                "company":      company_el.get_text(strip=True)            if company_el  else "",
                "location":     location_el.get_text(strip=True)           if location_el else "",
                "publish_time": time_el.get("datetime", "")                if time_el     else "",
                "url":          link_el.get("href", "").split("?")[0]      if link_el     else "",
            })

        return jobs

    @staticmethod
    def _parse_detail_html(html: str) -> dict:
        """Parse a job detail page into a supplementary dict."""
        if not html:
            return {}

        soup = BeautifulSoup(html, "html.parser")

        # Full description
        desc_el  = soup.select_one(".show-more-less-html__markup")
        description = desc_el.get_text(separator="\n", strip=True)[:500] if desc_el else ""

        # Structured criteria (seniority level, employment type, job function, industries)
        criteria: dict[str, str] = {}
        for item in soup.select(".description__job-criteria-item"):
            header = item.select_one(".description__job-criteria-subheader")
            value  = item.select_one(
                ".description__job-criteria-text--criteria, .description__job-criteria-text"
            )
            if header and value:
                criteria[header.get_text(strip=True).lower()] = value.get_text(strip=True)

        # Applicant count
        applicant_el = soup.select_one(
            ".num-applicants__caption, "
            ".num-applicants__caption--reached-applicant-limit"
        )
        applicant_count = applicant_el.get_text(strip=True) if applicant_el else ""

        # Workplace type (may appear as a badge in the top card)
        workplace_el = soup.select_one(
            ".workplace-type, .jobs-unified-top-card__workplace-type"
        )
        workplace_type = (
            workplace_el.get_text(strip=True) if workplace_el
            else criteria.get("on-site/remote", "")
        )

        return {
            "description":    description,
            "experience_level": criteria.get("seniority level", ""),
            "employment_type":  criteria.get("employment type", ""),
            "skills":           criteria.get("job function", ""),
            "applicant_count":  applicant_count,
            "workplace_type":   workplace_type,
        }

    # ------------------------------------------------------------------
    # Private helpers — collection
    # ------------------------------------------------------------------

    def _collect_raw(self, query: str, count: int, days: int | None) -> list[dict]:
        """Paginate through search results and optionally fetch job details."""
        cutoff: date | None = None
        if days is not None:
            cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=days)).date()

        seen_ids: set[str] = set()
        collected: list[dict] = []
        offset = 0
        page_num = 0

        while len(collected) < count:
            logger.info("[%s] Fetching search page %d (offset=%d) ...", query, page_num + 1, offset)
            html = self._fetch_search_html(query, offset, days)
            page = self._parse_search_html(html)

            if not page:
                logger.info("[%s] No more results.", query)
                break

            logger.info("[%s] Page %d: %d card(s) found", query, page_num + 1, len(page))
            reached_cutoff = False
            for job in page:
                job_id = job["job_id"]
                if not job_id or job_id in seen_ids:
                    continue

                # Date filter (day-level precision — LinkedIn returns ISO date strings)
                if cutoff is not None and job.get("publish_time"):
                    try:
                        pub = date.fromisoformat(job["publish_time"])
                        if pub < cutoff:
                            logger.info("[%s] Date cutoff reached on page %d.", query, page_num + 1)
                            reached_cutoff = True
                            break
                    except ValueError:
                        pass   # unparseable date → include the job

                seen_ids.add(job_id)

                # Optional per-job detail fetch
                if self._fetch_details:
                    time.sleep(self._detail_delay)
                    detail = self._parse_detail_html(self._fetch_detail_html(job_id))
                    job.update(detail)

                collected.append(job)
                if len(collected) >= count:
                    break

            logger.info("[%s] Page %d done — %d/%d job(s) collected", query, page_num + 1, len(collected), count)
            page_num += 1
            offset += len(page)
            if len(page) < _PAGE_SIZE or reached_cutoff:
                break

            # Polite delay between search pages
            if len(collected) < count:
                logger.debug("[%s] Waiting %.1f s before next page ...", query, self._request_delay)
                time.sleep(self._request_delay)

        return collected[:count]

    # ------------------------------------------------------------------
    # Conversion: raw dict → LinkedInJobListing
    # ------------------------------------------------------------------

    @staticmethod
    def _to_listing(raw: dict) -> LinkedInJobListing:
        return LinkedInJobListing(
            job_id=raw.get("job_id", ""),
            source=LinkedInScraper.SOURCE,
            title=raw.get("title", ""),
            company=raw.get("company", ""),
            location=raw.get("location", ""),
            workplace_type=raw.get("workplace_type", ""),
            employment_type=raw.get("employment_type", ""),
            experience_level=raw.get("experience_level", ""),
            description=raw.get("description", ""),
            skills=raw.get("skills", ""),
            publish_time=raw.get("publish_time", ""),
            url=raw.get("url", ""),
            applicant_count=raw.get("applicant_count", ""),
        )
