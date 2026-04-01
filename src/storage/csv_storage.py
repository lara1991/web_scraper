import csv
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any

from storage.base_storage import BaseStorage

_DEDUP_KEY: str = "job_id"


class CsvStorage(BaseStorage):
    """Append-only CSV store for any job listing dataclass.

    - Column headers are derived dynamically from the dataclass fields of the
      first listing written; subsequent writes must use the same schema.
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

    def save(self, listings: list[Any]) -> int:
        existing_ids = self.load_ids()
        new_listings = [listing for listing in listings if listing.job_id not in existing_ids]

        if not new_listings:
            return 0

        # Derive column order from the actual dataclass type being written
        columns = [f.name for f in fields(type(new_listings[0]))]

        self._path.parent.mkdir(parents=True, exist_ok=True)
        needs_header = not self._path.exists() or self._path.stat().st_size == 0

        with self._path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=columns)
            if needs_header:
                writer.writeheader()
            for listing in new_listings:
                writer.writerow(asdict(listing))

        return len(new_listings)
