"""Unified jobs browser tab — ag-Grid table showing all scraped sources."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from nicegui import ui
from nicegui.elements.aggrid import AgGrid

from ui import shared

# ---------------------------------------------------------------------------
# Cell renderers — key must use ':' prefix so NiceGUI passes them as JS
# ---------------------------------------------------------------------------
_URL_CELL_RENDERER = (
    "(params) => {"
    "  if (!params.value) return '\u2014';"
    "  return '<a href=\"' + params.value + '\" target=\"_blank\" rel=\"noopener noreferrer\"'"
    "    + ' style=\"color:#1565C0;text-decoration:underline;\">Open \u2197</a>';"
    "}"
)

_SOURCE_CELL_RENDERER = (
    "(params) => {"
    "  if (!params.value) return '';"
    "  var colors = {upwork: '#14a800', linkedin: '#0a66c2'};"
    "  var bg = colors[params.value.toLowerCase()] || '#555';"
    "  var label = params.value.charAt(0).toUpperCase() + params.value.slice(1);"
    "  return '<span style=\"background:' + bg + ';color:#fff;padding:2px 8px;"
    "border-radius:10px;font-size:0.78rem;font-weight:600;\">' + label + '</span>';"
    "}"
)


def _col_defs() -> list[dict[str, Any]]:
    """Column definitions for the unified jobs table."""
    base: dict[str, Any] = {"filter": True, "sortable": True, "resizable": True}
    return [
        # Hidden ID — kept in rowData for delete operations
        {**base, "field": "job_id", "headerName": "ID", "hide": True},
        # Platform chip with row-selection checkbox
        {
            **base,
            "field": "source",
            "headerName": "Platform",
            ":cellRenderer": _SOURCE_CELL_RENDERER,
            "checkboxSelection": True,
            "headerCheckboxSelection": True,
            "width": 130,
            "minWidth": 110,
            "maxWidth": 150,
            "pinned": "left",
        },
        {
            **base, "field": "title", "headerName": "Title",
            "flex": 2, "minWidth": 180, "tooltipField": "title",
        },
        {
            **base, "field": "company", "headerName": "Company",
            "flex": 1, "minWidth": 120, "tooltipField": "company",
        },
        {
            **base, "field": "location", "headerName": "Location",
            "flex": 1, "minWidth": 110,
        },
        {
            **base, "field": "employment_type", "headerName": "Type",
            "flex": 1, "minWidth": 100,
        },
        {
            **base, "field": "experience_level", "headerName": "Experience",
            "flex": 1, "minWidth": 120,
        },
        {
            **base,
            "field": "skills",
            "headerName": "Skills",
            "flex": 2,
            "minWidth": 200,
            "tooltipField": "skills",
            "cellStyle": {"overflow": "hidden", "textOverflow": "ellipsis", "whiteSpace": "nowrap"},
        },
        {
            **base, "field": "budget", "headerName": "Budget",
            "flex": 1, "minWidth": 90,
        },
        {
            **base, "field": "publish_time", "headerName": "Published",
            "flex": 1, "minWidth": 100,
        },
        {
            "field": "url",
            "headerName": "URL",
            ":cellRenderer": _URL_CELL_RENDERER,
            "width": 90,
            "minWidth": 90,
            "maxWidth": 90,
            "sortable": False,
            "filter": False,
            "pinned": "right",
        },
    ]


def build() -> None:
    """Render the unified job-browser tab (all sources in one table)."""

    # ── mutable state ──────────────────────────────────────────────────────
    grid_ref: dict[str, AgGrid | None] = {"grid": None}
    active_sources: dict[str, list[str] | None] = {"sources": None}  # None = all

    def _load_rows(sources: list[str] | None = None) -> list[dict]:
        return shared.storage.load_all_combined(sources)

    def _refresh() -> None:
        rows = _load_rows(active_sources["sources"])
        if grid_ref["grid"]:
            grid_ref["grid"].options["rowData"] = rows
            grid_ref["grid"].update()
        count_label.set_text(f"{len(rows)} record(s)")
        ui.notify("Table refreshed.", type="info", timeout=1500)

    # ── toolbar ────────────────────────────────────────────────────────────
    with ui.row().classes("w-full items-center gap-3 mb-2 flex-wrap"):
        ui.label("Jobs").classes("text-xl font-bold flex-1")
        count_label = ui.label("").classes("text-sm text-gray-500")

        source_toggle = ui.toggle(
            {"all": "All", "upwork": "Upwork", "linkedin": "LinkedIn"},
            value="all",
        ).props("dense")

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
                    ui.button(
                        "Delete", icon="delete",
                        on_click=lambda: dlg.submit("ok"),
                    ).props("color=red")
                    ui.button("Cancel", on_click=lambda: dlg.submit("cancel")).props("flat")

            if await dlg != "ok":
                return

            by_source: dict[str, list[str]] = defaultdict(list)
            for r in selected:
                by_source[r["source"]].append(r["job_id"])
            deleted = sum(
                shared.storage.delete_by_ids(src, ids)
                for src, ids in by_source.items()
            )
            ui.notify(f"Deleted {deleted} record(s).", type="positive")
            _refresh()

        ui.button(
            "Delete Selected", icon="delete", on_click=_delete_selected,
        ).props("flat dense color=red")

        async def _clear_all_confirm() -> None:
            scope = active_sources["sources"] or ["upwork", "linkedin"]
            names = " & ".join(s.capitalize() for s in scope)
            with ui.dialog() as dlg, ui.card():
                ui.label(
                    f"Delete ALL {names} jobs? This cannot be undone."
                ).classes("text-base")
                with ui.row():
                    ui.button(
                        "Clear All", icon="delete_forever",
                        on_click=lambda: dlg.submit("ok"),
                    ).props("color=red")
                    ui.button("Cancel", on_click=lambda: dlg.submit("cancel")).props("flat")

            if await dlg == "ok":
                for src in scope:
                    shared.storage.clear_all(src)
                ui.notify(f"All {names} jobs cleared.", type="warning")
                _refresh()

        ui.button(
            "Clear All", icon="delete_sweep", on_click=_clear_all_confirm,
        ).props("flat dense color=red")

    # ── grid ───────────────────────────────────────────────────────────────
    initial_rows = _load_rows()
    count_label.set_text(f"{len(initial_rows)} record(s)")

    grid = ui.aggrid({
        "columnDefs": _col_defs(),
        "rowData": initial_rows,
        "rowSelection": "multiple",
        "suppressRowClickSelection": True,
        "pagination": True,
        "paginationPageSize": 25,
        "tooltipShowDelay": 300,
        "defaultColDef": {
            "filter": True,
            "resizable": True,
            "sortable": True,
        },
        "quickFilterText": "",
    }).classes("w-full").style("height: 560px")

    grid_ref["grid"] = grid

    # Wire quick-search
    def _on_search(e) -> None:
        grid.options["quickFilterText"] = e.value
        grid.update()

    search_input.on("input", _on_search)

    # Wire source filter toggle — read from the element itself, event args vary by version
    def _on_source_change(_) -> None:
        val = source_toggle.value
        active_sources["sources"] = None if val == "all" else [val]
        rows = _load_rows(active_sources["sources"])
        grid.options["rowData"] = rows
        grid.update()
        count_label.set_text(f"{len(rows)} record(s)")

    source_toggle.on("update:model-value", _on_source_change)

    # ── detail panel ───────────────────────────────────────────────────────
    with ui.expansion("Job Detail", icon="info").classes("w-full mt-2") as detail_panel:
        detail_title  = ui.label("").classes("text-base font-semibold")
        detail_meta   = ui.label("").classes("text-xs text-gray-500 mt-1")
        detail_url    = ui.link("Open on platform", target="_blank").classes(
            "text-blue-600 text-sm"
        )
        detail_skills = ui.label("").classes("text-sm text-teal-700 mt-1")
        detail_desc   = ui.label("").classes("text-sm whitespace-pre-wrap mt-2")

    async def _on_row_click(e) -> None:
        row: dict = e.args.get("data", {})
        if not row:
            return
        detail_panel.open()
        detail_title.set_text(row.get("title", ""))
        company  = row.get("company", "") or ""
        location = row.get("location", "") or ""
        source   = row.get("source", "") or ""
        meta_parts = [p for p in [source.capitalize(), company, location] if p]
        detail_meta.set_text(" · ".join(meta_parts))
        url = row.get("url", "")
        detail_url.target = url
        detail_url.text   = url or "—"
        skills = row.get("skills", "") or ""
        detail_skills.set_text(f"Skills: {skills}" if skills else "")
        detail_desc.set_text(row.get("description", "") or "No description.")

    grid.on("rowClicked", _on_row_click)
