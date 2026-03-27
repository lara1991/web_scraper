import csv
from dataclasses import asdict, fields
from pathlib import Path

from storage.base_storage import BaseStorage
from web_scraping.models import JobListing

_COLUMNS: list[str] = [f.name for f in fields(JobListing)]
_DEDUP_KEY: str = "job_id"


class CsvStorage(BaseStorage):
    """Append-only CSV store for :class:`~web_scraping.models.JobListing`.

    - Column headers are written automatically on first write.
    - Deduplication is performed on ``job_id`` before every write.
    """

    def __init__(self, file_path: str | Path) -> None:
        self._path = Path(file_path)

    # ------------------------------------------------------------------
    # BaseStorage interface
    # ------------------------------------------------------------------

    def load_ids(self) -> set[str]:
        if not self._path.exists() or self._path.stat().st_size == 0:
            return set()
        with self._path.open(newline="", encoding="utf-8") as fh:
            return {row[_DEDUP_KEY] for row in csv.DictReader(fh) if row.get(_DEDUP_KEY)}

    def save(self, listings: list[JobListing]) -> int:
        existing_ids = self.load_ids()
        new_listings = [listing for listing in listings if listing.job_id not in existing_ids]

        if not new_listings:
            return 0

        self._path.parent.mkdir(parents=True, exist_ok=True)
        needs_header = not self._path.exists() or self._path.stat().st_size == 0

        with self._path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=_COLUMNS)
            if needs_header:
                writer.writeheader()
            for listing in new_listings:
                writer.writerow(asdict(listing))

        return len(new_listings)
