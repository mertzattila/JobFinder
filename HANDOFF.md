# Development Handoff

This document captures the state of the project so development can continue in a
new session (e.g. the Kiro desktop app). The code itself is the source of truth;
this is the context around it.

## How to continue

```bash
git clone https://github.com/mertzattila/JobFinder.git
cd JobFinder
git checkout feat/job-scraper-pipeline   # all work lives here (PR #1)

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q                                # 5 offline tests should pass
python run.py --dry-run --verbose        # smoke test (no alerts sent)
```

Open PR: https://github.com/mertzattila/JobFinder/pull/1 (base `main` ← `feat/job-scraper-pipeline`).

## What this project is

An automated daily job-search + CV-matching pipeline for the Hungarian
embedded/hardware internship market. Scrapes company career pages and local
student job boards directly (no LinkedIn), scores each job against the candidate
CV with an LLM, and alerts via Discord/Telegram for strong, unseen matches.
Runs on GitHub Actions on a daily cron.

## Architecture (decisions made)

- **Fetching**: `requests`/`BeautifulSoup` for static pages; **Playwright only**
  for targets with `render: true` (JS-heavy ATS portals). Keeps CI light.
- **Scraping**: a single **config-driven CSS-selector scraper**
  (`jobfinder/scrapers/generic.py`) reads selectors from `config.yaml`. Site
  markup changes are a config edit, not code. Add a `BaseScraper` subclass +
  register it in `pipeline.build_scraper` only if a site truly needs bespoke logic.
- **LLM matching** (`jobfinder/matcher.py`): Gemini or OpenAI via REST (no vendor
  SDK), using **JSON-schema structured output** validated by the `MatchResult`
  Pydantic model (`score` 1-10, 2-sentence `summary`, `recommended`).
- **Cost control**: keyword pre-filter (`pipeline.keyword_match`) runs before any
  LLM call.
- **State** (`jobfinder/state.py`): `seen_jobs.json`, committed back by the
  workflow so no job is notified twice.
- **Resilience**: a broken target or a single failed LLM call is logged and
  skipped; it never kills the whole run.

## Module map

| File | Responsibility |
|---|---|
| `run.py` | CLI entry point (`--dry-run`, `--config`, `--profile`, `--state`, `-v`) |
| `jobfinder/config.py` | Loads `config.yaml` (Settings) + env vars (Secrets) |
| `jobfinder/profile.py` | Loads CV text from `profile.md` |
| `jobfinder/models.py` | `JobPosting`, `MatchResult`, `ScoredJob` |
| `jobfinder/state.py` | Seen-URL JSON store |
| `jobfinder/fetcher.py` | Static + Playwright fetching |
| `jobfinder/scrapers/` | `base.py` (interface) + `generic.py` (config-driven) |
| `jobfinder/matcher.py` | LLM evaluation (Gemini/OpenAI) |
| `jobfinder/notifier.py` | Discord webhook / Telegram bot |
| `jobfinder/pipeline.py` | Orchestrator: scrape → filter → match → notify → persist |
| `.github/workflows/job_scraper.yml` | Daily cron + manual dispatch; commits state back |

## Current status

- ✅ Full pipeline implemented and wired together.
- ✅ 5 offline unit tests pass (score coercion, keyword filter, URL
  fingerprint/dedup, state roundtrip, end-to-end dry-run flow).
- ✅ Mocked request-shape checks confirmed for both LLM providers and both
  notifier channels (Gemini `responseSchema`, OpenAI `json_object`, Discord
  embed fields, Telegram HTML escaping).
- ✅ `ruff` clean (config in `pyproject.toml`).
- ✅ End-to-end `--dry-run` executes the real fetch → parse → filter → persist flow.

## Open follow-ups / TODO

1. **Verify CSS selectors per target** — the selectors in `config.yaml` are
   STARTING POINTS, not validated against live pages. For each enabled target:
   open the URL, inspect the HTML, adjust `job_card` / `title` / `link` /
   `location`, then run `python run.py --dry-run --verbose` and check the
   `matched N job cards` log line (0 = selector is wrong). Targets likely needing
   tuning (NXP, Silicon Labs — Workday-based) ship with `enabled: false`.
2. **Set `main` as the repo's default branch** — the repo started empty, so a PR
   base `main` was created as an empty baseline commit. Changing the default
   branch via the API was blocked (HTTP 403) in the build environment; do it in
   GitHub repo Settings → Branches, or it may already be fine from the desktop.
3. **Add repository secrets** before the first real Action run (see README):
   `GEMINI_API_KEY` or `OPENAI_API_KEY`; `DISCORD_WEBHOOK_URL` or
   `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`; and the `ENABLE_PLAYWRIGHT=1`
   repository *variable* if any target uses `render: true`.
4. **Paste the real CV** into `profile.md`.
5. **Possible enhancements**: per-target detail-page fetching for richer
   descriptions before scoring; RSS/API sources where available; a daily digest
   summary message; retry/backoff tuning.

## Gotchas worth knowing

- Playwright is an optional dependency, imported lazily. If a target sets
  `render: true` but Playwright/Chromium isn't installed, that target raises a
  clear error (and the run continues with other targets).
- `seen_jobs.json` is intentionally **not** gitignored — the workflow commits it
  back. Jobs are marked seen *before* the LLM call so a transient failure doesn't
  cause infinite re-processing across daily runs.
- The sandbox had a read-only system site-packages; use a virtualenv locally.
