"""Entry point for the multi-source job scraper.

Usage
-----
  uv run main.py --source upwork   [--query Q …] [--count N] [--days N]
  uv run main.py --source linkedin [--query Q …] [--count N] [--days N]
                                   [--location LOC] [--workplace remote|hybrid|onsite]
                                   [--employment-type full-time|contract|…]
                                   [--experience-level entry|mid-senior|director]

Examples
--------
  uv run main.py --source upwork --query "python developer" --count 50 --days 7
  uv run main.py --source linkedin --query "python" --count 25 --days 3 \\
                 --location "United States" --workplace remote
"""

import argparse
import asyncio
import logging
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from storage.csv_storage import CsvStorage

console = Console()

_LOG_FORMAT = "%(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=_LOG_FORMAT,
    datefmt="[%X]",
    handlers=[RichHandler(console=console, rich_tracebacks=True, markup=True)],
)
# Quiet down noisy third-party libraries
logging.getLogger("nodriver").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("curl_cffi").setLevel(logging.WARNING)

_CONFIG_PATH = Path(__file__).parent / "src" / "configs" / "scraping_configs.yaml"

# Mapping from CLI string to LinkedIn filter values
_WORKPLACE_MAP = {"on-site": "1", "onsite": "1", "remote": "2", "hybrid": "3"}
_EMPLOYMENT_MAP = {
    "full-time": "F", "part-time": "P", "contract": "C",
    "temporary": "T", "volunteer": "V", "internship": "I", "other": "O",
}
_EXPERIENCE_MAP = {
    "internship": "1", "entry": "2", "associate": "3",
    "mid-senior": "4", "director": "5", "executive": "6",
}


def _load_config() -> dict:
    with _CONFIG_PATH.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _parse_args(source: str, defaults: dict) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=f"Scrape {source} jobs and save to CSV.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    default_queries = defaults.get("query", ["python"])
    if isinstance(default_queries, str):
        default_queries = [default_queries]

    parser.add_argument("--source", "-s", default=source,
                        choices=["upwork", "linkedin"],
                        help="Job board to scrape")
    parser.add_argument("--query", "-q", nargs="+", default=default_queries,
                        metavar="QUERY", help="One or more search queries")
    parser.add_argument("--count", "-n", type=int, default=defaults.get("count", 10),
                        help="Maximum results per query")
    parser.add_argument("--days", "-d", type=int, default=defaults.get("days"),
                        help="Only include jobs posted in the last N days")

    # LinkedIn-specific filters (ignored when --source upwork)
    linkedin_grp = parser.add_argument_group("LinkedIn filters")
    linkedin_grp.add_argument("--location", default=None,
                               help="Location filter, e.g. \"United States\"")
    linkedin_grp.add_argument("--workplace", default=None,
                               choices=list(_WORKPLACE_MAP),
                               help="Workplace type filter")
    linkedin_grp.add_argument("--employment-type", dest="employment_type", default=None,
                               choices=list(_EMPLOYMENT_MAP),
                               help="Employment type filter")
    linkedin_grp.add_argument("--experience-level", dest="experience_level", default=None,
                               choices=list(_EXPERIENCE_MAP),
                               help="Experience level filter")

    return parser.parse_args()


def _apply_linkedin_cli_filters(args: argparse.Namespace, cfg: dict) -> dict:
    """Merge CLI LinkedIn filter overrides into the config dict."""
    filters = dict(cfg.get("filters", {}))
    if args.location:
        filters["location"] = args.location
    if args.workplace:
        filters.setdefault("workplace_types", [])
        code = _WORKPLACE_MAP[args.workplace]
        if code not in filters["workplace_types"]:
            filters["workplace_types"] = [code]
    if args.employment_type:
        code = _EMPLOYMENT_MAP[args.employment_type]
        filters["employment_types"] = [code]
    if args.experience_level:
        code = _EXPERIENCE_MAP[args.experience_level]
        filters["experience_levels"] = [code]
    cfg = dict(cfg)
    cfg["filters"] = filters
    return cfg


async def run() -> None:
    config = _load_config()

    # ---- pre-parse just --source so we know which defaults to load ----
    import sys
    raw_source = "upwork"  # default
    for i, arg in enumerate(sys.argv[1:]):
        if arg in ("--source", "-s") and i + 1 < len(sys.argv) - 1:
            raw_source = sys.argv[i + 2]
            break
        if arg.startswith("--source="):
            raw_source = arg.split("=", 1)[1]
            break
        if arg.startswith("-s="):
            raw_source = arg.split("=", 1)[1]
            break

    src_cfg: dict[str, Any] = config.get(raw_source, {})
    args = _parse_args(raw_source, src_cfg.get("defaults", {}))
    source = args.source

    # ---- build scraper ------------------------------------------------
    if source == "upwork":
        from web_scraping.upwork.scraper import UpworkScraper
        scraper = UpworkScraper(src_cfg)
    else:
        from web_scraping.linkedin.scraper import LinkedInScraper
        src_cfg = _apply_linkedin_cli_filters(args, src_cfg)
        scraper = LinkedInScraper(src_cfg)

    # ---- header -------------------------------------------------------
    queries: list[str] = args.query
    date_note = f", last {args.days} day(s)" if args.days else ""
    console.rule(f"[bold cyan]Web Scraper — {source.capitalize()}[/bold cyan]")
    console.print(
        f"  Queries  : [bold]{', '.join(queries)}[/bold]\n"
        f"  Count    : up to {args.count} per query{date_note}\n"
        f"  Output   : {src_cfg['output_file']}\n"
    )

    # ---- per-query progress bar ---------------------------------------
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}[/bold blue]"),
        BarColumn(),
        MofNCompleteColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    )

    output_path = Path(src_cfg["output_file"])
    storage = CsvStorage(output_path)
    total_fetched = total_new = 0

    with progress:
        overall = progress.add_task("Overall", total=len(queries))

        for query in queries:
            task = progress.add_task(f"[{query}]", total=args.count)

            listings = await scraper.scrape(query=query, count=args.count, days=args.days)

            progress.update(task, completed=len(listings))
            new_count = storage.save(listings)
            skipped = len(listings) - new_count
            total_fetched += len(listings)
            total_new += new_count

            progress.update(overall, advance=1)
            console.log(
                f"[{query}]  fetched=[green]{len(listings)}[/green]  "
                f"new=[cyan]{new_count}[/cyan]  "
                f"skipped=[yellow]{skipped}[/yellow]"
            )

    # ---- summary table ------------------------------------------------
    table = Table(title="Scraping Summary", show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="dim")
    table.add_column("Value", justify="right")
    table.add_row("Total fetched", str(total_fetched))
    table.add_row("New (saved)",   str(total_new))
    table.add_row("Skipped (dup)", str(total_fetched - total_new))
    table.add_row("Output file",   str(output_path))
    console.print(table)


if __name__ == "__main__":
    asyncio.run(run())
