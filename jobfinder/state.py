"""Lightweight state store for tracking already-seen jobs.

Persists a JSON file (``seen_jobs.json``) mapping each job fingerprint to the
timestamp it was first seen. The GitHub Actions workflow commits this file back
to the repository after each run, so you are never notified about the same job
twice.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class SeenStore:
    def __init__(self, path: str | Path = "seen_jobs.json") -> None:
        self.path = Path(path)
        self._seen: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                self._seen = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._seen = {}

    def is_seen(self, fingerprint: str) -> bool:
        return fingerprint in self._seen

    def mark_seen(self, fingerprint: str) -> None:
        self._seen.setdefault(fingerprint, datetime.now(timezone.utc).isoformat())

    def save(self) -> None:
        self.path.write_text(
            json.dumps(self._seen, indent=2, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )

    def __len__(self) -> int:
        return len(self._seen)
