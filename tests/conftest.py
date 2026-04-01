"""Shared fixtures used across the test suite."""

import pytest
from datetime import datetime, timezone

from web_scraping.models import JobListing, LinkedInJobListing

# ---------------------------------------------------------------------------
# Fixed timestamps so tests are deterministic
# ---------------------------------------------------------------------------
NOW_ISO  = "2026-03-27T12:00:00+00:00"
NOW_DATE = "2026-03-27"              # date-only form (used by LinkedIn)
OLD_ISO  = "2026-03-20T08:00:00+00:00"   # 7 days before NOW
OLD_DATE = "2026-03-20"


def make_listing(
    job_id: str = "job-001",
    source: str = "upwork",
    title: str = "Python Developer",
    job_type: str = "FIXED",
    budget: str = "$500",
    publish_time: str = NOW_ISO,
    url: str = "https://www.upwork.com/jobs/job-001",
    description: str = "We need a Python developer.",
    experience_level: str = "Expert",
    duration: str = "1 to 3 months",
    skills: str = "Python, Django",
    client_country: str = "United States",
    client_payment_verified: str = "Yes",
    client_total_spent: str = "$5K+",
    client_total_reviews: str = "10",
    client_total_feedback: str = "4.90",
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
        experience_level=experience_level,
        duration=duration,
        skills=skills,
        client_country=client_country,
        client_payment_verified=client_payment_verified,
        client_total_spent=client_total_spent,
        client_total_reviews=client_total_reviews,
        client_total_feedback=client_total_feedback,
    )
    object.__setattr__(listing, "scraped_at", scraped_at)
    return listing


def make_linkedin_listing(
    job_id: str = "li-001",
    source: str = "linkedin",
    title: str = "Python Developer",
    company: str = "TechCorp",
    location: str = "San Francisco, CA",
    workplace_type: str = "Remote",
    employment_type: str = "Full-time",
    experience_level: str = "Mid-Senior level",
    description: str = "We need a Python developer.",
    skills: str = "Software Engineering",
    publish_time: str = NOW_DATE,
    url: str = "https://www.linkedin.com/jobs/view/python-developer-li-001",
    applicant_count: str = "25 applicants",
    scraped_at: str = NOW_ISO,
) -> LinkedInJobListing:
    """Factory for :class:`LinkedInJobListing` with sensible defaults."""
    listing = LinkedInJobListing(
        job_id=job_id,
        source=source,
        title=title,
        company=company,
        location=location,
        workplace_type=workplace_type,
        employment_type=employment_type,
        experience_level=experience_level,
        description=description,
        skills=skills,
        publish_time=publish_time,
        url=url,
        applicant_count=applicant_count,
    )
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
    contractor_tier: str = "ExpertLevel",
) -> dict:
    """Factory for a raw GraphQL job dict (as returned by the Upwork API)."""
    return {
        "_source": "graphql",
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
                "contractorTier": contractor_tier,
            }
        },
    }


def make_ssr_job(
    uid: str = "ssr-001",
    *,
    title: str = "SSR Django Dev",
    job_type_code: int = 2,          # 2 = FIXED, 1 = HOURLY
    amount: float = 300.0,
    hourly_min: float = 0,
    hourly_max: float = 0,
    publish_time: str = NOW_ISO,
    tier_text: str = "jsn_Expert_207",
    duration_label: str = "1 to 3 months",
    skills: list[str] | None = None,
    client_country: str | None = "United States",
    client_payment_verified: bool = True,
    client_total_spent: float | None = 5000.0,
    client_total_feedback: float | None = 4.9,
    client_total_reviews: int | None = 10,
) -> dict:
    """Factory for a raw Nuxt SSR state job dict."""
    skills = ["Python", "Django"] if skills is None else skills
    return {
        "_source": "ssr",
        "uid": uid,
        "ciphertext": f"~02{uid}",
        "title": title,
        "description": f"SSR description for {title}",
        "publishedOn": publish_time,
        "createdOn": publish_time,
        "type": job_type_code,
        "hourlyBudget": {"min": hourly_min, "max": hourly_max},
        "amount": {"amount": amount},
        "durationLabel": duration_label,
        "tierText": tier_text,
        "attrs": [{"prettyName": s, "highlighted": i == 0} for i, s in enumerate(skills)],
        "client": {
            "location": {"country": client_country},
            "isPaymentVerified": client_payment_verified,
            "totalSpent": {"amount": client_total_spent} if client_total_spent is not None else None,
            "totalFeedback": client_total_feedback,
            "totalReviews": client_total_reviews,
            "hasFinancialPrivacy": False,
        },
    }


