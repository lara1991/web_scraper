# Web Scraper

A modular, extensible job-board scraper built in Python.  
Currently supports **Upwork** (internal GraphQL API) and **LinkedIn** (public guest API) — no official API keys or login required.

## Table of Contents

- [Web Scraper](#web-scraper)
  - [Table of Contents](#table-of-contents)
  - [How It Works](#how-it-works)
    - [Upwork](#upwork)
    - [LinkedIn](#linkedin)
  - [Project Structure](#project-structure)
  - [Requirements](#requirements)
  - [Installation](#installation)
  - [Configuration](#configuration)
    - [Upwork config keys](#upwork-config-keys)
    - [LinkedIn config keys](#linkedin-config-keys)
  - [Usage](#usage)
    - [Upwork](#upwork-1)
    - [LinkedIn](#linkedin-1)
    - [LinkedIn filter reference](#linkedin-filter-reference)
      - [`--workplace`](#--workplace)
      - [`--employment-type`](#--employment-type)
      - [`--experience-level`](#--experience-level)
      - [`--days`](#--days)
    - [Example output](#example-output)
  - [CSV Schemas](#csv-schemas)
    - [Upwork CSV schema](#upwork-csv-schema)
    - [LinkedIn CSV schema](#linkedin-csv-schema)
  - [Running Tests](#running-tests)
  - [Adding a New Scraper](#adding-a-new-scraper)
  - [Notes \& Limitations](#notes--limitations)
  - [Future Work](#future-work)
  - [License](#license)

---

## How It Works

### Upwork

1. Opens a real (non-headless) Chrome window via **nodriver** to bypass Cloudflare.
2. Extracts the visitor OAuth token that Upwork sets as a session cookie.
3. Uses **curl_cffi** (TLS fingerprint impersonation) to call Upwork's internal GraphQL endpoint with those cookies — no API key needed.
4. Results are deduplicated by `job_id` and appended to a CSV file. Re-running the scraper never creates duplicate rows.

### LinkedIn

1. Calls LinkedIn's public guest job-search API with **curl_cffi** — no login, no Selenium, no browser.
2. Parses the returned HTML job cards with **BeautifulSoup4**.
3. Optionally fetches each job's detail page for full description, skills, and applicant count.
4. Results are deduplicated by `job_id` and appended to a separate CSV file.

---

## Project Structure

```
web_scraper/
├── main.py                          # CLI entry point (--source upwork|linkedin)
├── pyproject.toml
│
├── src/
│   ├── configs/
│   │   └── scraping_configs.yaml    # All configuration (URLs, defaults, output paths)
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
│       └── csv_storage.py           # CsvStorage — dedup-safe append-only CSV writer
│
├── data/
│   └── web_scraping_results/
│       ├── upwork_scraping_results.csv    # Upwork results (auto-created)
│       └── linkedin_scraping_results.csv  # LinkedIn results (auto-created)
│
├── tests/
│   ├── conftest.py                  # Shared fixtures and factory helpers
│   ├── test_models.py
│   ├── test_csv_storage.py
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
upwork:
  browser_executable: "/usr/bin/google-chrome-stable"
  graphql_url: "https://www.upwork.com/api/graphql/v1?alias=visitorJobSearch"
  page_size: 50
  output_file: "data/web_scraping_results/upwork_scraping_results.csv"
  defaults:
    query: ["generative ai", "RAG Systems", "Computer Vision"]
    count: 100
    days: null     # null = no date filter

linkedin:
  page_size: 25
  output_file: "data/web_scraping_results/linkedin_scraping_results.csv"
  defaults:
    query: ["python", "machine learning"]
    count: 50
    days: 7
    locations: ["United States"]
    workplace_types: []     # see LinkedIn filter reference
    employment_types: []
    experience_levels: []
```

### Upwork config keys

| Key | Description |
|---|---|
| `browser_executable` | Path to the Chrome binary |
| `page_size` | Results per GraphQL request (max 50) |
| `output_file` | CSV output path (relative to project root) |
| `defaults.query` | Default search queries (list) |
| `defaults.count` | Default max results per query |
| `defaults.days` | Default date window in days (`null` = no limit) |

### LinkedIn config keys

| Key | Description |
|---|---|
| `page_size` | Results per search API page (fixed at 25 by LinkedIn) |
| `output_file` | CSV output path (relative to project root) |
| `defaults.query` | Default search queries (list) |
| `defaults.count` | Default max results per query |
| `defaults.days` | Default date window in days (`null` = no limit) |
| `defaults.locations` | Default location filters (list of strings) |
| `defaults.workplace_types` | Default workplace type codes (see filter reference) |
| `defaults.employment_types` | Default employment type codes (see filter reference) |
| `defaults.experience_levels` | Default experience level codes (see filter reference) |

---

## Usage

Select the job board with `--source upwork` or `--source linkedin`. All other flags are shared unless noted.

```
uv run main.py --source {upwork,linkedin} [options]
```

### Upwork

```bash
# Single query with defaults from YAML
uv run main.py --source upwork --query python

# Multiple queries (run concurrently in a single browser session)
uv run main.py --source upwork --query python django fastapi

# Limit results and apply a date filter
uv run main.py --source upwork --query "machine learning" --count 50 --days 7
```

### LinkedIn

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
Source   : linkedin
Fetching up to 50 job(s) per query, last 7 day(s)
Queries  : ML engineer, data scientist

  [ML engineer]    fetched=48  new=46  skipped=2
  [data scientist] fetched=50  new=49  skipped=1

Total fetched : 98
Total new     : 95
Total skipped : 3
Results       : data/web_scraping_results/linkedin_scraping_results.csv
```

---

## CSV Schemas

Each source writes to its own CSV file. Both files are append-only and deduplicated on `job_id`.

### Upwork CSV schema

| Column | Description |
|---|---|
| `job_id` | Unique Upwork job identifier (deduplication key) |
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

> **Note:** Client fields (`client_country`, `client_payment_verified`, etc.) are only populated when the client's profile is public. Visitor (unauthenticated) sessions return null for most clients.

### LinkedIn CSV schema

| Column | Description |
|---|---|
| `job_id` | Unique LinkedIn job identifier (deduplication key) |
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

---

## Running Tests

```bash
uv run pytest tests/ -v
```

The test suite is fully offline — no browser or network calls are made. All external dependencies are monkeypatched.

```
147 passed in 0.63s
```

| Test file | What it covers |
|---|---|
| `test_models.py` | `JobListing` and `LinkedInJobListing` fields, `scraped_at` auto-population, `asdict` round-trip |
| `test_csv_storage.py` | Header creation, parent directory creation, deduplication across runs, edge cases (commas, quotes, newlines in fields) |
| `test_upwork_scraping.py` | Field mapping, pagination, within/cross-page dedup, date cutoff, early stop, concurrent `scrape_many()` |
| `test_linkedin_scraping.py` | URL building, HTML card parsing, `_to_listing` field mapping, pagination, dedup, date cutoff, `scrape_many()` |

---

## Adding a New Scraper

1. **Create a subpackage** — add `src/web_scraping/<site>/scraper.py` with a class that subclasses `BaseScraper`.
2. **Add a model** — add a dataclass to `src/web_scraping/models.py` for the site's schema.
3. **Add config** — add a new top-level key to `src/configs/scraping_configs.yaml`.
4. **Wire it up** — add a branch in `main.py` to load the new config and instantiate the new scraper.
5. **Storage is automatic** — `CsvStorage` derives column names from any dataclass's fields at runtime.

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
- **LinkedIn rate limiting** — the guest API has no published rate limits, but aggressive scraping may result in temporary blocks. The scraper adds a short delay between queries in `scrape_many()` to stay conservative. Use `--count` and `--days` to narrow results rather than scraping large volumes at once.
- **LinkedIn time filter granularity** — LinkedIn only supports three time windows (24 h, 1 week, 1 month). The `--days` value is mapped to the nearest available window; see the [filter reference](#--days) above.
- **LinkedIn authentication** — the scraper uses the public guest API only. Authenticated scraping (for features like saved searches or private jobs) is not supported.

---

## Future Work

- **Additional job boards** — Indeed, Glassdoor, Freelancer, Toptal, and Remoteok scrapers following the same `BaseScraper` interface.
- **Scheduled runs** — cron / APScheduler integration to run searches automatically at set intervals.
- **Notification system** — email or Slack alerts when new matching jobs are found.
- **Filtering & ranking** — post-scrape filters (minimum budget, keyword exclusions) and relevance scoring.
- **Database storage** — `SqliteStorage` / `PostgresStorage` implementations of `BaseStorage` for queryable persistence.
- **Headless Cloudflare bypass** — investigate residential proxy or browser-fingerprint techniques to remove the X display dependency for Upwork.
- **Async HTTP** — replace curl_cffi with an async HTTP client (e.g. `httpx`) to make `_collect_raw` natively async and avoid `asyncio.to_thread`.
- **CLI tool** — publish as an installable command (`uv tool install`) with a proper entry point.
- **Dashboard** — lightweight web UI (e.g. Streamlit) to browse, filter, and export scraped results.

---

## License

MIT License

Copyright (c) 2026

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
