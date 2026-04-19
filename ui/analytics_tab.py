"""Analytics dashboard tab — Plotly charts over the SQLite data."""

from __future__ import annotations

from collections import Counter

import pandas as pd
import plotly.express as px
from nicegui import ui

from ui import shared


def _load_df(source: str) -> pd.DataFrame:
    rows = shared.storage.load_all(source)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def build() -> None:
    """Render the analytics tab content."""

    with ui.row().classes("w-full items-center gap-3 mb-4"):
        ui.label("Analytics Dashboard").classes("text-xl font-bold flex-1")
        source_sel = ui.select(["upwork", "linkedin"], label="Source", value="linkedin").classes("w-40")
        ui.button("Refresh", icon="refresh", on_click=lambda: _refresh()).props("flat dense")

    charts_container = ui.column().classes("w-full gap-6")

    def _refresh() -> None:
        charts_container.clear()
        source = source_sel.value
        df = _load_df(source)

        with charts_container:
            if df.empty:
                ui.label(
                    f"No {source} data yet. Run the scraper first."
                ).classes("text-gray-500 text-base mt-8")
                return

            _jobs_over_time(df, source)
            _top_skills(df, source)
            _experience_breakdown(df, source)
            if source == "upwork":
                _job_type_split(df)
            else:
                _workplace_breakdown(df)
                _employment_type_breakdown(df)
            if source == "linkedin":
                _top_locations(df)
            else:
                _top_client_countries(df)

    source_sel.on("update:model-value", lambda _: _refresh())
    _refresh()


# ---------------------------------------------------------------------------
# Individual chart builders
# ---------------------------------------------------------------------------

def _jobs_over_time(df: pd.DataFrame, source: str) -> None:
    col = "scraped_at"
    if col not in df.columns:
        return
    tmp = df.copy()
    tmp["date"] = pd.to_datetime(tmp[col], errors="coerce").dt.date
    counts = tmp.groupby("date").size().reset_index(name="count")
    if counts.empty:
        return
    fig = px.line(
        counts, x="date", y="count",
        title="Jobs Scraped Over Time",
        labels={"date": "Date", "count": "Jobs"},
        markers=True,
    )
    fig.update_layout(margin=dict(l=20, r=20, t=40, b=20))
    with ui.card().classes("w-full"):
        ui.plotly(fig).classes("w-full")


def _top_skills(df: pd.DataFrame, source: str) -> None:
    if "skills" not in df.columns:
        return
    skill_counts: Counter = Counter()
    for val in df["skills"].dropna():
        for s in str(val).split(","):
            s = s.strip()
            if s:
                skill_counts[s] += 1
    if not skill_counts:
        return
    top = dict(skill_counts.most_common(15))
    fig = px.bar(
        x=list(top.values()), y=list(top.keys()),
        orientation="h",
        title="Top 15 Skills",
        labels={"x": "Count", "y": "Skill"},
    )
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, margin=dict(l=20, r=20, t=40, b=20))
    with ui.card().classes("w-full"):
        ui.plotly(fig).classes("w-full")


def _experience_breakdown(df: pd.DataFrame, source: str) -> None:
    if "experience_level" not in df.columns:
        return
    counts = df["experience_level"].replace("", "N/A").fillna("N/A").value_counts().reset_index()
    counts.columns = ["level", "count"]
    fig = px.pie(
        counts, names="level", values="count",
        title="Experience Level Breakdown",
        hole=0.35,
    )
    fig.update_layout(margin=dict(l=20, r=20, t=40, b=20))
    with ui.card().classes("w-full"):
        ui.plotly(fig).classes("w-full")


def _job_type_split(df: pd.DataFrame) -> None:
    if "job_type" not in df.columns:
        return
    counts = df["job_type"].fillna("N/A").value_counts().reset_index()
    counts.columns = ["type", "count"]
    fig = px.pie(counts, names="type", values="count", title="Job Type (Fixed vs Hourly)", hole=0.35)
    fig.update_layout(margin=dict(l=20, r=20, t=40, b=20))
    with ui.card().classes("w-full"):
        ui.plotly(fig).classes("w-full")


def _workplace_breakdown(df: pd.DataFrame) -> None:
    if "workplace_type" not in df.columns:
        return
    counts = df["workplace_type"].replace("", "N/A").fillna("N/A").value_counts().reset_index()
    counts.columns = ["type", "count"]
    fig = px.bar(counts, x="type", y="count", title="Workplace Type", labels={"type": "", "count": "Count"})
    fig.update_layout(margin=dict(l=20, r=20, t=40, b=20))
    with ui.card().classes("w-full"):
        ui.plotly(fig).classes("w-full")


def _employment_type_breakdown(df: pd.DataFrame) -> None:
    if "employment_type" not in df.columns:
        return
    counts = df["employment_type"].replace("", "N/A").fillna("N/A").value_counts().reset_index()
    counts.columns = ["type", "count"]
    fig = px.bar(counts, x="type", y="count", title="Employment Type", labels={"type": "", "count": "Count"})
    fig.update_layout(margin=dict(l=20, r=20, t=40, b=20))
    with ui.card().classes("w-full"):
        ui.plotly(fig).classes("w-full")


def _top_locations(df: pd.DataFrame) -> None:
    if "location" not in df.columns:
        return
    counts = df["location"].replace("", "N/A").fillna("N/A").value_counts().head(15).reset_index()
    counts.columns = ["location", "count"]
    fig = px.bar(
        counts, x="count", y="location", orientation="h",
        title="Top 15 Locations",
        labels={"count": "Count", "location": ""},
    )
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, margin=dict(l=20, r=20, t=40, b=20))
    with ui.card().classes("w-full"):
        ui.plotly(fig).classes("w-full")


def _top_client_countries(df: pd.DataFrame) -> None:
    if "client_country" not in df.columns:
        return
    counts = df["client_country"].replace("", "N/A").fillna("N/A").value_counts().head(15).reset_index()
    counts.columns = ["country", "count"]
    fig = px.bar(
        counts, x="count", y="country", orientation="h",
        title="Top 15 Client Countries",
        labels={"count": "Count", "country": ""},
    )
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, margin=dict(l=20, r=20, t=40, b=20))
    with ui.card().classes("w-full"):
        ui.plotly(fig).classes("w-full")
