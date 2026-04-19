"""Scraper tab — query form + live log output."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

from nicegui import ui

from ui import shared

# ---------------------------------------------------------------------------
# Mapping from CLI-style strings to LinkedIn filter codes (mirrors main.py)
# ---------------------------------------------------------------------------
_WORKPLACE_MAP = {"on-site": "1", "onsite": "1", "remote": "2", "hybrid": "3"}
_EMPLOYMENT_MAP = {
    "full-time": "F", "part-time": "P", "contract": "C",
    "temporary": "T", "volunteer": "V", "internship": "I",
}
_EXPERIENCE_MAP = {
    "internship": "1", "entry": "2", "associate": "3",
    "mid-senior": "4", "director": "5", "executive": "6",
}


class _UILogHandler(logging.Handler):
    """Sends log records to a NiceGUI log element."""

    def __init__(self, log_element: ui.log) -> None:
        super().__init__()
        self._log = log_element

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._log.push(self.format(record))
        except Exception:
            pass


def build(source_selector: ui.toggle | None = None) -> None:
    """Render the Scraper tab content into the current NiceGUI container."""

    cfg = shared.config

    # ------------------------------------------------------------------ form
    with ui.card().classes("w-full"):
        ui.label("Search Settings").classes("text-lg font-semibold mb-2")

        with ui.row().classes("w-full gap-4 flex-wrap items-end"):
            source_val = ui.select(
                ["upwork", "linkedin"],
                label="Source",
                value="linkedin",
            ).classes("w-40")

            query_input = ui.input(
                label="Queries (comma-separated)",
                placeholder="python, machine learning",
                value=", ".join(
                    cfg.get("linkedin", {}).get("defaults", {}).get("query", ["python"])
                ),
            ).classes("flex-1 min-w-48")

            count_input = ui.number(
                label="Max per query",
                value=cfg.get("linkedin", {}).get("defaults", {}).get("count", 25),
                min=1, max=200, step=5,
            ).classes("w-36")

            days_input = ui.number(
                label="Days (0 = all)",
                value=cfg.get("linkedin", {}).get("defaults", {}).get("days") or 0,
                min=0, max=90, step=1,
            ).classes("w-32")

        # LinkedIn-specific filters (shown/hidden by source)
        with ui.expansion("LinkedIn Filters", icon="tune").classes("w-full") as li_filters:
            with ui.row().classes("w-full gap-4 flex-wrap items-end"):
                location_input = ui.input(
                    label="Location",
                    value=cfg.get("linkedin", {}).get("filters", {}).get("location", ""),
                    placeholder="United States",
                ).classes("w-48")

                workplace_select = ui.select(
                    ["", *_WORKPLACE_MAP.keys()],
                    label="Workplace",
                    value="",
                ).classes("w-40")

                employment_select = ui.select(
                    ["", *_EMPLOYMENT_MAP.keys()],
                    label="Employment type",
                    value="",
                ).classes("w-44")

                experience_select = ui.select(
                    ["", *_EXPERIENCE_MAP.keys()],
                    label="Experience level",
                    value="",
                ).classes("w-44")

        def _toggle_li_filters():
            li_filters.visible = source_val.value == "linkedin"

        source_val.on("update:model-value", lambda _: _toggle_li_filters())
        _toggle_li_filters()

    # ------------------------------------------------------------------ log
    with ui.card().classes("w-full mt-2"):
        ui.label("Live Output").classes("text-lg font-semibold mb-1")
        log = ui.log(max_lines=200).classes("w-full h-64 font-mono text-xs")

    # ------------------------------------------------------------------ run
    run_btn = ui.button("Run Scraper", icon="play_arrow").classes("mt-4 bg-green-600")
    spinner = ui.spinner(size="md").classes("mt-4").bind_visibility_from(
        run_btn, "disable"
    )

    async def _run() -> None:
        run_btn.disable = True
        log.clear()

        source = source_val.value
        queries = [q.strip() for q in query_input.value.split(",") if q.strip()]
        count   = int(count_input.value or 25)
        days    = int(days_input.value or 0) or None

        if not queries:
            ui.notify("Enter at least one query.", type="warning")
            run_btn.disable = False
            return

        # Attach log handler so scraper logger → UI log element
        handler = _UILogHandler(log)
        handler.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)

        try:
            src_cfg: dict = dict(shared.config.get(source, {}))

            if source == "linkedin":
                # Apply UI filter overrides
                filters = dict(src_cfg.get("filters", {}))
                if location_input.value:
                    filters["location"] = location_input.value
                if workplace_select.value:
                    filters["workplace_types"] = [_WORKPLACE_MAP[workplace_select.value]]
                if employment_select.value:
                    filters["employment_types"] = [_EMPLOYMENT_MAP[employment_select.value]]
                if experience_select.value:
                    filters["experience_levels"] = [_EXPERIENCE_MAP[experience_select.value]]
                src_cfg["filters"] = filters
                from web_scraping.linkedin.scraper import LinkedInScraper
                scraper = LinkedInScraper(src_cfg)
            else:
                from web_scraping.upwork.scraper import UpworkScraper
                scraper = UpworkScraper(src_cfg)

            log.push(f"Starting {source} scrape: {queries}")

            total_new = 0
            for query in queries:
                log.push(f"→ [{query}] scraping up to {count} job(s) ...")
                listings = await scraper.scrape(query=query, count=count, days=days)
                # Cache entries
                for listing in listings:
                    shared.storage.cache_put(source, query, listing.job_id, {})
                new_count = shared.storage.save(listings)
                total_new += new_count
                log.push(
                    f"  [{query}]  fetched={len(listings)}  "
                    f"new={new_count}  skipped={len(listings) - new_count}"
                )

            log.push(f"\nDone. Total new records saved: {total_new}")
            ui.notify(f"Scrape complete — {total_new} new record(s) saved.", type="positive")

        except Exception as exc:  # noqa: BLE001
            log.push(f"ERROR: {exc}")
            ui.notify(str(exc), type="negative")
        finally:
            root_logger.removeHandler(handler)
            run_btn.disable = False

    run_btn.on("click", _run)
