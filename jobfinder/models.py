"""Pydantic data models shared across the pipeline.

These give us structured, validated objects for scraped jobs and for the
LLM's evaluation output, so the rest of the code never deals with raw dicts.
"""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class JobPosting(BaseModel):
    """A single job advert discovered by a scraper."""

    title: str
    company: str
    url: str
    location: str | None = None
    description: str = ""
    source: str = Field(default="", description="Which scraper/source produced this")

    @field_validator("title", "company", mode="before")
    @classmethod
    def _strip(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v

    @property
    def fingerprint(self) -> str:
        """Stable ID used for de-duplication.

        We key on the URL (normalised) because the same job can have slightly
        different titles across refreshes. Falls back to title+company.
        """
        basis = self.url.strip().lower().rstrip("/") or f"{self.title}|{self.company}".lower()
        return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


class MatchResult(BaseModel):
    """The LLM's assessment of how well a job fits the candidate."""

    score: int = Field(..., ge=1, le=10, description="Match score from 1 (poor) to 10 (perfect)")
    summary: str = Field(..., description="Two-sentence explanation of the fit")
    recommended: Literal["yes", "no", "maybe"] = "maybe"

    @field_validator("score", mode="before")
    @classmethod
    def _coerce_score(cls, v: object) -> object:
        # LLMs sometimes return "8/10" or 8.0; normalise to a clamped int.
        if isinstance(v, str):
            v = v.split("/")[0].strip()
        try:
            iv = round(float(v))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return v
        return max(1, min(10, iv))


class ScoredJob(BaseModel):
    """A job paired with its match result, ready for notification."""

    job: JobPosting
    match: MatchResult
