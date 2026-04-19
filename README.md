# Web Scraper

A modular, extensible job-board scraper built in Python.  
Currently supports **Upwork** (internal GraphQL API) and **LinkedIn** (public guest API) — no official API keys or login required.

Results are stored in a **SQLite database** (persistent, deduplicated across runs). A **NiceGUI desktop UI** lets you run scrapers, browse saved jobs, delete records, and view analytics charts — all in a native window.

## Table of Contents

- [How It Works](#how-it-works)
- [Project Structure](#project-structure)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Desktop UI](#desktop-ui)
- [CLI Usage](#cli-usage)
  - [Upwork](#upwork-cli)
  - [LinkedIn](#linkedin-cli)
  - [LinkedIn filter reference](#linkedin-filter-reference)
- [Database & Storage](#database--storage)
  - [Job schemas](#job-schemas)
  - [Cache](#cache)
  - [Clearing data](#clearing-data)
- [Running Tests](#running-tests)
- [Adding a New Scraper](#adding-a-new-scraper)
- [Notes & Limitations](#notes--limitations)
- [Future Work](#future-work)
- [License](#license)

---

## How It Works

### Upwork

1. Opens a real (non-headless) Chrome window via **nodriver** to bypass Cloudflare.
2. Extracts the visitor OAuth token that Upwork sets as a session cookie.
3. Uses **curl_cffi** (TLS fingerprint impersonation) to call Upwork's internal GraphQL endpoint with those cookies — no API key needed.
4. Results are deduplicated by `job_id` and inserted into the SQLite database. Re-running never creates duplicate rows.

### LinkedIn

1. Calls LinkedIn's public guest job-search API with **curl_cffi** — no login, no Selenium, no browser.
2. Parses the returned HTML job cards with **BeautifulSoup4**.
3. Optionally fetches each job's detail page for full description, skills, and applicant count.
4. Results are deduplicated by `job_id` and inserted into the SQLite database.

---

## Project Structure

```
web_scraper/
├── main.py                          # CLI entry point (--source upwork|linkedin)
├── app.py                           # NiceGUI desktop UI entry point
├── pyproject.toml
│
├── src/
│   ├── configs/
│   │   └── scraping_configs.yaml    # All configuration (DB path, scrapers, defaults)
│   │
│   ├── web_scraping/
│   │   ├── models.py                # JobListing + LinkedInJobListing dataclasses
│   │   ├── base_scraper.py          # BaseScraper abstract base class
│   │   ├── upwork/
│   │   │   ├── __init__.py
│   │   │   └── scraper.py           # UpworkScraper (hybrid SSR + GraphQL)
│   │   └── linkedin/
│   │       ├── __init__.py
│   │       ├── filters.py           # LinkedInFilters dataclass + filter enums
│   │       └── scraper.py           # LinkedInScraper (guest API + BeautifulSoup4)
│   │
│   └── storage/
│       ├── base_storage.py          # BaseStorage abstract base class
│       ├── csv_storage.py           # CsvStorage — legacy CSV writer (still available)
│       └── sqlite_storage.py        # SqliteStorage — primary store (dedup + cache)
│
├── ui/
│   ├── shared.py                    # Singleton storage + config shared across tabs
│   ├── scraper_tab.py               # Scraper form + live log output
│   ├── jobs_tab.py                  # ag-Grid browser: sort, filter, delete, detail view
│   └── analytics_tab.py             # Plotly charts (skills, experience, locations, …)
│
├── data/
│   └── jobs.db                      # SQLite database (auto-created on first run)
│
├── tests/
│   ├── conftest.py                  # Shared fixtures and factory helpers
│   ├── test_models.py
│   ├── test_csv_storage.py
│   ├── test_sqlite_storage.py       # SqliteStorage — save, dedup, delete, cache tests
│   ├── test_upwork_scraping.py
│   └── test_linkedin_scraping.py
│
└── experiments/
    └── upwork_with_playwrght_search.py   # Standalone prototype (reference only)
```

---

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (package manager)
- Google Chrome installed at `/usr/bin/google-chrome-stable` *(Upwork only)*
- A running X display (standard desktop session) *(Upwork only — required to bypass Cloudflare)*

LinkedIn scraping has no browser or display requirements.

---

## Installation

```bash
git clone <repo-url>
cd web_scraper

# Install all dependencies (including dev tools)
uv sync --group dev
```

---

## Configuration

All settings live in `src/configs/scraping_configs.yaml`:

```yaml
database:
  path: "data/jobs.db"       # SQLite file path (relative to project root)
  cache_ttl_days: 2          # Cached scrape entries are purged after this many days

upwork:
  browser_executable: "/usr/bin/google-chrome-stable"
  graphql_url: "https://www.upwork.com/api/graphql/v1?alias=visitorJobSearch"
  page_size: 50
  defaults:
    query: ["generative ai", "RAG Systems", "Computer Vision"]
    count: 100
    days: null     # null = no date filter

linkedin:
  request_delay: 1.5         # Seconds between paginated search requests
  detail_delay: 0.7          # Seconds between per-job detail fetches
  fetch_details: true        # Set false to skip detail pages (faster, less data)
  filters:
    location: "United States"
    # experience_levels: ["2", "4"]   # "2"=Entry, "4"=Mid-Senior
    # employment_types:  ["F", "C"]   # "F"=Full-time, "C"=Contract
    # workplace_types:   ["2", "3"]   # "2"=Remote, "3"=Hybrid
  defaults:
    query: ["python", "machine learning"]
    count: 50
    days: 7
```

### Database config keys

| Key | Description |
|---|---|
| `database.path` | Path to the SQLite `.db` file (auto-created) |
| `database.cache_ttl_days` | How many days raw scrape cache entries are retained before automatic purge |

### Upwork config keys

| Key | Description |
|---|---|
| `browser_executable` | Path to the Chrome binary |
| `page_size` | Results per GraphQL request (max 50) |
| `defaults.query` | Default search queries (list) |
| `defaults.count` | Default max results per query |
| `defaults.days` | Default date window in days (`null` = no limit) |

### LinkedIn config keys

| Key | Description |
|---|---|
| `request_delay` | Seconds to wait between paginated search requests |
| `detail_delay` | Seconds to wait between per-job detail page fetches |
| `fetch_details` | Whether to fetch full description/criteria per job |
| `filters.location` | Static location filter applied to every search |
| `filters.experience_levels` | Static experience level filter codes |
| `filters.employment_types` | Static employment type filter codes |
| `filters.workplace_types` | Static workplace type filter codes |
| `defaults.query` | Default search queries (list) |
| `defaults.count` | Default max results per query |
| `defaults.days` | Default date window in days (`null` = no limit) |

---

---

## Desktop UI

The desktop app is the primary way to interact with the scraper. It opens a native window (no browser tab needed) and provides four tabs.

```bash
uv run app.py
```

### Tabs

| Tab | Description |
|---|---|
| **Scraper** | Form to configure and run a scrape. Supports all source/filter options. Live log shows progress as scraping happens. |
| **Upwork Jobs** | ag-Grid table of all saved Upwork jobs. Sort, filter, quick-search, click for detail panel. |
| **LinkedIn Jobs** | ag-Grid table of all saved LinkedIn jobs. Same features as Upwork tab. |
| **Analytics** | Plotly charts: jobs over time, top skills, experience level breakdown, workplace/employment type split, top locations/countries. Source selector to switch between Upwork and LinkedIn data. |

### Job management in the UI

- **Delete selected rows** — select one or more rows (checkbox column) then click *Delete Selected*. A confirmation dialog appears before any data is removed.
- **Clear all** — removes every record for the active source. Requires confirmation.
- After either operation, deleted `job_id` values are no longer tracked, so those jobs will be re-inserted if encountered in a future scrape.

---

## CLI Usage

Select the job board with `--source upwork` or `--source linkedin`. All other flags are shared unless noted.

```
uv run main.py --source {upwork,linkedin} [options]
```

### Upwork <a name="upwork-cli"></a>

```bash
# Single query with defaults from YAML
uv run main.py --source upwork --query python

# Multiple queries (run concurrently in a single browser session)
uv run main.py --source upwork --query python django fastapi

# Limit results and apply a date filter
uv run main.py --source upwork --query "machine learning" --count 50 --days 7
```

### LinkedIn <a name="linkedin-cli"></a>

LinkedIn scraping requires no browser and no login. Filter flags are optional.

```bash
# Basic search
uv run main.py --source linkedin --query "python developer"

# Multiple queries with result limit and date filter
uv run main.py --source linkedin --query "python" "machine learning" --count 50 --days 7

# With location and workplace filter
uv run main.py --source linkedin \
    --query "data scientist" \
    --location "United States" \
    --workplace remote

# Full filter set
uv run main.py --source linkedin \
    --query "ML engineer" "data scientist" \
    --count 50 --days 7 \
    --location "United States" \
    --workplace remote \
    --experience-level mid-senior entry \
    --employment-type full-time contract
```

> **Note:** `--experience-level` and `--employment-type` each accept a single value via the CLI.
> To combine multiple values, set them in the YAML `defaults` section using the raw filter codes.

### LinkedIn filter reference

#### `--workplace`

| CLI value | Meaning |
|---|---|
| `onsite` | On-site only |
| `remote` | Remote only |
| `hybrid` | Hybrid |

#### `--employment-type`

| CLI value | Meaning |
|---|---|
| `full-time` | Full-time |
| `part-time` | Part-time |
| `contract` | Contract |
| `temporary` | Temporary |
| `internship` | Internship |
| `volunteer` | Volunteer |

#### `--experience-level`

| CLI value | Meaning |
|---|---|
| `internship` | Internship |
| `entry` | Entry level |
| `associate` | Associate |
| `mid-senior` | Mid-Senior level |
| `director` | Director |
| `executive` | Executive |

#### `--days`

LinkedIn maps the `--days` value to the nearest available time window:

| `--days` value | LinkedIn filter applied |
|---|---|
| 1 | Last 24 hours |
| 2–7 | Last week |
| 8+ | Last month |

### Example output

```
──────────────────────── Web Scraper — Linkedin ────────────────────────
  Queries  : ML engineer, data scientist
  Count    : up to 50 per query, last 7 day(s)
  Database : data/jobs.db

[23:06:02] INFO  Fetching search page 1 (offset=0) ...
[23:06:03] INFO  Page 1: 25 card(s) found
...
  [ML engineer]    fetched=48  new=46  skipped=2
  [data scientist] fetched=50  new=49  skipped=1

┏━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┓
┃ Metric        ┃      Value ┃
┡━━━━━━━━━━━━━━━╇━━━━━━━━━━━━┩
│ Total fetched │         98 │
│ New (saved)   │         95 │
│ Skipped (dup) │          3 │
│ Database      │ data/jobs.db │
└───────────────┴────────────┘
```

---

## Database & Storage

All scraped jobs are stored in a single SQLite database (`data/jobs.db` by default).

- **No overwriting** — existing records are never modified. Only new `job_id` values are inserted.
- **Cross-run deduplication** — the same job appearing in multiple scrape runs is stored exactly once.
- **Separate tables** — `upwork_jobs` and `linkedin_jobs` each mirror their dataclass schema exactly.
- **Future migration** — replacing SQLite with PostgreSQL requires only swapping the `sqlite3` calls in `SqliteStorage`; the public API (`save`, `load_all`, `delete_by_ids`, `clear_all`) stays identical.

### Job schemas

#### Upwork (`upwork_jobs` table)

| Column | Description |
|---|---|
| `job_id` | Unique Upwork job identifier (primary key) |
| `source` | Always `upwork` |
| `title` | Job title |
| `job_type` | `FIXED` or `HOURLY` |
| `budget` | Budget string (e.g. `$500` or `$20–$40/hr`) |
| `publish_time` | ISO 8601 timestamp when the job was posted |
| `url` | Direct link to the job posting |
| `description` | First 500 characters of the job description |
| `experience_level` | `Expert` / `Intermediate` / `Entry Level` / `N/A` |
| `duration` | e.g. `1 to 3 months` / `N/A` |
| `skills` | Comma-separated list of up to 5 required skills |
| `client_country` | Client's country, if public |
| `client_payment_verified` | `Yes` / `No` / empty |
| `client_total_spent` | e.g. `$5,000+` / empty |
| `client_total_reviews` | Number of reviews / empty |
| `client_total_feedback` | Average star rating, e.g. `4.90` / empty |
| `scraped_at` | ISO 8601 UTC timestamp of when the row was written |

> **Note:** Client fields are only populated when the client's profile is public. Visitor sessions return empty values for most clients.

#### LinkedIn (`linkedin_jobs` table)

| Column | Description |
|---|---|
| `job_id` | Unique LinkedIn job identifier (primary key) |
| `source` | Always `linkedin` |
| `title` | Job title |
| `company` | Hiring company name |
| `location` | City / state / country |
| `workplace_type` | `Remote` / `Hybrid` / `On-site` |
| `employment_type` | `Full-time` / `Part-time` / `Contract` / `Temporary` / etc. |
| `experience_level` | `Entry level` / `Mid-Senior level` / `Director` / etc. |
| `description` | Full job description text |
| `skills` | Job function or extracted keywords |
| `publish_time` | ISO date string (e.g. `2026-04-12`) |
| `url` | Direct link to the job posting |
| `applicant_count` | e.g. `Over 200 applicants` / empty |
| `scraped_at` | ISO 8601 UTC timestamp of when the row was written |

### Cache

A `scrape_cache` table stores metadata about recent scrape runs. Entries are keyed on `(source, query, job_id)` and automatically purged after `cache_ttl_days` (default 2 days).

- Cache is checked before each query. A cache hit is logged; the scraper still runs to pick up new postings, but the cache signals that recent data exists.
- Purging happens automatically on every `SqliteStorage` initialisation.
- The TTL is configurable in YAML: `database.cache_ttl_days`.

### Clearing data

**Via the CLI (Python REPL):**
```python
from storage.sqlite_storage import SqliteStorage
s = SqliteStorage("data/jobs.db")
s.clear_all()              # delete everything
s.clear_all("upwork")     # delete only Upwork jobs
s.clear_all("linkedin")   # delete only LinkedIn jobs
s.delete_by_ids("upwork", ["job-id-1", "job-id-2"])  # delete specific records
```

**Via the UI:** Use *Delete Selected* or *Clear All* buttons in the Upwork Jobs or LinkedIn Jobs tabs.

---

## Running Tests

```bash
uv run pytest tests/ -v
```

The test suite is fully offline — no browser or network calls are made. All external dependencies are monkeypatched.

```
186 passed in 1.12s
```

| Test file | What it covers |
|---|---|
| `test_models.py` | `JobListing` and `LinkedInJobListing` fields, `scraped_at` auto-population, `asdict` round-trip |
| `test_csv_storage.py` | Header creation, parent directory creation, deduplication across runs, edge cases (commas, quotes, newlines in fields) |
| `test_sqlite_storage.py` | Schema init, save/dedup (Upwork + LinkedIn), `load_all`, `delete_by_ids`, `clear_all`, full cache lifecycle (put/get/has/purge/expire) |
| `test_upwork_scraping.py` | Field mapping, pagination, within/cross-page dedup, date cutoff, early stop, concurrent `scrape_many()` |
| `test_linkedin_scraping.py` | URL building, HTML card parsing, `_to_listing` field mapping, pagination, dedup, date cutoff, `scrape_many()` |

---

## Adding a New Scraper

1. **Create a subpackage** — add `src/web_scraping/<site>/scraper.py` with a class that subclasses `BaseScraper`.
2. **Add a model** — add a dataclass to `src/web_scraping/models.py` for the site's schema, and register it in `SqliteStorage._SOURCE_META`.
3. **Add config** — add a new top-level key to `src/configs/scraping_configs.yaml`.
4. **Wire up the CLI** — add a branch in `main.py` to load the new config and instantiate the scraper.
5. **Wire up the UI** — add a tab in `app.py` calling `jobs_tab.build("<site>")` and a branch in `ui/scraper_tab.py`.
6. **Storage is automatic** — `SqliteStorage` derives column names from the dataclass fields at schema creation time.

```python
# src/web_scraping/base_scraper.py
class BaseScraper(ABC):
    @abstractmethod
    async def scrape(self, query: str, count: int, days: int | None) -> list[Any]: ...

    @abstractmethod
    async def scrape_many(self, queries: list[str], count: int, days: int | None) -> dict[str, list[Any]]: ...
```

---

## Notes & Limitations

- **Upwork client info** — client fields (`client_country`, `client_payment_verified`, etc.) are only populated when the client's profile is set to public. Most visitor (unauthenticated) sessions return empty values for these fields.
- **Upwork requires a display** — Upwork's Cloudflare protection requires a real (non-headless) browser. A running X display is needed (standard desktop session). Headless or server environments are not supported for Upwork.
- **LinkedIn rate limiting** — the guest API has no published rate limits, but aggressive scraping may result in temporary blocks. The scraper adds a short delay between pages (`request_delay`) and between detail fetches (`detail_delay`). Increase these in YAML if you hit 429 errors.
- **LinkedIn time filter granularity** — LinkedIn only supports three time windows (24 h, 1 week, 1 month). The `--days` value is mapped to the nearest available window; see the [filter reference](#--days) above.
- **LinkedIn authentication** — the scraper uses the public guest API only. Authenticated scraping (for features like saved searches or private jobs) is not supported.
- **Database file** — the SQLite file is a single flat file at `data/jobs.db`. Back it up before running `clear_all()` if you want to preserve data.
- **Cache TTL** — the scrape cache stores only metadata (source, query, job_id), not full job content. Adjusting `cache_ttl_days` to `0` effectively disables caching.

---

## Future Work

- **Additional job boards** — Indeed, Glassdoor, Freelancer, Toptal, and Remoteok scrapers following the same `BaseScraper` interface.
- **PostgreSQL backend** — swap `sqlite3` in `SqliteStorage` for `psycopg2` / `asyncpg` for multi-user or cloud deployments; the public API is unchanged.
- **Scheduled runs** — APScheduler integration to trigger scrapes automatically at set intervals, with optional desktop notifications.
- **Notification system** — email or Slack alerts when new matching jobs are found.
- **Filtering & ranking** — post-scrape filters (minimum budget, keyword exclusions) and relevance scoring.
- **Headless Cloudflare bypass** — investigate residential proxy or browser-fingerprint techniques to remove the X display dependency for Upwork.
- **Async HTTP** — replace curl_cffi with an async HTTP client (e.g. `httpx`) to make `_collect_raw` natively async.
- **CLI tool** — publish as an installable command (`uv tool install`) with a proper entry point.
- **Export from UI** — button in the Jobs tab to export the current filtered view to CSV.
- **LinkedIn authenticated scraping** — explore authenticated sessions for access to private job posts and saved searches.

---

## License

MIT License

Copyright (c) 2026

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
