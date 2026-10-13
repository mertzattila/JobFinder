"""HTML fetching.

Two strategies:
  * ``fetch_static`` — plain ``requests`` for server-rendered pages (fast/cheap).
  * ``fetch_rendered`` — Playwright for JavaScript-heavy pages. Playwright is an
    optional dependency; it is imported lazily so the pipeline still runs without
    it as long as no target sets ``render: true``.
"""

from __future__ import annotations

import logging

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

log = logging.getLogger(__name__)


class Fetcher:
    def __init__(self, user_agent: str, timeout: int = 20) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept-Language": "hu-HU,hu;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def fetch_static(self, url: str) -> str:
        log.info("GET (static) %s", url)
        resp = self.session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        return resp.text

    def fetch_rendered(self, url: str, wait_selector: str | None = None) -> str:
        """Render a page with a headless browser and return its HTML."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "Target requires JS rendering (render: true) but Playwright is not "
                "installed. Install with `pip install playwright && playwright install "
                "chromium`, or set ENABLE_PLAYWRIGHT=1 in the workflow."
            ) from exc

        log.info("GET (rendered) %s", url)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(user_agent=self.session.headers["User-Agent"])
                page.goto(url, timeout=self.timeout * 1000, wait_until="networkidle")
                if wait_selector:
                    try:
                        page.wait_for_selector(wait_selector, timeout=10_000)
                    except Exception:  # noqa: BLE001 - best effort; return what we have
                        log.warning("wait_selector %r not found on %s", wait_selector, url)
                return page.content()
            finally:
                browser.close()
