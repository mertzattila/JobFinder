"""Scraper for RecruiterBox / Trakstar Hire career sites.

Some companies (e.g. Commsignia) host jobs on RecruiterBox (now Trakstar Hire),
which exposes a clean public JSON API:

    GET https://jsapi.recruiterbox.com/v1/openings?client_name=<client>

The response is ``{"objects": [...]}`` where each opening has ``title``,
``location`` ({"city","state","country"}), and ``hosted_url``. There is no
server-side location filter, so we filter by substring on the location
(configured via ``location_filter``, e.g. "Hungary").

No browser needed.

Config (config.yaml) for a RecruiterBox target:

    scraper: recruiterbox
    api_url: https://jsapi.recruiterbox.com/v1/openings?client_name=commsignia
    location_filter: Hungary       # keep jobs whose location contains this (optional)
"""

from __future__ import annotations

import logging

import requests

from jobfinder.models import JobPosting
from jobfinder.scrapers.base import BaseScraper

log = logging.getLogger(__name__)


class RecruiterBoxScraper(BaseScraper):
    def scrape(self) -> list[JobPosting]:
        t = self.target
        if not t.api_url:
            log.error("[%s] recruiterbox scraper needs api_url in config; skipping", t.name)
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
            log.exception("[%s] recruiterbox API request failed", t.name)
            return []

        openings = payload.get("objects") or []
        loc_filter = (t.location_filter or "").lower()

        jobs: list[JobPosting] = []
        for o in openings:
            loc = o.get("location") or {}
            # Dedupe parts (state/country are often identical, e.g. "Hungary").
            seen_parts: list[str] = []
            for p in (loc.get("city"), loc.get("state"), loc.get("country")):
                if p and p not in seen_parts:
                    seen_parts.append(p)
            location = ", ".join(seen_parts)
            if loc_filter and loc_filter not in location.lower():
                continue
            title = (o.get("title") or "").strip()
            url = o.get("hosted_url") or ""
            if not title or not url:
                continue
            jobs.append(
                JobPosting(
                    title=title,
                    company=t.company,
                    url=url,
                    location=location or None,
                    description=f"{title} {location} {o.get('team') or ''}".strip(),
                    source=t.name,
                )
            )
        log.info(
            "[%s] recruiterbox API: %d openings, %d match location %r",
            t.name,
            len(openings),
            len(jobs),
            t.location_filter,
        )
        return jobs
