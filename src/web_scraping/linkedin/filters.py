"""LinkedIn-specific search filters.

Supported URL query parameters
-------------------------------
keywords    : search terms
location    : e.g. "United States", "London, United Kingdom"
f_E         : experience level codes (comma-separated)
f_JT        : employment type codes (comma-separated)
f_WT        : workplace type codes (comma-separated)
f_TPR       : time-posted filter (r86400 = 24 h, r604800 = 7 d, r2592000 = 30 d)
sortBy      : "DD" = most recent, "R" = most relevant
start       : pagination offset (25 per page)

Finding other filter codes
--------------------------
Perform the search on LinkedIn in a browser with the desired filters applied,
then read the corresponding parameter from the URL bar:
  - f_I=<n>  for industry codes
  - geoId=<n> for geography IDs (more precise than ``location`` string)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlencode


class ExperienceLevelFilter(str, Enum):
    """LinkedIn experience level codes."""
    INTERNSHIP = "1"
    ENTRY      = "2"
    ASSOCIATE  = "3"
    MID_SENIOR = "4"
    DIRECTOR   = "5"
    EXECUTIVE  = "6"


class EmploymentTypeFilter(str, Enum):
    """LinkedIn employment type codes."""
    FULL_TIME  = "F"
    PART_TIME  = "P"
    CONTRACT   = "C"
    TEMPORARY  = "T"
    VOLUNTEER  = "V"
    INTERNSHIP = "I"
    OTHER      = "O"


class WorkplaceTypeFilter(str, Enum):
    """LinkedIn workplace / remote type codes."""
    ON_SITE = "1"
    REMOTE  = "2"
    HYBRID  = "3"


class TimeFilter(str, Enum):
    """LinkedIn time-posted filter values."""
    DAY   = "r86400"
    WEEK  = "r604800"
    MONTH = "r2592000"
    ANY   = ""


def days_to_time_filter(days: int) -> TimeFilter:
    """Map a ``--days`` integer to the nearest LinkedIn TimeFilter."""
    if days <= 1:
        return TimeFilter.DAY
    if days <= 7:
        return TimeFilter.WEEK
    return TimeFilter.MONTH


@dataclass
class LinkedInFilters:
    """Optional per-query LinkedIn search filters.

    Attributes:
        location:          Location string, e.g. "United States".
        experience_levels: Seniority filter; multiple values are OR-ed.
        employment_types:  Contract type filter; multiple values are OR-ed.
        workplace_types:   On-site / remote filter; multiple values are OR-ed.
        time_filter:       Restrict to jobs posted within a time window.
                           When ``time_filter`` is set it overrides the
                           ``--days`` CLI argument's server-side filter.
    """

    location: str = ""
    experience_levels: list[ExperienceLevelFilter] = field(default_factory=list)
    employment_types:  list[EmploymentTypeFilter]  = field(default_factory=list)
    workplace_types:   list[WorkplaceTypeFilter]   = field(default_factory=list)
    time_filter: str = ""   # set to a TimeFilter.value when needed

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def to_url_params(self) -> dict[str, str]:
        """Return a dict of URL query parameters that encode these filters."""
        params: dict[str, str] = {}
        if self.location:
            params["location"] = self.location
        if self.experience_levels:
            params["f_E"] = ",".join(e.value for e in self.experience_levels)
        if self.employment_types:
            params["f_JT"] = ",".join(t.value for t in self.employment_types)
        if self.workplace_types:
            params["f_WT"] = ",".join(w.value for w in self.workplace_types)
        if self.time_filter:
            params["f_TPR"] = self.time_filter
        return params

    @classmethod
    def from_config(cls, cfg: dict) -> "LinkedInFilters":
        """Build a :class:`LinkedInFilters` from a config dict (YAML section)."""

        def _parse(enum_cls: type[Enum], value) -> list:
            if not value:
                return []
            items = value if isinstance(value, list) else [v.strip() for v in value.split(",")]
            return [enum_cls(v) for v in items if v]

        return cls(
            location=cfg.get("location", ""),
            experience_levels=_parse(ExperienceLevelFilter, cfg.get("experience_levels")),
            employment_types=_parse(EmploymentTypeFilter,  cfg.get("employment_types")),
            workplace_types=_parse(WorkplaceTypeFilter,    cfg.get("workplace_types")),
            time_filter=cfg.get("time_filter", ""),
        )
