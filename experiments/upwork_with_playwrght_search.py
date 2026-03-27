"""
Upwork job search via the internal GraphQL API.

Status of official options (as of March 2026):
- Official GraphQL API : Available, but requires manual application for API keys
                         (up to 2 weeks approval). Apply at:
                         https://www.upwork.com/developer/keys/apply
- RSS Feed             : Dead (HTTP 410 Gone)
- python-upwork library: Archived / deprecated since Aug 2025

How this script works:
  1. Opens a real (non-headless) Chrome window via nodriver to bypass Cloudflare.
  2. Extracts the visitor OAuth token that Upwork sets as a cookie.
  3. Uses curl_cffi (TLS fingerprint impersonation) to call Upwork's internal
     GraphQL endpoint with those cookies — no API key needed.

Requirements: a running X display (e.g. normal desktop session).

Usage:
  uv run experiments/upwork_with_playwrght_search.py [options]

  --query QUERY     Search terms (default: python)
  --count N         Number of results to return, e.g. 10, 25, 50 (default: 10)
  --days N          Only show jobs posted within the last N days (default: all)
"""

import argparse
import asyncio
import json
from datetime import datetime, timedelta, timezone

import nodriver as uc
from curl_cffi import requests as cffi_requests

GRAPHQL_URL = "https://www.upwork.com/api/graphql/v1?alias=visitorJobSearch"
# Maximum results Upwork returns per GraphQL page request.
PAGE_SIZE = 50

GRAPHQL_QUERY = """
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search Upwork jobs via the internal GraphQL API.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--query", "-q", default="python", help="Job search query")
    parser.add_argument(
        "--count", "-n", type=int, default=10,
        help="Number of results to return (e.g. 10, 25, 50)",
    )
    parser.add_argument(
        "--days", "-d", type=int, default=None,
        help="Only show jobs posted within the last N days",
    )
    return parser.parse_args()


async def get_session(search_url: str) -> tuple[dict, str]:
    """Open Chrome, pass Cloudflare, and return (cookies_dict, user_agent)."""
    browser = await uc.start(
        browser_executable_path="/usr/bin/google-chrome-stable",
        headless=False,
    )
    page = await browser.get(search_url)

    # Wait for Cloudflare challenge to resolve (title changes from "Just a moment...")
    for _ in range(20):
        await asyncio.sleep(1)
        title = await page.evaluate("document.title")
        if "Just a moment" not in str(title) and str(title) != "":
            break

    raw_cookie: str = await page.evaluate("document.cookie")
    user_agent: str = await page.evaluate("navigator.userAgent")
    browser.stop()

    cookies = {}
    for part in raw_cookie.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            cookies[k.strip()] = v.strip()

    return cookies, str(user_agent)


def fetch_page(
    cookies: dict,
    user_agent: str,
    query: str,
    search_url: str,
    offset: int,
    page_size: int,
) -> list[dict]:
    """Fetch one page of results from the GraphQL endpoint."""
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
        "query": GRAPHQL_QUERY,
        "variables": {
            "requestVariables": {
                "userQuery": query,
                "sort": "recency",
                "paging": {"offset": offset, "count": page_size},
            }
        },
    }

    session = cffi_requests.Session(impersonate="chrome")
    response = session.post(GRAPHQL_URL, json=payload, headers=headers, cookies=cookies, timeout=15)
    response.raise_for_status()
    data = response.json()

    try:
        return data["data"]["search"]["universalSearchNuxt"]["visitorJobSearchV1"]["results"] or []
    except (KeyError, TypeError):
        print("Unexpected response structure:")
        print(json.dumps(data, indent=2))
        return []


def collect_jobs(
    cookies: dict,
    user_agent: str,
    query: str,
    search_url: str,
    count: int,
    days: int | None,
) -> list[dict]:
    """
    Paginate through the API until we have `count` unique jobs,
    filtering by publish date when `days` is specified.
    Results are already sorted by recency (newest first).
    """
    cutoff: datetime | None = None
    if days is not None:
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)

    seen_ids: set[str] = set()
    collected: list[dict] = []
    offset = 0

    while len(collected) < count:
        page = fetch_page(cookies, user_agent, query, search_url, offset, PAGE_SIZE)

        if not page:
            break  # no more results from API

        reached_cutoff = False
        for job in page:
            job_id = job.get("id") or job.get("jobTile", {}).get("job", {}).get("ciphertext")
            if job_id in seen_ids:
                continue

            if cutoff is not None:
                publish_raw = (job.get("jobTile") or {}).get("job", {}).get("publishTime", "")
                if publish_raw:
                    try:
                        publish_dt = datetime.fromisoformat(publish_raw)
                        if publish_dt.tzinfo is None:
                            publish_dt = publish_dt.replace(tzinfo=timezone.utc)
                        if publish_dt < cutoff:
                            reached_cutoff = True
                            break
                    except ValueError:
                        pass  # unparseable date — include the job anyway

            seen_ids.add(job_id)
            collected.append(job)

            if len(collected) >= count:
                break

        offset += len(page)

        # Stop paginating if we've hit the date boundary or the API has no more results
        if reached_cutoff or len(page) < PAGE_SIZE:
            break

    return collected


def print_jobs(jobs: list[dict]) -> None:
    if not jobs:
        print("No jobs found.")
        return

    for job in jobs:
        job_info = (job.get("jobTile") or {}).get("job") or {}
        job_type = job_info.get("jobType", "N/A")

        if job_type == "HOURLY":
            lo = job_info.get("hourlyBudgetMin", "?")
            hi = job_info.get("hourlyBudgetMax", "?")
            budget = f"${lo}-${hi}/hr"
        else:
            amount = (job_info.get("fixedPriceAmount") or {}).get("amount", "N/A")
            budget = f"${amount}" if amount != "N/A" else "N/A"

        print(f"Title  : {job.get('title', 'N/A')}")
        print(f"Type   : {job_type}  |  Budget: {budget}")
        print(f"Posted : {job_info.get('publishTime', 'N/A')}")
        print(f"Link   : https://www.upwork.com/jobs/{job_info.get('ciphertext', '')}")
        desc = (job.get("description") or "").strip()
        print(f"Desc   : {desc[:200]}{'...' if len(desc) > 200 else ''}")
        print("-" * 60)


async def main() -> None:
    args = parse_args()
    search_url = f"https://www.upwork.com/nx/search/jobs/?q={args.query}&sort=recency"

    date_note = f", last {args.days} day(s)" if args.days else ""
    print(f"Fetching up to {args.count} Upwork jobs for: '{args.query}'{date_note}\n")

    cookies, user_agent = await get_session(search_url)
    jobs = collect_jobs(cookies, user_agent, args.query, search_url, args.count, args.days)

    print(f"Found {len(jobs)} job(s).\n")
    print_jobs(jobs)


if __name__ == "__main__":
    asyncio.run(main())

