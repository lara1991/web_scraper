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
"""

import asyncio
import json

import nodriver as uc
from curl_cffi import requests as cffi_requests

SEARCH_QUERY = "python"
SEARCH_URL = f"https://www.upwork.com/nx/search/jobs/?q={SEARCH_QUERY}&sort=recency"
GRAPHQL_URL = "https://www.upwork.com/api/graphql/v1?alias=visitorJobSearch"

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


async def get_session() -> tuple[dict, str]:
    """Open Chrome, pass Cloudflare, and return (cookies_dict, user_agent)."""
    browser = await uc.start(
        browser_executable_path="/usr/bin/google-chrome-stable",
        headless=False,
    )
    page = await browser.get(SEARCH_URL)

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


def search_jobs(cookies: dict, user_agent: str) -> dict:
    """Call Upwork's GraphQL endpoint with the extracted visitor session."""
    token = cookies.get("UniversalSearchNuxt_vt", "")

    headers = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "origin": "https://www.upwork.com",
        "referer": SEARCH_URL,
        "user-agent": user_agent,
        "x-requested-with": "XMLHttpRequest",
    }
    if token:
        headers["authorization"] = f"Bearer {token}"

    payload = {
        "query": GRAPHQL_QUERY,
        "variables": {
            "requestVariables": {
                "userQuery": SEARCH_QUERY,
                "sort": "recency",
                "paging": {"offset": 0, "count": 10},
            }
        },
    }

    session = cffi_requests.Session(impersonate="chrome")
    response = session.post(GRAPHQL_URL, json=payload, headers=headers, cookies=cookies, timeout=15)
    response.raise_for_status()
    return response.json()


def print_jobs(data: dict) -> None:
    try:
        results = data["data"]["search"]["universalSearchNuxt"]["visitorJobSearchV1"]["results"]
    except (KeyError, TypeError):
        print("Unexpected response structure:")
        print(json.dumps(data, indent=2))
        return

    if not results:
        print("No jobs found.")
        return

    for job in results:
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


async def main():
    print(f"Fetching Upwork jobs for: '{SEARCH_QUERY}'\n")
    cookies, user_agent = await get_session()
    data = search_jobs(cookies, user_agent)
    print_jobs(data)


if __name__ == "__main__":
    asyncio.run(main())

