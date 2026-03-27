"""Shared fixtures used across the test suite."""

import pytest
from datetime import datetime, timezone

from web_scraping.models import JobListing

# ---------------------------------------------------------------------------
# Fixed timestamps so tests are deterministic
# ---------------------------------------------------------------------------
NOW_ISO = "2026-03-27T12:00:00+00:00"
OLD_ISO = "2026-03-20T08:00:00+00:00"   # 7 days before NOW


def make_listing(
    job_id: str = "job-001",
    source: str = "upwork",
    title: str = "Python Developer",
    job_type: str = "FIXED",
    budget: str = "$500",
    publish_time: str = NOW_ISO,
    url: str = "https://www.upwork.com/jobs/job-001",
    description: str = "We need a Python developer.",
    scraped_at: str = NOW_ISO,
) -> JobListing:
    """Factory for :class:`JobListing` with sensible defaults."""
    listing = JobListing(
        job_id=job_id,
        source=source,
        title=title,
        job_type=job_type,
        budget=budget,
        publish_time=publish_time,
        url=url,
        description=description,
    )
    # Override the auto-generated scraped_at for deterministic tests
    object.__setattr__(listing, "scraped_at", scraped_at)
    return listing


def make_raw_job(
    job_id: str = "raw-001",
    *,
    title: str = "Django Dev",
    job_type: str = "FIXED",
    amount: float = 200.0,
    publish_time: str = NOW_ISO,
    hourly_min: float | None = None,
    hourly_max: float | None = None,
) -> dict:
    """Factory for a raw GraphQL job dict (as returned by the Upwork API)."""
    return {
        "id": job_id,
        "title": title,
        "description": f"Description for {title}",
        "jobTile": {
            "job": {
                "ciphertext": job_id,
                "jobType": job_type,
                "hourlyBudgetMin": hourly_min,
                "hourlyBudgetMax": hourly_max,
                "fixedPriceAmount": {"amount": amount} if job_type == "FIXED" else None,
                "publishTime": publish_time,
            }
        },
    }


# ---------------------------------------------------------------------------
# Standard config matching scraping_configs.yaml
# ---------------------------------------------------------------------------
UPWORK_CONFIG = {
    "browser_executable": "/usr/bin/google-chrome-stable",
    "graphql_url": "https://www.upwork.com/api/graphql/v1?alias=visitorJobSearch",
    "page_size": 50,
    "output_file": "data/web_scraping_results/upwork_scraping_results.csv",
    "defaults": {"query": "python", "count": 10, "days": None},
}


@pytest.fixture()
def upwork_config() -> dict:
    return UPWORK_CONFIG.copy()


@pytest.fixture()
def sample_listing() -> JobListing:
    return make_listing()


@pytest.fixture()
def sample_listings() -> list[JobListing]:
    return [
        make_listing(job_id=f"job-{i:03d}", title=f"Job {i}")
        for i in range(1, 6)
    ]
