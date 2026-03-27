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
    default_queries = defaults.get("query", ["python"])
    if isinstance(default_queries, str):
        default_queries = [default_queries]
    parser.add_argument(
        "--query", "-q",
        nargs="+",
        default=default_queries,
        metavar="QUERY",
        help="One or more search queries (space-separated)",
    )
    parser.add_argument(
        "--count", "-n",
        type=int,
        default=defaults.get("count", 10),
        help="Maximum number of results per query",
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

    queries: list[str] = args.query
    date_note = f", last {args.days} day(s)" if args.days else ""
    print(
        f"Fetching up to {args.count} job(s) per query{date_note}\n"
        f"Queries  : {', '.join(queries)}\n"
    )

    scraper = UpworkScraper(upwork_cfg)
    listings_by_query = await scraper.scrape_many(
        queries=queries, count=args.count, days=args.days
    )

    output_path = Path(upwork_cfg["output_file"])
    storage = CsvStorage(output_path)

    total_fetched = total_new = 0
    for query, listings in listings_by_query.items():
        new_count = storage.save(listings)
        skipped = len(listings) - new_count
        total_fetched += len(listings)
        total_new += new_count
        print(f"  [{query}]  fetched={len(listings)}  new={new_count}  skipped={skipped}")

    print(f"\nTotal fetched : {total_fetched}")
    print(f"Total new     : {total_new}")
    print(f"Total skipped : {total_fetched - total_new}")
    print(f"Results       : {output_path}")


if __name__ == "__main__":
    asyncio.run(run())
