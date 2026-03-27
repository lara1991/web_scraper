import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any

import nodriver as uc
from curl_cffi import requests as cffi_requests

from web_scraping.base_scraper import BaseScraper
from web_scraping.models import JobListing

_GRAPHQL_QUERY = """
query visitorJobSearch($requestVariables: VisitorJobSearchV1Request!) {
  search {
    universalSearchNuxt {
      visitorJobSearchV1(request: $requestVariables) {
        results {
          id
          title
          description
          jobTile {
            job {
              ciphertext: cipherText
              jobType
              hourlyBudgetMax
              hourlyBudgetMin
              fixedPriceAmount { amount }
              publishTime
            }
          }
        }
      }
    }
  }
}
"""


class UpworkScraper(BaseScraper):
    """Scrapes Upwork job listings via the internal GraphQL API.

    Strategy:
      1. Open a real Chrome window via nodriver to pass Cloudflare.
      2. Extract the visitor OAuth token set as a cookie.
      3. Use curl_cffi (TLS fingerprint impersonation) to call the
         GraphQL endpoint — no API key needed.

    Requires a running X display (i.e. a normal desktop session).
    """

    SOURCE = "upwork"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._graphql_url: str = config["graphql_url"]
        self._browser_exec: str = config["browser_executable"]
        self._page_size: int = int(config.get("page_size", 50))

    # ------------------------------------------------------------------
    # BaseScraper interface
    # ------------------------------------------------------------------

    async def scrape(self, query: str, count: int, days: int | None) -> list[JobListing]:
        search_url = f"https://www.upwork.com/nx/search/jobs/?q={query}&sort=recency"
        cookies, user_agent = await self._get_session(search_url)
        raw_jobs = self._collect_raw(cookies, user_agent, query, search_url, count, days)
        return [self._to_listing(job) for job in raw_jobs]

    async def scrape_many(
        self, queries: list[str], count: int, days: int | None
    ) -> dict[str, list[JobListing]]:
        """Scrape multiple queries concurrently, reusing a single browser session.

        Opens Chrome exactly once to obtain session cookies, then fires all
        query fetches in parallel threads (curl_cffi is synchronous, so each
        query runs via ``asyncio.to_thread``).

        Args:
            queries: List of search terms.
            count:   Maximum results per query.
            days:    Date-range filter applied to every query.

        Returns:
            Mapping of ``{query: [JobListing, ...]}``, preserving input order.
        """
        if not queries:
            return {}

        first_url = f"https://www.upwork.com/nx/search/jobs/?q={queries[0]}&sort=recency"
        cookies, user_agent = await self._get_session(first_url)

        async def _fetch_query(query: str) -> list[JobListing]:
            search_url = f"https://www.upwork.com/nx/search/jobs/?q={query}&sort=recency"
            raw_jobs = await asyncio.to_thread(
                self._collect_raw, cookies, user_agent, query, search_url, count, days
            )
            return [self._to_listing(job) for job in raw_jobs]

        results = await asyncio.gather(*[_fetch_query(q) for q in queries])
        return dict(zip(queries, results))

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _get_session(self, search_url: str) -> tuple[dict[str, str], str]:
        browser = await uc.start(
            browser_executable_path=self._browser_exec,
            headless=False,
        )
        page = await browser.get(search_url)

        for _ in range(20):
            await asyncio.sleep(1)
            title = await page.evaluate("document.title")
            if "Just a moment" not in str(title) and str(title) != "":
                break

        raw_cookie: str = await page.evaluate("document.cookie")
        user_agent: str = await page.evaluate("navigator.userAgent")
        browser.stop()

        cookies: dict[str, str] = {}
        for part in raw_cookie.split(";"):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                cookies[k.strip()] = v.strip()

        return cookies, str(user_agent)

    def _fetch_page(
        self,
        cookies: dict[str, str],
        user_agent: str,
        query: str,
        search_url: str,
        offset: int,
    ) -> list[dict]:
        token = cookies.get("UniversalSearchNuxt_vt", "")
        headers = {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "origin": "https://www.upwork.com",
            "referer": search_url,
            "user-agent": user_agent,
            "x-requested-with": "XMLHttpRequest",
        }
        if token:
            headers["authorization"] = f"Bearer {token}"

        payload = {
            "query": _GRAPHQL_QUERY,
            "variables": {
                "requestVariables": {
                    "userQuery": query,
                    "sort": "recency",
                    "paging": {"offset": offset, "count": self._page_size},
                }
            },
        }

        session = cffi_requests.Session(impersonate="chrome")
        response = session.post(
            self._graphql_url,
            json=payload,
            headers=headers,
            cookies=cookies,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()

        try:
            return (
                data["data"]["search"]["universalSearchNuxt"]["visitorJobSearchV1"]["results"]
                or []
            )
        except (KeyError, TypeError):
            print("Unexpected GraphQL response structure:")
            print(json.dumps(data, indent=2))
            return []

    def _collect_raw(
        self,
        cookies: dict[str, str],
        user_agent: str,
        query: str,
        search_url: str,
        count: int,
        days: int | None,
    ) -> list[dict]:
        cutoff: datetime | None = None
        if days is not None:
            cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)

        seen_ids: set[str] = set()
        collected: list[dict] = []
        offset = 0

        while len(collected) < count:
            page = self._fetch_page(cookies, user_agent, query, search_url, offset)

            if not page:
                break

            reached_cutoff = False
            for job in page:
                job_id = job.get("id") or (
                    (job.get("jobTile") or {}).get("job", {}).get("ciphertext")
                )
                if job_id in seen_ids:
                    continue

                if cutoff is not None:
                    publish_raw = (
                        (job.get("jobTile") or {}).get("job", {}).get("publishTime", "")
                    )
                    if publish_raw:
                        try:
                            pub_dt = datetime.fromisoformat(publish_raw)
                            if pub_dt.tzinfo is None:
                                pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                            if pub_dt < cutoff:
                                reached_cutoff = True
                                break
                        except ValueError:
                            pass

                seen_ids.add(job_id)
                collected.append(job)

                if len(collected) >= count:
                    break

            offset += len(page)

            if reached_cutoff or len(page) < self._page_size:
                break

        return collected

    @staticmethod
    def _to_listing(raw: dict) -> JobListing:
        job_info = (raw.get("jobTile") or {}).get("job") or {}
        job_type = job_info.get("jobType", "N/A")

        if job_type == "HOURLY":
            lo = job_info.get("hourlyBudgetMin", "?")
            hi = job_info.get("hourlyBudgetMax", "?")
            budget = f"${lo}-${hi}/hr"
        else:
            amount = (job_info.get("fixedPriceAmount") or {}).get("amount", "N/A")
            budget = f"${amount}" if amount != "N/A" else "N/A"

        cipher = job_info.get("ciphertext", "")
        return JobListing(
            job_id=raw.get("id") or cipher,
            source=UpworkScraper.SOURCE,
            title=raw.get("title", "N/A"),
            job_type=job_type,
            budget=budget,
            publish_time=job_info.get("publishTime", "N/A"),
            url=f"https://www.upwork.com/jobs/{cipher}" if cipher else "N/A",
            description=((raw.get("description") or "").strip())[:500],
        )