def make_raw_li_job(
    job_id: str = "li-raw-001",
    *,
    title: str = "Python Developer",
    company: str = "TechCorp",
    location: str = "San Francisco, CA",
    publish_time: str = NOW_DATE,
    url: str = "",
    description: str = "We need a Python developer.",
    experience_level: str = "Mid-Senior level",
    employment_type: str = "Full-time",
    workplace_type: str = "Remote",
    skills: str = "Software Engineering",
    applicant_count: str = "25 applicants",
) -> dict:
    """Factory for a raw LinkedIn job dict (as parsed from HTML)."""
    return {
        "job_id":         job_id,
        "title":          title,
        "company":        company,
        "location":       location,
        "publish_time":   publish_time,
        "url":            url or f"https://www.linkedin.com/jobs/view/{job_id}",
        "description":    description,
        "experience_level": experience_level,
        "employment_type":  employment_type,
        "workplace_type":   workplace_type,
        "skills":           skills,
        "applicant_count":  applicant_count,
    }


# ---------------------------------------------------------------------------
# Standard configs matching scraping_configs.yaml
# ---------------------------------------------------------------------------
UPWORK_CONFIG = {
    "browser_executable": "/usr/bin/google-chrome-stable",
    "graphql_url": "https://www.upwork.com/api/graphql/v1?alias=visitorJobSearch",
    "page_size": 50,
    "output_file": "data/web_scraping_results/upwork_scraping_results.csv",
    "defaults": {"query": "python", "count": 10, "days": None},
}

LINKEDIN_CONFIG = {
    "request_delay": 0.0,    # no delay in tests
    "detail_delay":  0.0,
    "fetch_details": False,  # skip detail requests by default in tests
    "output_file":   "data/web_scraping_results/linkedin_scraping_results.csv",
    "filters": {},
    "defaults": {"query": ["python developer"], "count": 10, "days": None},
}


@pytest.fixture()
def upwork_config() -> dict:
    return UPWORK_CONFIG.copy()


@pytest.fixture()
def linkedin_config() -> dict:
    return LINKEDIN_CONFIG.copy()


@pytest.fixture()
def sample_listing() -> JobListing:
    return make_listing()


@pytest.fixture()
def sample_listings() -> list[JobListing]:
    return [
        make_listing(job_id=f"job-{i:03d}", title=f"Job {i}")
        for i in range(1, 6)
    ]


@pytest.fixture()
def sample_linkedin_listings() -> list[LinkedInJobListing]:
    return [
        make_linkedin_listing(job_id=f"li-{i:03d}", title=f"LinkedIn Job {i}")
        for i in range(1, 6)
    ]



def make_listing(
    job_id: str = "job-001",
    source: str = "upwork",
    title: str = "Python Developer",
    job_type: str = "FIXED",
    budget: str = "$500",
    publish_time: str = NOW_ISO,
    url: str = "https://www.upwork.com/jobs/job-001",
    description: str = "We need a Python developer.",
    experience_level: str = "Expert",
    duration: str = "1 to 3 months",
    skills: str = "Python, Django",
    client_country: str = "United States",
    client_payment_verified: str = "Yes",
    client_total_spent: str = "$5K+",
    client_total_reviews: str = "10",
    client_total_feedback: str = "4.90",
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
        experience_level=experience_level,
        duration=duration,
        skills=skills,
        client_country=client_country,
        client_payment_verified=client_payment_verified,
        client_total_spent=client_total_spent,
        client_total_reviews=client_total_reviews,
        client_total_feedback=client_total_feedback,
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
    contractor_tier: str = "ExpertLevel",
) -> dict:
    """Factory for a raw GraphQL job dict (as returned by the Upwork API)."""
    return {
        "_source": "graphql",
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
                "contractorTier": contractor_tier,
            }
        },
    }


def make_ssr_job(
    uid: str = "ssr-001",
    *,
    title: str = "SSR Django Dev",
    job_type_code: int = 2,          # 2 = FIXED, 1 = HOURLY
    amount: float = 300.0,
    hourly_min: float = 0,
    hourly_max: float = 0,
    publish_time: str = NOW_ISO,
    tier_text: str = "jsn_Expert_207",
    duration_label: str = "1 to 3 months",
    skills: list[str] | None = None,
    client_country: str | None = "United States",
    client_payment_verified: bool = True,
    client_total_spent: float | None = 5000.0,
    client_total_feedback: float | None = 4.9,
    client_total_reviews: int | None = 10,
) -> dict:
    """Factory for a raw Nuxt SSR state job dict."""
    skills = ["Python", "Django"] if skills is None else skills
    return {
        "_source": "ssr",
        "uid": uid,
        "ciphertext": f"~02{uid}",
        "title": title,
        "description": f"SSR description for {title}",
        "publishedOn": publish_time,
        "createdOn": publish_time,
        "type": job_type_code,
        "hourlyBudget": {"min": hourly_min, "max": hourly_max},
        "amount": {"amount": amount},
        "durationLabel": duration_label,
        "tierText": tier_text,
        "attrs": [{"prettyName": s, "highlighted": i == 0} for i, s in enumerate(skills)],
        "client": {
            "location": {"country": client_country},
            "isPaymentVerified": client_payment_verified,
            "totalSpent": {"amount": client_total_spent} if client_total_spent is not None else None,
            "totalFeedback": client_total_feedback,
            "totalReviews": client_total_reviews,
            "hasFinancialPrivacy": False,
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

