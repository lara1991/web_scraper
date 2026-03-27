"""Entry point for the web scraper.

Usage:
  uv run main.py [--query QUERY] [--count N] [--days N]
"""

import argparse
import asyncio
from pathlib import Path

import yaml

from web_scraping.upwork_scraping import UpworkScraper
from storage.csv_storage import CsvStorage

_CONFIG_PATH = Path(__file__).parent / "src" / "configs" / "scraping_configs.yaml"


def _load_config() -> dict:
    with _CONFIG_PATH.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _parse_args(defaults: dict) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search Upwork jobs and save results to CSV.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--query", "-q",
        default=defaults.get("query", "python"),
        help="Job search query",
    )
    parser.add_argument(
        "--count", "-n",
        type=int,
        default=defaults.get("count", 10),
        help="Maximum number of results to fetch",
    )
    parser.add_argument(
        "--days", "-d",
        type=int,
        default=defaults.get("days"),
        help="Only include jobs posted within the last N days",
    )
    return parser.parse_args()


async def run() -> None:
    config = _load_config()
    upwork_cfg = config["upwork"]
    args = _parse_args(upwork_cfg.get("defaults", {}))

    date_note = f", last {args.days} day(s)" if args.days else ""
    print(f"Fetching up to {args.count} Upwork jobs for: '{args.query}'{date_note}\n")

    scraper = UpworkScraper(upwork_cfg)
    listings = await scraper.scrape(query=args.query, count=args.count, days=args.days)

    output_path = Path(upwork_cfg["output_file"])
    storage = CsvStorage(output_path)
    new_count = storage.save(listings)

    print(f"\nFetched  : {len(listings)} job(s)")
    print(f"New      : {new_count} saved")
    print(f"Skipped  : {len(listings) - new_count} duplicate(s)")
    print(f"Results  : {output_path}")


if __name__ == "__main__":
    asyncio.run(run())
