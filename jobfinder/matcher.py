"""LLM-based CV matching.

Sends the candidate profile + a job description to an LLM and asks for a
structured verdict (score 1-10, two-sentence summary). We request JSON output
and validate it with the ``MatchResult`` Pydantic model so malformed responses
are caught rather than silently mis-notified.

Supports Google Gemini and OpenAI via their REST APIs using only ``requests``
(no vendor SDK needed). Pick the provider in config.yaml (llm.provider).
"""

from __future__ import annotations

import json
import logging

import requests
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from jobfinder.config import LLMConfig, Secrets
from jobfinder.models import JobPosting, MatchResult

log = logging.getLogger(__name__)


class _NonRetryableError(RuntimeError):
    """Raised for permanent API errors (bad key/model/request) that retrying
    would not fix, so the pipeline skips the job immediately instead of
    burning the full backoff schedule."""


class QuotaExceededError(RuntimeError):
    """Raised when the LLM API returns 429 (rate limit / quota exhausted) even
    after retries. Signals the pipeline to STOP the whole run early rather than
    hammer the API for every remaining job — the quota won't recover mid-run."""

_SYSTEM_INSTRUCTION = (
    "You are a technical recruiter evaluating how well a job posting matches a "
    "candidate's profile. Be strict and realistic. A high score (8-10) means the "
    "role is clearly an embedded/hardware software internship aligned with the "
    "candidate's stack. A low score (1-3) means it is unrelated, senior-only, or "
    "not an internship. Judge on: embedded/hardware focus, internship/student "
    "eligibility, and overlap with the candidate's languages and project experience."
)

# JSON schema shared by both providers for structured output.
_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "minimum": 1, "maximum": 10},
        "summary": {"type": "string"},
        "recommended": {"type": "string", "enum": ["yes", "no", "maybe"]},
    },
    "required": ["score", "summary", "recommended"],
}


def _build_prompt(profile: str, job: JobPosting, max_chars: int) -> str:
    desc = job.description[:max_chars]
    return (
        f"CANDIDATE PROFILE:\n{profile}\n\n"
        f"JOB POSTING:\n"
        f"Title: {job.title}\n"
        f"Company: {job.company}\n"
        f"Location: {job.location or 'n/a'}\n"
        f"Description: {desc}\n\n"
        "Return a JSON object with:\n"
        '  "score": integer 1-10 (match quality),\n'
        '  "summary": exactly two sentences explaining WHY it fits (or does not),\n'
        '  "recommended": "yes" | "no" | "maybe".'
    )


class Matcher:
    def __init__(self, cfg: LLMConfig, secrets: Secrets, profile: str) -> None:
        self.cfg = cfg
        self.secrets = secrets
        self.profile = profile

    def evaluate(self, job: JobPosting) -> MatchResult:
        prompt = _build_prompt(self.profile, job, self.cfg.max_description_chars)
        if self.cfg.provider == "gemini":
            raw = self._call_gemini(prompt)
        elif self.cfg.provider == "openai":
            raw = self._call_openai(prompt)
        else:
            raise ValueError(f"Unknown LLM provider: {self.cfg.provider!r}")
        data = json.loads(raw)
        return MatchResult(**data)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=30),
        retry=retry_if_not_exception_type((_NonRetryableError, QuotaExceededError)),
    )
    def _call_gemini(self, prompt: str) -> str:
        if not self.secrets.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.cfg.model}:generateContent"
        )
        payload = {
            "systemInstruction": {"parts": [{"text": _SYSTEM_INSTRUCTION}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": _RESPONSE_SCHEMA,
                "temperature": 0.2,
            },
        }
        resp = requests.post(
            url,
            params={"key": self.secrets.gemini_api_key},
            json=payload,
            timeout=60,
        )
        # 429 = rate limit / quota exhausted. Fail fast with a dedicated error so
        # the pipeline can stop the whole run instead of retrying every job — the
        # free-tier quota will not recover within a single run.
        if resp.status_code == 429:
            raise QuotaExceededError(resp.text[:200])
        # Other 4xx (bad key/model/request) won't fix itself either; don't retry.
        if 400 <= resp.status_code < 500:
            raise _NonRetryableError(f"{resp.status_code}: {resp.text[:200]}")
        resp.raise_for_status()
        body = resp.json()
        return body["candidates"][0]["content"]["parts"][0]["text"]

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=30),
        retry=retry_if_not_exception_type((_NonRetryableError, QuotaExceededError)),
    )
    def _call_openai(self, prompt: str) -> str:
        if not self.secrets.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.secrets.openai_api_key}"},
            json={
                "model": self.cfg.model,
                "messages": [
                    {"role": "system", "content": _SYSTEM_INSTRUCTION},
                    {"role": "user", "content": prompt},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.2,
            },
            timeout=60,
        )
        if resp.status_code == 429:
            raise QuotaExceededError(resp.text[:200])
        if 400 <= resp.status_code < 500:
            raise _NonRetryableError(f"{resp.status_code}: {resp.text[:200]}")
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
