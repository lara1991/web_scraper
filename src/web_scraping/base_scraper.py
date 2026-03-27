from abc import ABC, abstractmethod
from typing import Any

from web_scraping.models import JobListing


class BaseScraper(ABC):
    """Abstract base class for all job-board scrapers."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config

    @abstractmethod
    async def scrape(self, query: str, count: int, days: int | None) -> list[JobListing]:
        """Scrape jobs matching *query*.

        Args:
            query: Search terms.
            count: Maximum number of unique results to return.
            days:  Only include jobs posted within the last *days* days.
                   ``None`` means no date restriction.

        Returns:
            A list of :class:`JobListing` objects, newest first, without duplicates.
        """
