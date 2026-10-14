"""Pipeline orchestrator: scrape -> filter -> match -> notify -> persist state."""

from __future__ import annotations

import logging
import time

from jobfinder.config import Secrets, Settings, TargetConfig
from jobfinder.fetcher import Fetcher
from jobfinder.matcher import Matcher, QuotaExceededError
from jobfinder.models import JobPosting, ScoredJob
from jobfinder.notifier import Notifier
from jobfinder.profile import load_profile
from jobfinder.scrapers import (
    BaseScraper,
    GenericScraper,
    GreenhouseScraper,
    PhenomScraper,
)
from jobfinder.state import SeenStore

log = logging.getLogger(__name__)


def build_scraper(target: TargetConfig, fetcher: Fetcher) -> BaseScraper:
    """Factory for scrapers. Picks the scraper by target.scraper: "generic"
    (default CSS scraper), "phenom" (Phenom People JSON API, e.g. Infineon),
    or "greenhouse" (Greenhouse boards JSON API, e.g. Formlabs)."""
    if target.scraper == "phenom":
        return PhenomScraper(target, fetcher)
    if target.scraper == "greenhouse":
        return GreenhouseScraper(target, fetcher)
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
        for i, job in enumerate(new_jobs):
            # Mark seen up front so a failed LLM/notify call doesn't cause an
            # endless retry loop across daily runs.
            self.store.mark_seen(job.fingerprint)
            try:
                match = self.matcher.evaluate(job)
            except QuotaExceededError:
                # Quota won't recover mid-run — stop immediately with a clear
                # message instead of hammering the API for every remaining job.
                # Jobs already marked seen will be skipped next run; unprocessed
                # ones below stay unseen and get picked up when quota resets.
                self.store.discard(job.fingerprint)
                log.error(
                    "LLM quota/rate limit hit (HTTP 429) after %d job(s). Stopping "
                    "this run; the remaining %d job(s) will be retried next run. "
                    "Free-tier Gemini has low daily/per-minute limits — wait for the "
                    "quota to reset or lower the number of enabled targets.",
                    i,
                    len(new_jobs) - i,
                )
                break
            except Exception:  # noqa: BLE001 - one bad job shouldn't kill the run
                log.exception("LLM evaluation failed for %s", job.url)
                continue

            # Be gentle on free-tier rate limits: small pause between LLM calls.
            time.sleep(self.settings.llm_request_delay_seconds)

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
