"""Pipeline orchestrator: scrape -> filter -> match -> notify -> persist state."""

from __future__ import annotations

import logging
import time

from jobfinder.config import Secrets, Settings, TargetConfig
from jobfinder.fetcher import Fetcher
from jobfinder.matcher import Matcher
from jobfinder.models import JobPosting, ScoredJob
from jobfinder.notifier import Notifier
from jobfinder.profile import load_profile
from jobfinder.scrapers import BaseScraper, GenericScraper
from jobfinder.state import SeenStore

log = logging.getLogger(__name__)


def build_scraper(target: TargetConfig, fetcher: Fetcher) -> BaseScraper:
    """Factory for scrapers. Add bespoke scrapers here keyed on target.name."""
    return GenericScraper(target, fetcher)


def keyword_match(job: JobPosting, keywords: list[str]) -> bool:
    """Cheap pre-filter so we only spend LLM calls on plausible jobs."""
    haystack = f"{job.title} {job.description}".lower()
    return any(kw.lower() in haystack for kw in keywords)


class Pipeline:
    def __init__(
        self,
        settings: Settings,
        secrets: Secrets,
        profile_path: str = "profile.md",
        state_path: str = "seen_jobs.json",
        dry_run: bool = False,
    ) -> None:
        self.settings = settings
        self.secrets = secrets
        self.dry_run = dry_run
        self.fetcher = Fetcher(settings.user_agent, settings.request_timeout)
        self.store = SeenStore(state_path)
        self.profile = load_profile(profile_path)
        self.matcher = Matcher(settings.llm, secrets, self.profile)
        self.notifier = Notifier(settings.notifier, secrets)

    def run(self) -> list[ScoredJob]:
        new_jobs = self._collect_new_jobs()
        log.info("Collected %d new keyword-matching jobs", len(new_jobs))

        alerted: list[ScoredJob] = []
        for job in new_jobs:
            # Mark seen up front so a failed LLM/notify call doesn't cause an
            # endless retry loop across daily runs.
            self.store.mark_seen(job.fingerprint)
            try:
                match = self.matcher.evaluate(job)
            except Exception:  # noqa: BLE001 - one bad job shouldn't kill the run
                log.exception("LLM evaluation failed for %s", job.url)
                continue

            log.info("Scored %s/10: %s @ %s", match.score, job.title, job.company)
            if match.score >= self.settings.score_threshold:
                scored = ScoredJob(job=job, match=match)
                if self.dry_run:
                    log.info("[dry-run] would notify: %s", job.url)
                elif self.notifier.send(scored):
                    log.info("Notified: %s", job.url)
                alerted.append(scored)

        self.store.save()
        log.info("Run complete. %d alerts. %d jobs tracked.", len(alerted), len(self.store))
        return alerted

    def _collect_new_jobs(self) -> list[JobPosting]:
        new_jobs: list[JobPosting] = []
        seen_fps: set[str] = set()
        for target in self.settings.targets:
            if not target.enabled:
                continue
            try:
                scraper = build_scraper(target, self.fetcher)
                jobs = scraper.scrape()
            except Exception:  # noqa: BLE001 - a broken target shouldn't kill the run
                log.exception("Scraping failed for target %s", target.name)
                continue

            for job in jobs:
                fp = job.fingerprint
                if fp in seen_fps or self.store.is_seen(fp):
                    continue
                if not keyword_match(job, self.settings.keywords):
                    continue
                seen_fps.add(fp)
                new_jobs.append(job)

            time.sleep(self.settings.request_delay_seconds)  # be polite between sites
        return new_jobs
