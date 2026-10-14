"""Scraper for Phenom People career sites.

Many large employers (e.g. Infineon) host their jobs on the Phenom People ATS,
served from ``jobs.<company>.com``. Rather than scrape the JavaScript-rendered
DOM, Phenom exposes a clean public JSON search API:

    GET https://jobs.<company>.com/api/pcsx/search
        ?domain=<company>.com&query=&location=<loc>&start=0&num=<n>

The response is ``{"data": {"positions": [...], "count": N}}`` where each
position has ``name``, ``locations`` (list), ``displayJobId`` and
``positionUrl`` (relative, e.g. ``/careers/job/<id>``).

This is far more robust than CSS selectors: no browser, no markup to break.

Config (config.yaml) for a Phenom target:

    scraper: phenom
    url: https://jobs.infineon.com/careers        # public site, used for base + display
    api_url: https://jobs.infineon.com/api/pcsx/search
    location_filter: Hungary                        # server-side location filter
"""

from __future__ import annotations

import logging
from urllib.parse import urljoin, urlparse

import requests

from jobfinder.models import JobPosting
from jobfinder.scrapers.base import BaseScraper

log = logging.getLogger(__name__)

_PAGE_SIZE = 50


class PhenomScraper(BaseScraper):
    def scrape(self) -> list[JobPosting]:
        t = self.target
        if not t.api_url:
            log.error("[%s] phenom scraper needs api_url in config; skipping", t.name)
            return []

        parsed = urlparse(t.api_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        # domain param is the bare company domain, e.g. "infineon.com"
        domain = parsed.netloc.split(".", 1)[-1] if parsed.netloc.startswith("jobs.") else parsed.netloc

        headers = {"User-Agent": self.fetcher.session.headers["User-Agent"], "Accept": "application/json"}

        # The API caps each response at ~10 results regardless of the page-size
        # param, so paginate with `start` until we've collected `count` jobs.
        positions: list[dict] = []
        start = 0
        total = None
        while True:
            params = {
                "domain": domain,
                "query": "",
                "location": t.location_filter or "",
                "start": start,
                "num": _PAGE_SIZE,
            }
            try:
                resp = requests.get(
                    t.api_url, params=params, headers=headers, timeout=self.fetcher.timeout
                )
                resp.raise_for_status()
                data = (resp.json().get("data") or {})
            except Exception:  # noqa: BLE001 - a broken API shouldn't kill the run
                log.exception("[%s] phenom API request failed at start=%d", t.name, start)
                break

            page = data.get("positions") or []
            if total is None:
                total = data.get("count") or 0
            if not page:
                break
            positions.extend(page)
            start += len(page)
            if start >= total or len(page) < 1:
                break
            if start > 500:  # safety cap
                break

        log.info("[%s] phenom API returned %d positions", t.name, len(positions))

        jobs: list[JobPosting] = []
        for p in positions:
            title = (p.get("name") or "").strip()
            rel_url = p.get("positionUrl") or ""
            if not title or not rel_url:
                continue
            url = urljoin(origin + "/", rel_url.lstrip("/"))
            locations = p.get("locations") or []
            location = ", ".join(str(x) for x in locations) if locations else None
            department = p.get("department") or ""
            jobs.append(
                JobPosting(
                    title=title,
                    company=t.company,
                    url=url,
                    location=location,
                    description=f"{title} {department} {location or ''}".strip(),
                    source=t.name,
                )
            )
        return jobs
