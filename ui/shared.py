"""Shared application state accessible from all UI modules."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from storage.sqlite_storage import SqliteStorage

_CONFIG_PATH = Path(__file__).parent.parent / "src" / "configs" / "scraping_configs.yaml"


def load_config() -> dict[str, Any]:
    with _CONFIG_PATH.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# Initialised once in app.py and imported here so all tabs share the same DB handle.
storage: SqliteStorage | None = None
config: dict[str, Any] = {}
