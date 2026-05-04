"""NiceGUI desktop application entry point.

Launch with:
    uv run app.py

Opens a native desktop window (no browser, no server URL).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import yaml
from nicegui import app as _app
from nicegui import ui

# ---------------------------------------------------------------------------
# Path setup — allow imports from src/ without installing the package
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).parent
sys.path.insert(0, str(_ROOT / "src"))

# ---------------------------------------------------------------------------
# Shared state (must be set before importing ui modules)
# ---------------------------------------------------------------------------
from ui import shared  # noqa: E402
from storage.sqlite_storage import SqliteStorage  # noqa: E402

_CONFIG_PATH = _ROOT / "src" / "configs" / "scraping_configs.yaml"


def _load_config() -> dict:
    with _CONFIG_PATH.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


shared.config = _load_config()
db_cfg = shared.config.get("database", {})
shared.storage = SqliteStorage(
    _ROOT / db_cfg.get("path", "data/jobs.db"),
    cache_ttl_days=int(db_cfg.get("cache_ttl_days", 2)),
)

# ---------------------------------------------------------------------------
# Logging — route to stdout so NiceGUI doesn't suppress it
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s %(name)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logging.getLogger("nodriver").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("curl_cffi").setLevel(logging.WARNING)
logging.getLogger("nicegui").setLevel(logging.WARNING)

# ---------------------------------------------------------------------------
# UI modules (imported after shared.storage is ready)
# ---------------------------------------------------------------------------
from ui import scraper_tab, jobs_tab, analytics_tab  # noqa: E402


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
@ui.page("/")
def index() -> None:
    ui.query("body").style("background-color: #f5f7fa")

    with ui.header(elevated=True).classes("bg-blue-700 text-white items-center"):
        ui.icon("work").classes("text-2xl mr-2")
        ui.label("Job Board Scraper").classes("text-xl font-bold flex-1")

    with ui.tabs().classes("w-full bg-white shadow") as tabs:
        tab_scraper   = ui.tab("Scraper",   icon="search")
        tab_jobs      = ui.tab("Jobs",      icon="list")
        tab_analytics = ui.tab("Analytics", icon="bar_chart")

    with ui.tab_panels(tabs, value=tab_scraper).classes("w-full p-4"):
        with ui.tab_panel(tab_scraper):
            scraper_tab.build()

        with ui.tab_panel(tab_jobs):
            jobs_tab.build()

        with ui.tab_panel(tab_analytics):
            analytics_tab.build()


# ---------------------------------------------------------------------------
# Run as native desktop window
# ---------------------------------------------------------------------------
ui.run(
    native=True,
    window_size=(1280, 800),
    title="Job Board Scraper",
    reload=False,
)
