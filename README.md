# Web Scraper

A modular, extensible job-board scraper built in Python.  
Currently supports **Upwork** via its internal GraphQL API — no official API key needed.

## Table of Contents

- [How It Works](#how-it-works)
- [Project Structure](#project-structure)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Running Tests](#running-tests)
- [Adding a New Scraper](#adding-a-new-scraper)
- [Future Work](#future-work)
- [License](#license)

---

## How It Works

1. Opens a real (non-headless) Chrome window via **nodriver** to bypass Cloudflare.
2. Extracts the visitor OAuth token that Upwork sets as a session cookie.
3. Uses **curl_cffi** (TLS fingerprint impersonation) to call Upwork's internal GraphQL endpoint with those cookies — no API key needed.
4. Results are deduplicated by `job_id` and appended to a CSV file. Re-running the scraper never creates duplicate rows.

---

## Project Structure

```
web_scraper/
├── main.py                          # CLI entry point
├── pyproject.toml
│
├── src/
│   ├── configs/
│   │   └── scraping_configs.yaml    # All configuration (URLs, defaults, output paths)
│   │
│   ├── web_scraping/
│   │   ├── models.py                # JobListing dataclass (shared schema)
│   │   ├── base_scraper.py          # BaseScraper abstract base class
│   │   ├── upwork_scraping.py       # UpworkScraper implementation
│   │   └── other_scraping.py        # Placeholder for future scrapers
│   │
│   └── storage/
│       ├── base_storage.py          # BaseStorage abstract base class
│       └── csv_storage.py           # CsvStorage — dedup-safe append-only CSV writer
│
├── data/
│   └── web_scraping_results/
│       └── upwork_scraping_results.csv   # Persistent results (auto-created)
│
├── tests/
│   ├── conftest.py                  # Shared fixtures and factory helpers
│   ├── test_models.py
│   ├── test_csv_storage.py
│   └── test_upwork_scraping.py
│
└── experiments/
    └── upwork_with_playwrght_search.py   # Standalone prototype (reference only)
```

---

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (package manager)
- Google Chrome installed at `/usr/bin/google-chrome-stable`
- A running X display (standard desktop session — headless is not supported due to Cloudflare)

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
    query:
      - "python"
    count: 10
    days: null     # null = no date filter
```

| Key | Description |
|---|---|
| `browser_executable` | Path to the Chrome binary |
| `page_size` | Results per GraphQL request (max 50) |
| `output_file` | CSV output path (relative to project root) |
| `defaults.query` | Default search queries (list) |
| `defaults.count` | Default max results per query |
| `defaults.days` | Default date window in days (`null` = no limit) |

---

## Usage

### Single query

```bash
uv run main.py --query python
```

### Multiple queries (run concurrently, single browser session)

```bash
uv run main.py --query python django fastapi
```

### With result count and date filter

```bash
# Up to 50 results per query, posted within the last 7 days
uv run main.py --query python django --count 50 --days 7
```

### All options

```
options:
  --query / -q  QUERY [QUERY ...]   One or more search queries  (default: from yaml)
  --count / -n  N                   Max results per query       (default: 10)
  --days  / -d  N                   Max age of posting in days  (default: no limit)
```

### Example output

```
Fetching up to 20 job(s) per query, last 7 day(s)
Queries  : python, django, fastapi

  [python]  fetched=20  new=18  skipped=2
  [django]  fetched=15  new=15  skipped=0
  [fastapi] fetched=9   new=8   skipped=1

Total fetched : 44
Total new     : 41
Total skipped : 3
Results       : data/web_scraping_results/upwork_scraping_results.csv
```

### CSV columns

| Column | Description |
|---|---|
| `job_id` | Unique job identifier (deduplication key) |
| `source` | Platform name (e.g. `upwork`) |
| `title` | Job title |
| `job_type` | `FIXED` or `HOURLY` |
| `budget` | Budget string (e.g. `$500` or `$20-$40/hr`) |
| `publish_time` | ISO 8601 timestamp when the job was posted |
| `url` | Direct link to the job posting |
| `description` | First 500 characters of the job description |
| `scraped_at` | ISO 8601 UTC timestamp of when the row was written |

---

## Running Tests

```bash
uv run pytest tests/ -v
```

The test suite is fully offline — no browser or network calls are made. All external dependencies are monkeypatched.

```
58 passed in 0.36s
```

| Test file | What it covers |
|---|---|
| `test_models.py` | `JobListing` fields, `scraped_at` auto-population, `asdict` round-trip |
| `test_csv_storage.py` | Header creation, parent directory creation, deduplication across runs, edge cases (commas, quotes, newlines in fields) |
| `test_upwork_scraping.py` | Field mapping, pagination, within/cross-page dedup, date cutoff, early stop, concurrent `scrape_many()` |

---

## Adding a New Scraper

1. **Add config** — add a new top-level key to `src/configs/scraping_configs.yaml`.
2. **Implement the scraper** — create `src/web_scraping/<site>_scraping.py`, subclass `BaseScraper`, and implement `scrape()` and `scrape_many()`.
3. **Wire it up** — add a branch in `main.py` to load the new config and call the new scraper.
4. **Storage is free** — `CsvStorage` accepts any list of `JobListing` objects regardless of source.

```python
# src/web_scraping/base_scraper.py
class BaseScraper(ABC):
    @abstractmethod
    async def scrape(self, query: str, count: int, days: int | None) -> list[JobListing]: ...
```

---

## Future Work

- **Additional job boards** — LinkedIn, Indeed, Freelancer, Toptal, and Remoteok scrapers following the same `BaseScraper` interface.
- **Scheduled runs** — cron / APScheduler integration to run searches automatically at set intervals.
- **Notification system** — email or Slack alerts when new matching jobs are found.
- **Filtering & ranking** — post-scrape filters (minimum budget, keyword exclusions) and relevance scoring.
- **Database storage** — `SqliteStorage` / `PostgresStorage` implementations of `BaseStorage` for queryable persistence.
- **Headless Cloudflare bypass** — investigate residential proxy or browser-fingerprint techniques to remove the X display dependency.
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
