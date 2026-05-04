import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import nodriver as uc
from curl_cffi import requests as cffi_requests

from web_scraping.base_scraper import BaseScraper
from web_scraping.models import JobListing
from web_scraping.skill_extractor import extract_skills

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GraphQL query — used for paginated fetches (pages 2+).
# The visitor GraphQL API does not expose client info, so we use SSR state
# extraction (see _extract_ssr_jobs) for the first page which does carry
# whatever client fields the SSR server includes.
# ---------------------------------------------------------------------------
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
              contractorTier
            }
          }
        }
      }
    }
  }
}
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_experience_level(raw: str) -> str:
    """Normalise experience level strings from both SSR tierText and GraphQL contractorTier."""
    if not raw:
        return "N/A"
    lower = raw.lower()
    if "expert" in lower:
        return "Expert"
    if "intermediate" in lower or "mid" in lower:
        return "Intermediate"
    if "entry" in lower or "basic" in lower:
        return "Entry"
    return raw


def _format_client_spent(spent: dict | None) -> str:
    if not spent or not spent.get("amount"):
        return ""
    amt = float(spent["amount"])
    if amt >= 1_000_000:
        return f"${amt / 1_000_000:.1f}M+"
    if amt >= 1_000:
        return f"${amt / 1_000:.0f}K+"
    return f"${amt:.0f}"


