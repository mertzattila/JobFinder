"""Loads the candidate CV / profile text used by the LLM matcher."""

from __future__ import annotations

from pathlib import Path

# Fallback profile used if profile.md is missing. Edit profile.md instead of this.
DEFAULT_PROFILE = """\
5th-semester Electrical Engineering university student in Budapest, Hungary,
specializing in embedded software development. Actively seeking internship
("gyakornok" / "intern") positions.

Technical stack: C, C++, Python, Verilog, Assembly, Arduino, ESP32.
Hands-on experience with hardware projects and telemetry systems.
"""


def load_profile(path: str | Path = "profile.md") -> str:
    p = Path(path)
    if p.exists():
        text = p.read_text(encoding="utf-8").strip()
        if text:
            return text
    return DEFAULT_PROFILE.strip()
