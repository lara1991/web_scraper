from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class JobListing:
    """Represents a single scraped Upwork job listing."""

    # ---- core job fields ----
    job_id: str
    source: str
    title: str
    job_type: str
    budget: str
    publish_time: str
    url: str
    description: str
    experience_level: str          # Expert / Intermediate / Entry / N/A
    duration: str                  # e.g. "1 to 3 months" / N/A
    skills: str                    # comma-separated top-5 skill names

    # ---- client / buyer fields ----
    # These are only populated when the client's profile is public.
    # Visitor (unauthenticated) sessions return null for most clients.
    client_country: str            # e.g. "United States" or ""
    client_payment_verified: str   # "Yes" / "No" / ""
    client_total_spent: str        # e.g. "$5,000+" or ""
    client_total_reviews: str      # number of reviews or ""
    client_total_feedback: str     # average star rating, e.g. "4.90" or ""

    scraped_at: str = field(
        default_factory=lambda: datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
    )


@dataclass
class LinkedInJobListing:
    """Represents a single scraped LinkedIn job listing."""

    job_id: str
    source: str
    title: str
    company: str             # hiring company name
    location: str            # city / state / country
    workplace_type: str      # Remote / Hybrid / On-site
    employment_type: str     # Full-time / Part-time / Contract / Temporary / etc.
    experience_level: str    # Entry level / Mid-Senior level / Director / etc.
    description: str
    skills: str              # job function or extracted keywords
    publish_time: str        # ISO date string e.g. "2026-03-30"
    url: str
    applicant_count: str     # e.g. "Over 200 applicants" or ""

    scraped_at: str = field(
        default_factory=lambda: datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
    )
