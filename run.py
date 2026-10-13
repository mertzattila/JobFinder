#!/usr/bin/env python3
"""JobFinder entry point.

Usage:
    python run.py                 # normal run (scrape, match, notify)
    python run.py --dry-run       # scrape + match + log, but do NOT send alerts
    python run.py --config x.yaml # use a different config file
"""

from __future__ import annotations

import argparse
import logging
import sys

from jobfinder.config import Secrets, load_settings
from jobfinder.pipeline import Pipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="JobFinder daily scraper")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--profile", default="profile.md")
    parser.add_argument("--state", default="seen_jobs.json")
    parser.add_argument("--dry-run", action="store_true", help="do not send notifications")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    settings = load_settings(args.config)
    secrets = Secrets.from_env()
    pipeline = Pipeline(
        settings=settings,
        secrets=secrets,
        profile_path=args.profile,
        state_path=args.state,
        dry_run=args.dry_run,
    )
    alerted = pipeline.run()
    print(f"\n✅ Done. {len(alerted)} job(s) scored above the threshold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
