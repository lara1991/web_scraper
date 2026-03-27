from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class JobListing:
    """Represents a single scraped job listing, common across all sources."""

    job_id: str
    source: str
    title: str
    job_type: str
    budget: str
    publish_time: str
    url: str
    description: str
    scraped_at: str = field(
        default_factory=lambda: datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
    )
