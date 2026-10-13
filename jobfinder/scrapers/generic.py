"""Config-driven scraper.

Most career pages and job boards render a repeating list of "job cards". Rather
than hand-code a parser per company, this scraper reads CSS selectors from the
target's config entry and extracts title/link/location generically. When a
site's HTML changes, you fix a selector in config.yaml instead of editing code.
"""

from __future__ import annotations

import logging
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from bs4.element import Tag

from jobfinder.models import JobPosting
from jobfinder.scrapers.base import BaseScraper

log = logging.getLogger(__name__)


class GenericScraper(BaseScraper):
    def scrape(self) -> list[JobPosting]:
        t = self.target
        html = (
            self.fetcher.fetch_rendered(t.url, wait_selector=t.job_card)
            if t.render
            else self.fetcher.fetch_static(t.url)
        )
        soup = BeautifulSoup(html, "lxml")
        base = t.base_url or f"{urlparse(t.url).scheme}://{urlparse(t.url).netloc}"

        jobs: list[JobPosting] = []
        cards = soup.select(t.job_card)
        log.info("[%s] matched %d job cards", t.name, len(cards))

        for card in cards:
            title = self._extract_title(card, t.title)
            url = self._extract_link(card, t.link, base)
            if not title or not url:
                continue
            location = self._extract_text(card, t.location) if t.location else None
            jobs.append(
                JobPosting(
                    title=title,
                    company=t.company,
                    url=url,
                    location=location,
                    description=card.get_text(" ", strip=True)[:2000],
                    source=t.name,
                )
            )
        return jobs

    @staticmethod
    def _extract_title(card: Tag, selector: str | None) -> str:
        if selector:
            el = card.select_one(selector)
            return el.get_text(" ", strip=True) if el else ""
        return card.get_text(" ", strip=True)

    @staticmethod
    def _extract_text(card: Tag, selector: str) -> str | None:
        el = card.select_one(selector)
        return el.get_text(" ", strip=True) if el else None

    @staticmethod
    def _extract_link(card: Tag, selector: str | None, base: str) -> str:
        el: Tag | None
        if selector:
            el = card.select_one(selector)
        elif card.name == "a":
            el = card
        else:
            el = card.select_one("a[href]")
        if not el:
            return ""
        href = el.get("href")
        if not href or not isinstance(href, str):
            return ""
        return urljoin(base + "/", href)
