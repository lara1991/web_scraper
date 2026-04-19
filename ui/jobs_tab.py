"""Jobs browser tab — ag-Grid table with delete, refresh, and search."""

from __future__ import annotations

from typing import Any

import pandas as pd
from nicegui import ui
from nicegui.elements.aggrid import AgGrid

from ui import shared

# Columns that are shown by default in the grid (keep to a reasonable width)
_UPWORK_VISIBLE = [
    "job_id", "title", "job_type", "budget", "experience_level",
    "skills", "client_country", "publish_time", "url",
]
_LINKEDIN_VISIBLE = [
    "job_id", "title", "company", "location", "workplace_type",
    "employment_type", "experience_level", "skills", "publish_time", "url",
]


def _col_defs(columns: list[str], visible_cols: list[str]) -> list[dict]:
    defs = []
    for col in columns:
        d: dict[str, Any] = {
            "field": col,
            "headerName": col.replace("_", " ").title(),
            "filter": True,
            "sortable": True,
            "resizable": True,
            "hide": col not in visible_cols,
        }
        if col in ("description", "url"):
            d["width"] = 260
        elif col == "job_id":
            d["checkboxSelection"] = True
            d["headerCheckboxSelection"] = True
            d["width"] = 160
        else:
            d["width"] = 160
        defs.append(d)
    return defs


def build(source: str) -> None:
    """Render the job-browser tab for *source* ('upwork' or 'linkedin')."""
    visible_cols = _UPWORK_VISIBLE if source == "upwork" else _LINKEDIN_VISIBLE

    # State
    grid_ref: dict[str, AgGrid | None] = {"grid": None}
    rows_ref: dict[str, list[dict]] = {"rows": []}

    def _load_rows() -> list[dict]:
        return shared.storage.load_all(source)

    def _refresh() -> None:
        rows = _load_rows()
        rows_ref["rows"] = rows
        if grid_ref["grid"]:
            grid_ref["grid"].options["rowData"] = rows
            grid_ref["grid"].update()
        count_label.set_text(f"{len(rows)} record(s)")
        ui.notify("Table refreshed.", type="info", timeout=1500)

    # ------------------------------------------------------------------ toolbar
    with ui.row().classes("w-full items-center gap-3 mb-2"):
        ui.label(f"{source.capitalize()} Jobs").classes("text-xl font-bold flex-1")
        count_label = ui.label("").classes("text-sm text-gray-500")
        search_input = ui.input(placeholder="Quick search …").classes("w-56")
        ui.button("Refresh", icon="refresh", on_click=_refresh).props("flat dense")

        async def _delete_selected() -> None:
            if grid_ref["grid"] is None:
                return
            selected: list[dict] = await grid_ref["grid"].get_selected_rows()
            if not selected:
                ui.notify("No rows selected.", type="warning")
                return

            with ui.dialog() as dlg, ui.card():
                ui.label(f"Delete {len(selected)} selected job(s)?").classes("text-base")
                with ui.row():
                    ui.button("Delete", icon="delete", on_click=lambda: dlg.submit("ok")).props("color=red")
                    ui.button("Cancel", on_click=lambda: dlg.submit("cancel")).props("flat")

            result = await dlg
            if result != "ok":
                return

            ids = [r["job_id"] for r in selected]
            deleted = shared.storage.delete_by_ids(source, ids)
            ui.notify(f"Deleted {deleted} record(s).", type="positive")
            _refresh()

        ui.button("Delete Selected", icon="delete", on_click=_delete_selected).props(
            "flat dense color=red"
        )

        def _clear_all_confirm() -> None:
            with ui.dialog() as dlg, ui.card():
                ui.label(f"Delete ALL {source} jobs? This cannot be undone.").classes("text-base")
                with ui.row():
                    ui.button("Clear All", icon="delete_forever", on_click=lambda: dlg.submit("ok")).props("color=red")
                    ui.button("Cancel", on_click=lambda: dlg.submit("cancel")).props("flat")

            async def _run():
                result = await dlg
                if result == "ok":
                    shared.storage.clear_all(source)
                    ui.notify(f"All {source} jobs cleared.", type="warning")
                    _refresh()

            asyncio.ensure_future(_run())

        ui.button("Clear All", icon="delete_sweep", on_click=_clear_all_confirm).props(
            "flat dense color=red"
        )

    # ------------------------------------------------------------------ grid
    initial_rows = _load_rows()
    rows_ref["rows"] = initial_rows
    cols = list(initial_rows[0].keys()) if initial_rows else (
        list(shared.storage.load_all(source)[0].keys())
        if shared.storage.load_all(source) else []
    )
    # Fallback column list from model fields if table empty
    if not cols:
        from dataclasses import fields as dc_fields
        from web_scraping.models import JobListing, LinkedInJobListing
        model = JobListing if source == "upwork" else LinkedInJobListing
        cols = [f.name for f in dc_fields(model)]

    count_label.set_text(f"{len(initial_rows)} record(s)")

    grid = ui.aggrid({
        "columnDefs": _col_defs(cols, visible_cols),
        "rowData": initial_rows,
        "rowSelection": "multiple",
        "suppressRowClickSelection": True,
        "pagination": True,
        "paginationPageSize": 25,
        "defaultColDef": {
            "filter": True,
            "resizable": True,
            "sortable": True,
        },
        "quickFilterText": "",
    }).classes("w-full").style("height: 520px")

    grid_ref["grid"] = grid

    # Wire quick-search to ag-Grid quickFilterText
    def _on_search(e):
        grid.options["quickFilterText"] = e.value
        grid.update()

    search_input.on("input", _on_search)

    # ------------------------------------------------------------------ detail panel
    with ui.expansion("Job Detail", icon="info").classes("w-full mt-2") as detail_panel:
        detail_title    = ui.label("").classes("text-base font-semibold")
        detail_url      = ui.link("Open on platform", target="_blank").classes("text-blue-600 text-sm")
        detail_desc     = ui.label("").classes("text-sm whitespace-pre-wrap mt-2")

    async def _on_row_click(e) -> None:
        row: dict = e.args.get("data", {})
        if not row:
            return
        detail_panel.open()
        detail_title.set_text(row.get("title", ""))
        url = row.get("url", "")
        detail_url.target = url
        detail_url.text = url or "—"
        detail_desc.set_text(row.get("description", "No description."))

    grid.on("rowClicked", _on_row_click)


import asyncio  # noqa: E402 (needed for ensure_future in closure)
