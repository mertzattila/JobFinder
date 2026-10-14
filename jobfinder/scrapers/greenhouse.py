"""Scraper for Greenhouse-hosted career sites.

Greenhouse is one of the most common ATS platforms and exposes a clean,
unauthenticated public JSON API:

    GET https://boards-api.greenhouse.io/v1/boards/<board>/jobs

The response is ``{"jobs": [...]}`` where each job has ``title``,
``location`` ({"name": ...}), ``absolute_url`` and ``updated_at``. The API
has no server-side location filter, so we filter by substring on the location
name (configured via ``location_filter``, e.g. "Hungary").

No browser needed — robust and fast.

Config (config.yaml) for a Greenhouse target:

    scraper: greenhouse
    api_url: https://boards-api.greenhouse.io/v1/boards/formlabs/jobs
    location_filter: Hungary       # keep jobs whose location contains this
"""

from __future__ import annotations

import logging

import requests

from jobfinder.models import JobPosting
from jobfinder.scrapers.base import BaseScraper

log = logging.getLogger(__name__)


class GreenhouseScraper(BaseScraper):
    def scrape(self) -> list[JobPosting]:
        t = self.target
        if not t.api_url:
            log.error("[%s] greenhouse scraper needs api_url in config; skipping", t.name)
            return []

        headers = {
            "User-Agent": self.fetcher.session.headers["User-Agent"],
            "Accept": "application/json",
        }
        try:
            resp = requests.get(t.api_url, headers=headers, timeout=self.fetcher.timeout)
            resp.raise_for_status()
            payload = resp.json()
        except Exception:  # noqa: BLE001 - a broken API shouldn't kill the run
            log.exception("[%s] greenhouse API request failed", t.name)
            return []

        all_jobs = payload.get("jobs") or []
        loc_filter = (t.location_filter or "").lower()

        jobs: list[JobPosting] = []
        for j in all_jobs:
            location = (j.get("location") or {}).get("name") or ""
            if loc_filter and loc_filter not in location.lower():
                continue
            title = (j.get("title") or "").strip()
            url = j.get("absolute_url") or ""
            if not title or not url:
                continue
            jobs.append(
                JobPosting(
                    title=title,
                    company=t.company,
                    url=url,
                    location=location or None,
                    description=f"{title} {location}".strip(),
                    source=t.name,
                )
            )
        log.info(
            "[%s] greenhouse API: %d jobs, %d match location %r",
            t.name,
            len(all_jobs),
            len(jobs),
            t.location_filter,
        )
        return jobs
