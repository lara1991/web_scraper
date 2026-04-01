from abc import ABC, abstractmethod
from typing import Any


class BaseScraper(ABC):
    """Abstract base class for all job-board scrapers."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config

    @abstractmethod
    async def scrape(self, query: str, count: int, days: int | None) -> list[Any]:
        """Scrape jobs matching *query*.

        Args:
            query: Search terms.
            count: Maximum number of unique results to return.
            days:  Only include jobs posted within the last *days* days.
                   ``None`` means no date restriction.

        Returns:
            A list of job listing dataclass objects, newest first, without duplicates.
        """

    @abstractmethod
    async def scrape_many(
        self, queries: list[str], count: int, days: int | None
    ) -> dict[str, list[Any]]:
        """Scrape *queries* in sequence/parallel.

        Returns:
            Mapping of ``{query: [listing, ...]}``, preserving input order.
        """
