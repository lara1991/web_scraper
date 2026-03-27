from abc import ABC, abstractmethod

from web_scraping.models import JobListing


class BaseStorage(ABC):
    """Abstract base class for persisting job listings."""

    @abstractmethod
    def save(self, listings: list[JobListing]) -> int:
        """Persist *listings*, skipping duplicates.

        Returns:
            The number of newly written records.
        """

    @abstractmethod
    def load_ids(self) -> set[str]:
        """Return the set of ``job_id`` values already in storage."""
