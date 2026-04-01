"""Tests for web_scraping.models.JobListing."""

from dataclasses import asdict, fields

import pytest

from web_scraping.models import JobListing
from tests.conftest import make_listing, NOW_ISO


class TestJobListingFields:
    """Verify required fields and their order (drives CSV column layout)."""

    EXPECTED_COLUMNS = [
        "job_id", "source", "title", "job_type", "budget", "publish_time",
        "url", "description", "experience_level", "duration", "skills",
        "client_country", "client_payment_verified", "client_total_spent",
        "client_total_reviews", "client_total_feedback", "scraped_at",
    ]

    def test_field_names_and_order(self):
        assert [f.name for f in fields(JobListing)] == self.EXPECTED_COLUMNS

    def test_all_fields_are_strings(self, sample_listing):
        for f in fields(sample_listing):
            value = getattr(sample_listing, f.name)
            assert isinstance(value, str), f"{f.name!r} should be str, got {type(value)}"

    def test_scraped_at_auto_populated(self):
        listing = JobListing(
            job_id="x", source="upwork", title="T", job_type="FIXED",
            budget="$100", publish_time=NOW_ISO, url="https://example.com",
            description="desc", experience_level="Expert",
            duration="1 to 3 months", skills="Python",
            client_country="USA", client_payment_verified="Yes",
            client_total_spent="$1K+", client_total_reviews="5",
            client_total_feedback="4.80",
        )
        assert listing.scraped_at != ""
        from datetime import datetime
        parsed = datetime.fromisoformat(listing.scraped_at)
        assert parsed.tzinfo is not None

    def test_scraped_at_is_unique_across_instances(self):
        import time
        a = JobListing("a", "upwork", "T", "FIXED", "$1", NOW_ISO, "url", "d",
                       "Expert", "N/A", "", "", "", "", "", "")
        time.sleep(0.001)
        b = JobListing("b", "upwork", "T", "FIXED", "$1", NOW_ISO, "url", "d",
                       "Expert", "N/A", "", "", "", "", "", "")
        assert a.scraped_at != "" and b.scraped_at != ""


class TestJobListingConversion:
    def test_asdict_returns_all_columns(self, sample_listing):
        d = asdict(sample_listing)
        assert set(d.keys()) == set(TestJobListingFields.EXPECTED_COLUMNS)

    def test_values_round_trip(self, sample_listing):
        d = asdict(sample_listing)
        assert d["job_id"] == sample_listing.job_id
        assert d["source"] == sample_listing.source
        assert d["client_country"] == sample_listing.client_country
        assert d["client_payment_verified"] == sample_listing.client_payment_verified

    def test_equality(self):
        a = make_listing(job_id="same")
        b = make_listing(job_id="same")
        assert a == b

    def test_inequality_on_different_job_id(self):
        a = make_listing(job_id="aaa")
        b = make_listing(job_id="bbb")
        assert a != b


class TestClientFields:
    def test_client_fields_default_to_empty_string(self):
        listing = make_listing(
            client_country="",
            client_payment_verified="",
            client_total_spent="",
            client_total_reviews="",
            client_total_feedback="",
        )
        assert listing.client_country == ""
        assert listing.client_payment_verified == ""
        assert listing.client_total_spent == ""

    def test_client_fields_populated(self):
        listing = make_listing(
            client_country="Germany",
            client_payment_verified="Yes",
            client_total_spent="$10K+",
            client_total_reviews="25",
            client_total_feedback="4.95",
        )
        assert listing.client_country == "Germany"
        assert listing.client_payment_verified == "Yes"
        assert listing.client_total_spent == "$10K+"
        assert listing.client_total_reviews == "25"
        assert listing.client_total_feedback == "4.95"

