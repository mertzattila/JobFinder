"""Scraper interface.

Subclass ``BaseScraper`` to add bespoke parsing for a site whose markup the
generic CSS-selector scraper cannot handle. Register the subclass in
``pipeline.build_scraper`` if you add one.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from jobfinder.config import TargetConfig
from jobfinder.fetcher import Fetcher
from jobfinder.models import JobPosting


class BaseScraper(ABC):
    def __init__(self, target: TargetConfig, fetcher: Fetcher) -> None:
        self.target = target
        self.fetcher = fetcher

    @abstractmethod
    def scrape(self) -> list[JobPosting]:
        """Return the job postings found on the target page."""
        raise NotImplementedError
