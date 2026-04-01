from abc import ABC, abstractmethod
from typing import Any


class BaseStorage(ABC):
    """Abstract base class for persisting job listings."""

    @abstractmethod
    def save(self, listings: list[Any]) -> int:
        """Persist *listings*, skipping duplicates.

        Returns:
            The number of newly written records.
        """

    @abstractmethod
    def load_ids(self) -> set[str]:
        """Return the set of ``job_id`` values already in storage."""