class UpworkScraper(BaseScraper):
    """Scrapes Upwork job listings via a hybrid SSR + GraphQL approach.

    Strategy:
      1. Open a real Chrome window via nodriver to bypass Cloudflare.
      2. Extract (a) the visitor OAuth token from cookies and (b) the first
         batch of rich job data from the Nuxt SSR state
         (``window.__NUXT__.state.jobsSearch.jobs``).  The SSR data includes
         client fields (country, payment status, total spent, review score)
         that are absent from the external visitor GraphQL API.
      3. For pages beyond the first, use curl_cffi with TLS fingerprint
         impersonation to call the GraphQL endpoint.

    Note on client data:
      Client info (country, total spent, stars) is only populated when the
      client has not enabled financial privacy.  For a logged-out (visitor)
      session the fields are often ``null``; they are captured when available.

    Requires a running X display (i.e. a normal desktop session).
    """

    SOURCE = "upwork"
    _SSR_PAGE_SIZE = 10   # Nuxt SSR loads 10 jobs per page

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
        cookies, user_agent, ssr_jobs = await self._get_session(search_url)
        raw_jobs = self._collect_raw(
            cookies, user_agent, ssr_jobs, query, search_url, count, days
        )
        return [self._to_listing(job) for job in raw_jobs]

    async def scrape_many(
        self, queries: list[str], count: int, days: int | None
    ) -> dict[str, list[JobListing]]:
        """Scrape multiple queries, opening one browser session per query.

        Each query navigates the browser to its own search URL so the SSR
        state for that specific query is captured.  Subsequent pages for each
        query are fetched concurrently via the GraphQL API (reusing cookies
        from the last browser session).

        Returns:
            Mapping of ``{query: [JobListing, ...]}``, preserving input order.
        """
        if not queries:
            return {}

        results: dict[str, list[JobListing]] = {}
        last_cookies: dict[str, str] = {}
        last_ua: str = ""

        for query in queries:
            search_url = f"https://www.upwork.com/nx/search/jobs/?q={query}&sort=recency"
            cookies, user_agent, ssr_jobs = await self._get_session(search_url)
            last_cookies, last_ua = cookies, user_agent

            raw_jobs = self._collect_raw(
                cookies, user_agent, ssr_jobs, query, search_url, count, days
            )
            results[query] = [self._to_listing(job) for job in raw_jobs]

        return results

    # ------------------------------------------------------------------
    # Private helpers — browser session
    # ------------------------------------------------------------------

    async def _get_session(
        self, search_url: str
    ) -> tuple[dict[str, str], str, list[dict]]:
        """Open Chrome, pass Cloudflare, extract cookies and SSR job data.

        Returns:
            (cookies_dict, user_agent, ssr_jobs_list)
        """
        logger.info("Launching Chrome (%s) ...", self._browser_exec)
        browser = await uc.start(
            browser_executable_path=self._browser_exec,
            headless=False,
        )
        page = await browser.get(search_url)

        logger.info("Waiting for Cloudflare challenge to clear ...")
        for _ in range(30):
            await asyncio.sleep(1)
            title = await page.evaluate("document.title")
            if (
                title
                and "Just a moment" not in str(title)
                and "Challenge" not in str(title)
                and str(title) != ""
            ):
                logger.info("Page ready: %r", title)
                break

        # Extra wait so the Nuxt SSR state is fully populated
        await asyncio.sleep(2)

        raw_cookie: str = await page.evaluate("document.cookie")
        user_agent: str = await page.evaluate("navigator.userAgent")
        ssr_jobs: list[dict] = await self._extract_ssr_jobs(page)

        browser.stop()
        logger.info("Session established — %d SSR job(s) loaded from page state", len(ssr_jobs))

        cookies: dict[str, str] = {}
        for part in raw_cookie.split(";"):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                cookies[k.strip()] = v.strip()

        return cookies, str(user_agent), ssr_jobs

    @staticmethod
    async def _extract_ssr_jobs(page) -> list[dict]:
        """Extract the first batch of jobs from the Nuxt SSR state."""
        raw = await page.evaluate(
            "typeof window.__NUXT__ !== 'undefined' && window.__NUXT__.state.jobsSearch "
            "? JSON.stringify(window.__NUXT__.state.jobsSearch.jobs || []) : '[]'"
        )
        try:
            return json.loads(raw) if raw else []
        except (json.JSONDecodeError, TypeError):
            return []

    # ------------------------------------------------------------------
    # Private helpers — data collection
    # ------------------------------------------------------------------

    def _collect_raw(
        self,
        cookies: dict[str, str],
        user_agent: str,
        ssr_jobs: list[dict],
        query: str,
        search_url: str,
        count: int,
        days: int | None,
    ) -> list[dict]:
        """Collect up to *count* unique jobs, newest first.

        First batch comes from the SSR state (rich data, no GraphQL field
        restrictions).  Additional pages are fetched via the GraphQL API.

        Each SSR dict is tagged with ``"_source": "ssr"``; each GraphQL dict
        is tagged with ``"_source": "graphql"`` so ``_to_listing`` can parse
        them correctly.
        """
        cutoff: datetime | None = None
        if days is not None:
            cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)

        seen_ids: set[str] = set()
        collected: list[dict] = []

        # --- Page 0: SSR state ---
        logger.info("[%s] Processing %d SSR job(s) from page state ...", query, len(ssr_jobs))
        reached_cutoff = False
        for job in ssr_jobs:
            job["_source"] = "ssr"
            job_id = str(job.get("uid") or job.get("ciphertext") or "")
            if not job_id or job_id in seen_ids:
                continue

            if cutoff is not None:
                pub_raw = job.get("publishedOn") or job.get("createdOn") or ""
                if pub_raw:
                    try:
                        pub_dt = datetime.fromisoformat(pub_raw)
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

        logger.info("[%s] After SSR: %d/%d job(s) collected", query, len(collected), count)

        # --- Pages 1+: GraphQL API ---
        offset = 0
        while not reached_cutoff and len(collected) < count:
            logger.info("[%s] Fetching GraphQL page at offset %d ...", query, offset)
            page = self._fetch_graphql_page(cookies, user_agent, query, search_url, offset)
            if not page:
                logger.info("[%s] No more GraphQL results.", query)
                break

            for job in page:
                job["_source"] = "graphql"
                job_id = job.get("id") or (
                    (job.get("jobTile") or {}).get("job", {}).get("ciphertext", "")
                )
                # Skip jobs already captured from SSR (match by stripped cipher)
                cipher = (job.get("jobTile") or {}).get("job", {}).get("ciphertext", "")
                numeric_id = cipher.lstrip("~0") if cipher else job_id
                if job_id in seen_ids or numeric_id in seen_ids:
                    continue

                if cutoff is not None:
                    pub_raw = (
                        (job.get("jobTile") or {}).get("job", {}).get("publishTime", "")
                    )
                    if pub_raw:
                        try:
                            pub_dt = datetime.fromisoformat(pub_raw)
                            if pub_dt.tzinfo is None:
                                pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                            if pub_dt < cutoff:
                                reached_cutoff = True
                                break
                        except ValueError:
                            pass

                seen_ids.add(job_id)
                if numeric_id:
                    seen_ids.add(numeric_id)
                collected.append(job)
                if len(collected) >= count:
                    break

            offset += len(page)
            logger.info("[%s] GraphQL page: %d result(s) — %d/%d collected", query, len(page), len(collected), count)
            if len(page) < self._page_size:
                break

        return collected[:count]

    def _fetch_graphql_page(
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
            logger.warning("Unexpected GraphQL response structure: %s", json.dumps(data, indent=2))
            return []

    # ------------------------------------------------------------------
    # Conversion: raw dict → JobListing
    # ------------------------------------------------------------------

    @staticmethod
    def _to_listing(raw: dict) -> JobListing:
        source = raw.get("_source", "graphql")
        if source == "ssr":
            return UpworkScraper._from_ssr(raw)
        return UpworkScraper._from_graphql(raw)

    @staticmethod
    def _from_ssr(job: dict) -> JobListing:
        """Map a raw SSR state job dict to a JobListing."""
        cipher = job.get("ciphertext", "")
        uid = str(job.get("uid") or cipher)
        job_type_code = job.get("type", 0)
        job_type = "HOURLY" if job_type_code == 1 else "FIXED" if job_type_code == 2 else "N/A"

        # Budget
        if job_type == "HOURLY":
            lo = (job.get("hourlyBudget") or {}).get("min", 0) or 0
            hi = (job.get("hourlyBudget") or {}).get("max", 0) or 0
            budget = f"${lo}-${hi}/hr" if (lo or hi) else "N/A"
        else:
            amt = (job.get("amount") or {}).get("amount", 0) or 0
            budget = f"${amt}" if amt else "N/A"

        # Skills
        attrs = job.get("attrs") or []
        skills = ", ".join(a["prettyName"] for a in attrs[:5] if a.get("prettyName"))

        # Experience level
        exp = _parse_experience_level(job.get("tierText", ""))

        # Client
        client = job.get("client") or {}
        location = client.get("location") or {}
        country = location.get("country") or ""
        pv = client.get("isPaymentVerified")
        payment_verified = "Yes" if pv is True else ("No" if pv is False else "")
        total_spent = _format_client_spent(client.get("totalSpent"))
        feedback = client.get("totalFeedback")
        reviews = client.get("totalReviews")

        desc = (job.get("description") or "").strip()

        return JobListing(
            job_id=uid,
            source=UpworkScraper.SOURCE,
            title=job.get("title", "N/A"),
            job_type=job_type,
            budget=budget,
            publish_time=job.get("publishedOn") or job.get("createdOn") or "N/A",
            url=f"https://www.upwork.com/jobs/{cipher}" if cipher else "N/A",
            description=desc[:500],
            experience_level=exp,
            duration=job.get("durationLabel") or "N/A",
            skills=skills,
            client_country=country,
            client_payment_verified=payment_verified,
            client_total_spent=total_spent,
            client_total_reviews=str(reviews) if reviews is not None else "",
            client_total_feedback=f"{feedback:.2f}" if isinstance(feedback, (int, float)) else "",
        )

    @staticmethod
    def _from_graphql(raw: dict) -> JobListing:
        """Map a raw GraphQL result dict to a JobListing."""
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
        exp = _parse_experience_level(job_info.get("contractorTier", ""))

        desc = (raw.get("description") or "").strip()

        return JobListing(
            job_id=raw.get("id") or cipher,
            source=UpworkScraper.SOURCE,
            title=raw.get("title", "N/A"),
            job_type=job_type,
            budget=budget,
            publish_time=job_info.get("publishTime", "N/A"),
            url=f"https://www.upwork.com/jobs/{cipher}" if cipher else "N/A",
            description=desc[:500],
            experience_level=exp,
            duration="N/A",      # not available in visitor GraphQL API
            skills=extract_skills(desc),
            client_country="",
            client_payment_verified="",
            client_total_spent="",
            client_total_reviews="",
            client_total_feedback="",
        )

