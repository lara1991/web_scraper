"""Tests for storage.csv_storage.CsvStorage."""

import csv
from dataclasses import fields
from pathlib import Path

import pytest

from storage.csv_storage import CsvStorage
from web_scraping.models import JobListing
from tests.conftest import make_listing, NOW_ISO

EXPECTED_COLUMNS = [f.name for f in fields(JobListing)]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# ---------------------------------------------------------------------------
# load_ids
# ---------------------------------------------------------------------------

class TestLoadIds:
    def test_returns_empty_set_when_file_missing(self, tmp_path):
        storage = CsvStorage(tmp_path / "missing.csv")
        assert storage.load_ids() == set()

    def test_returns_empty_set_for_empty_file(self, tmp_path):
        empty = tmp_path / "empty.csv"
        empty.touch()
        storage = CsvStorage(empty)
        assert storage.load_ids() == set()

    def test_returns_existing_ids(self, tmp_path):
        path = tmp_path / "results.csv"
        storage = CsvStorage(path)
        storage.save([make_listing(job_id="id-1"), make_listing(job_id="id-2")])
        assert storage.load_ids() == {"id-1", "id-2"}


# ---------------------------------------------------------------------------
# save – first write
# ---------------------------------------------------------------------------

class TestSaveFirstWrite:
    def test_creates_file_with_header(self, tmp_path):
        path = tmp_path / "results.csv"
        storage = CsvStorage(path)
        storage.save([make_listing()])
        assert path.exists()
        rows = read_csv(path)
        assert list(rows[0].keys()) == EXPECTED_COLUMNS

    def test_creates_parent_directories(self, tmp_path):
        path = tmp_path / "a" / "b" / "c" / "results.csv"
        CsvStorage(path).save([make_listing()])
        assert path.exists()

    def test_returns_count_of_written_records(self, tmp_path, sample_listings):
        storage = CsvStorage(tmp_path / "results.csv")
        written = storage.save(sample_listings)
        assert written == len(sample_listings)

    def test_writes_all_field_values(self, tmp_path):
        listing = make_listing(
            job_id="chk-001",
            source="upwork",
            title="Check Title",
            job_type="HOURLY",
            budget="$20-$40/hr",
            publish_time=NOW_ISO,
            url="https://www.upwork.com/jobs/chk-001",
            description="Check description",
            scraped_at=NOW_ISO,
        )
        path = tmp_path / "results.csv"
        CsvStorage(path).save([listing])
        row = read_csv(path)[0]
        assert row["job_id"] == "chk-001"
        assert row["source"] == "upwork"
        assert row["title"] == "Check Title"
        assert row["job_type"] == "HOURLY"
        assert row["budget"] == "$20-$40/hr"
        assert row["publish_time"] == NOW_ISO
        assert row["url"] == "https://www.upwork.com/jobs/chk-001"
        assert row["description"] == "Check description"
        assert row["scraped_at"] == NOW_ISO


# ---------------------------------------------------------------------------
# save – deduplication
# ---------------------------------------------------------------------------

class TestSaveDeduplication:
    def test_returns_zero_when_all_duplicates(self, tmp_path, sample_listings):
        path = tmp_path / "results.csv"
        storage = CsvStorage(path)
        storage.save(sample_listings)
        written = storage.save(sample_listings)
        assert written == 0

    def test_does_not_append_duplicate_rows(self, tmp_path, sample_listings):
        path = tmp_path / "results.csv"
        storage = CsvStorage(path)
        storage.save(sample_listings)
        storage.save(sample_listings)
        rows = read_csv(path)
        assert len(rows) == len(sample_listings)

    def test_writes_only_new_records_in_mixed_batch(self, tmp_path, sample_listings):
        path = tmp_path / "results.csv"
        storage = CsvStorage(path)
        storage.save(sample_listings[:3])

        new_listing = make_listing(job_id="brand-new")
        # Mix 2 existing + 1 new
        written = storage.save([sample_listings[0], sample_listings[1], new_listing])
        assert written == 1
        rows = read_csv(path)
        assert len(rows) == 4  # 3 original + 1 new
        assert rows[-1]["job_id"] == "brand-new"

    def test_dedup_across_multiple_runs(self, tmp_path):
        path = tmp_path / "results.csv"
        storage = CsvStorage(path)
        for i in range(5):
            # Simulate 5 independent runs each adding 1 new + 1 duplicate
            storage.save([make_listing(job_id=f"job-{i}")])
            storage.save([make_listing(job_id=f"job-{i}")])  # duplicate
        rows = read_csv(path)
        assert len(rows) == 5

    def test_header_written_exactly_once(self, tmp_path, sample_listings):
        path = tmp_path / "results.csv"
        storage = CsvStorage(path)
        storage.save(sample_listings[:2])
        storage.save([make_listing(job_id="extra")])
        lines = path.read_text(encoding="utf-8").splitlines()
        header_lines = [l for l in lines if l.startswith("job_id")]
        assert len(header_lines) == 1


# ---------------------------------------------------------------------------
# save – edge cases
# ---------------------------------------------------------------------------

class TestSaveEdgeCases:
    def test_save_empty_list_returns_zero(self, tmp_path):
        storage = CsvStorage(tmp_path / "results.csv")
        assert storage.save([]) == 0

    def test_save_empty_list_does_not_create_file(self, tmp_path):
        path = tmp_path / "results.csv"
        CsvStorage(path).save([])
        assert not path.exists()

    def test_description_with_commas_and_quotes(self, tmp_path):
        listing = make_listing(
            job_id="q-001",
            description='Need "Python", Django, and REST APIs.',
        )
        path = tmp_path / "results.csv"
        CsvStorage(path).save([listing])
        row = read_csv(path)[0]
        assert row["description"] == 'Need "Python", Django, and REST APIs.'

    def test_description_with_newlines(self, tmp_path):
        listing = make_listing(job_id="nl-001", description="Line1\nLine2\nLine3")
        path = tmp_path / "results.csv"
        CsvStorage(path).save([listing])
        row = read_csv(path)[0]
        assert "Line1" in row["description"]
