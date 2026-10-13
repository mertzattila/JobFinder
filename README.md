# JobFinder 🎯

An automated, self-hosted job-search and CV-matching pipeline for the Hungarian
embedded/hardware market. It runs **daily on GitHub Actions**, scrapes company
career pages and local student job boards directly (no LinkedIn), uses an **LLM
to score how well each job fits your CV**, and pings you on **Discord or
Telegram** only for strong matches you haven't seen before.

---

## Architecture

```
run.py                      # CLI entry point
jobfinder/
├── config.py               # Loads config.yaml (settings) + env vars (secrets)
├── profile.py              # Loads your CV text from profile.md
├── models.py               # Pydantic models: JobPosting, MatchResult, ScoredJob
├── state.py                # Seen-URL store (seen_jobs.json) for de-duplication
├── fetcher.py              # requests (static) + Playwright (JS-rendered) fetching
├── scrapers/
│   ├── base.py             # BaseScraper interface
│   └── generic.py          # Config-driven CSS-selector scraper
├── matcher.py              # LLM evaluation -> structured MatchResult (Gemini/OpenAI)
├── notifier.py             # Discord webhook / Telegram bot alerts
└── pipeline.py             # Orchestrator: scrape → filter → match → notify → persist
config.yaml                 # Targets, selectors, keywords, threshold, provider
profile.md                  # ← PASTE YOUR CV HERE
seen_jobs.json              # State, committed back by the Action each run
.github/workflows/job_scraper.yml
```

### Why this design

| Concern | Choice | Reason |
|---|---|---|
| HTML fetching | `requests`/`BeautifulSoup` by default, **Playwright only when `render: true`** | Fast and cheap for static pages; a real browser only where JS is required (Workday, SmartRecruiters, etc.). Keeps CI light. |
| Scraping | **One config-driven scraper** reading CSS selectors from `config.yaml` | Career-page markup changes constantly. Fixing a selector is a config edit, not a code change. Add a bespoke `BaseScraper` subclass only when a site truly needs it. |
| LLM output | **Pydantic + JSON schema** (`responseSchema` / `response_format`) | Guarantees a validated `score` (1–10) and summary instead of free text you must regex. |
| Cost control | **Keyword pre-filter before the LLM** | Only plausible jobs cost an API call. |
| State | **`seen_jobs.json` committed back by the Action** | Simple, durable, auditable; no external DB. (GitHub Actions cache is an alternative — see below.) |
| Resilience | A broken target or one failed LLM call is logged and skipped | One bad site never kills the whole run. |

The daily data flow: **scrape every enabled target → drop already-seen URLs →
keyword pre-filter → LLM scores each survivor → if score ≥ threshold, send an
alert → persist the updated seen-list.**

---

## Quick start (local)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Only if any target uses render: true
pip install playwright && python -m playwright install chromium

# 1. Paste your CV
$EDITOR profile.md

# 2. Set secrets for a local run (see table below)
export GEMINI_API_KEY="..."          # or OPENAI_API_KEY
export DISCORD_WEBHOOK_URL="..."      # or TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID

# 3. Try it without sending any alerts
python run.py --dry-run --verbose

# 4. Real run
python run.py
```

---

## 1. Where to paste your CV

Open **`profile.md`** and replace the template under the comment block with your
real summary, skills, and projects. The whole file is sent to the LLM verbatim
as the candidate profile, so being specific about your stack (C, C++, Python,
Verilog, Assembly, Arduino, ESP32) and hands-on hardware/telemetry projects
directly improves scoring accuracy. If `profile.md` is missing or empty, a
built-in default profile is used.

## 2. How to configure target URLs

Everything tunable lives in **`config.yaml`** — no code changes needed:

- **`keywords`** – the pre-filter terms (already includes `embedded`,
  `beágyazott`, `C`, `C++`, `Python`, `microcontroller`, `gyakornok`, `intern`,
  `student`, …).
- **`score_threshold`** – minimum LLM score (1–10) to trigger an alert. Default `7`.
- **`llm.provider`** – `gemini` or `openai`; **`llm.model`** – e.g.
  `gemini-1.5-flash` or `gpt-4o-mini`.
- **`notifier.channel`** – `discord` or `telegram`.
- **`targets`** – each entry is one career page / job board:

  ```yaml
  - name: bosch-hu          # internal id (used in logs + fingerprints)
    company: Bosch          # shown in notifications
    url: https://...        # page listing the jobs
    enabled: true           # flip to false to skip without deleting
    render: true            # true => render with Playwright (JS-heavy page)
    job_card: "a.job-item"  # CSS selector matching ONE job listing (repeats)
    title: ".title"         # title text, relative to job_card (optional)
    link: "a"               # the <a> with the job URL (optional; auto-detected)
    location: ".location"   # location text (optional)
  ```

> ⚠️ **The selectors shipped in `config.yaml` are starting points.** Career-page
> HTML differs per vendor and changes over time. Before trusting a target, open
> its URL in your browser, inspect the markup, and adjust `job_card` / `title` /
> `link` / `location`. Run `python run.py --dry-run --verbose` and watch the
> `matched N job cards` log line — if it says `0`, your `job_card` selector is
> wrong. Targets whose portals need careful tuning (e.g. NXP/Silicon Labs on
> Workday) ship with `enabled: false`; enable them once verified.

## 3. Repository secrets setup

In your GitHub repo: **Settings → Secrets and variables → Actions → New
repository secret**. Add the ones your chosen provider/channel need:

| Secret | Needed when | Where to get it |
|---|---|---|
| `GEMINI_API_KEY` | `llm.provider: gemini` | [Google AI Studio](https://aistudio.google.com/app/apikey) |
| `OPENAI_API_KEY` | `llm.provider: openai` | [OpenAI API keys](https://platform.openai.com/api-keys) |
| `DISCORD_WEBHOOK_URL` | `notifier.channel: discord` | Discord → Server/Channel Settings → Integrations → Webhooks → New Webhook → Copy URL |
| `TELEGRAM_BOT_TOKEN` | `notifier.channel: telegram` | Create a bot with [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT_ID` | `notifier.channel: telegram` | Message your bot, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` and read `chat.id` |

If any target uses `render: true`, also add a repository **variable** (Settings →
Secrets and variables → Actions → **Variables** tab) named `ENABLE_PLAYWRIGHT`
with value `1`. This makes CI install the Chromium browser; otherwise Playwright
is skipped to keep runs fast.

## 4. Automation

`.github/workflows/job_scraper.yml` runs **daily at 06:30 UTC** (≈07:30–08:30
Budapest) and can also be launched manually from the **Actions** tab
(`workflow_dispatch`, with an optional **dry-run** toggle). After each real run
it commits the updated `seen_jobs.json` back to the repo so you're never alerted
about the same job twice. The commit message carries `[skip ci]` to avoid a loop.

### Alternative state backend
If you'd rather not commit state, swap the "Commit updated state" step for
`actions/cache` keyed on a rolling date, and point `--state` at the cached path.
The current commit-back approach is the default because it's durable and lets you
see the history of what was found.

---

## Running the tests

```bash
source .venv/bin/activate
pip install pytest
pytest -q
```

The tests are fully offline (LLM and HTTP are mocked), covering score coercion,
keyword filtering, URL fingerprinting/de-dup, state persistence, and the
end-to-end pipeline flow.

---

## Legal / etiquette note
Scrape responsibly: respect each site's Terms of Service and `robots.txt`, keep
the built-in request delay, and don't hammer endpoints. This tool is for your
own personal job search.
