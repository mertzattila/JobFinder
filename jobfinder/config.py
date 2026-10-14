"""Configuration loading.

Non-secret settings (target URLs, selectors, keywords, thresholds) live in
``config.yaml`` so you can tweak them without touching code. Secrets (API keys,
webhook URLs) are read from environment variables, which GitHub Actions injects
from repository secrets.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class TargetConfig(BaseModel):
    """One scrape target (a career page or job board)."""

    name: str
    company: str
    url: str
    enabled: bool = True
    render: bool = False  # True => use Playwright (JS-rendered page)

    # Which scraper to use. "generic" = config-driven CSS scraper (default);
    # "phenom" = JSON API scraper for Phenom People career sites (jobs.<co>.com).
    scraper: str = "generic"

    # Extra params for API-based scrapers (e.g. phenom): the search endpoint and
    # a location filter. Ignored by the generic scraper.
    api_url: str | None = None
    location_filter: str | None = None

    # CSS selectors for the generic scraper. Optional for API-based scrapers.
    job_card: str = Field(default="", description="Selector matching each job listing element")
    title: str | None = None  # selector relative to job_card; None => use card text
    link: str | None = None  # selector for the <a>; None => card is/contains the <a>
    location: str | None = None
    base_url: str | None = None  # for resolving relative links; defaults to url's origin


class LLMConfig(BaseModel):
    provider: str = "gemini"  # "gemini" or "openai"
    model: str = "gemini-1.5-flash"
    max_description_chars: int = 6000


class NotifierConfig(BaseModel):
    channel: str = "discord"  # "discord" or "telegram"


class Settings(BaseModel):
    keywords: list[str]
    score_threshold: int = 7
    request_timeout: int = 20
    request_delay_seconds: float = 1.0
    # Pause between LLM calls to stay under free-tier per-minute rate limits.
    llm_request_delay_seconds: float = 6.0
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
    llm: LLMConfig = LLMConfig()
    notifier: NotifierConfig = NotifierConfig()
    targets: list[TargetConfig] = []


class Secrets(BaseModel):
    """Resolved from environment variables."""

    gemini_api_key: str | None = None
    openai_api_key: str | None = None
    discord_webhook_url: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

    @classmethod
    def from_env(cls) -> Secrets:
        return cls(
            gemini_api_key=os.getenv("GEMINI_API_KEY"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            discord_webhook_url=os.getenv("DISCORD_WEBHOOK_URL"),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID"),
        )


def load_settings(path: str | Path = "config.yaml") -> Settings:
    data: dict[str, Any] = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return Settings(**data)
