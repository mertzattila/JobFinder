"""Alerting via Discord webhook or Telegram bot.

A notification contains the job title, company, match score, the LLM's
two-sentence summary, and the direct application URL.
"""

from __future__ import annotations

import logging

import requests

from jobfinder.config import NotifierConfig, Secrets
from jobfinder.models import ScoredJob

log = logging.getLogger(__name__)


class Notifier:
    def __init__(self, cfg: NotifierConfig, secrets: Secrets) -> None:
        self.cfg = cfg
        self.secrets = secrets

    def send(self, scored: ScoredJob) -> bool:
        if self.cfg.channel == "discord":
            return self._send_discord(scored)
        if self.cfg.channel == "telegram":
            return self._send_telegram(scored)
        raise ValueError(f"Unknown notifier channel: {self.cfg.channel!r}")

    def _send_discord(self, scored: ScoredJob) -> bool:
        if not self.secrets.discord_webhook_url:
            log.error("DISCORD_WEBHOOK_URL not set; cannot notify")
            return False
        job, match = scored.job, scored.match
        embed = {
            "title": f"🎯 {job.title}",
            "url": job.url,
            "color": 0x2ECC71 if match.score >= 8 else 0xF1C40F,
            "fields": [
                {"name": "Company", "value": job.company, "inline": True},
                {"name": "Match Score", "value": f"{match.score}/10", "inline": True},
                {"name": "Location", "value": job.location or "—", "inline": True},
                {"name": "Why it fits", "value": match.summary, "inline": False},
                {"name": "Apply", "value": job.url, "inline": False},
            ],
            "footer": {"text": f"JobFinder · source: {job.source}"},
        }
        resp = requests.post(
            self.secrets.discord_webhook_url,
            json={"embeds": [embed]},
            timeout=20,
        )
        ok = resp.status_code in (200, 204)
        if not ok:
            log.error("Discord webhook failed: %s %s", resp.status_code, resp.text[:200])
        return ok

    def _send_telegram(self, scored: ScoredJob) -> bool:
        token = self.secrets.telegram_bot_token
        chat_id = self.secrets.telegram_chat_id
        if not token or not chat_id:
            log.error("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set; cannot notify")
            return False
        job, match = scored.job, scored.match
        text = (
            f"🎯 <b>{_esc(job.title)}</b>\n"
            f"🏢 {_esc(job.company)}  |  ⭐ {match.score}/10\n"
            f"📍 {_esc(job.location or '—')}\n\n"
            f"{_esc(match.summary)}\n\n"
            f'🔗 <a href="{job.url}">Apply here</a>'
        )
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            },
            timeout=20,
        )
        ok = resp.ok
        if not ok:
            log.error("Telegram send failed: %s %s", resp.status_code, resp.text[:200])
        return ok


def _esc(s: str) -> str:
    """Escape the characters Telegram's HTML parse mode is sensitive to."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
