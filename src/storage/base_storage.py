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

    def delete_by_ids(self, source: str, job_ids: list[str]) -> int:
        """Delete specific jobs by id. Returns number of rows deleted.

        Optional — raise NotImplementedError for read-only stores.
        """
        raise NotImplementedError

    def clear_all(self, source: str | None = None) -> None:
        """Delete all records (optionally scoped to one source).

        Optional — raise NotImplementedError for read-only stores.
        """
        raise NotImplementedError
