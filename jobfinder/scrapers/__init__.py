"""Scrapers package."""

from jobfinder.scrapers.base import BaseScraper
from jobfinder.scrapers.generic import GenericScraper
from jobfinder.scrapers.greenhouse import GreenhouseScraper
from jobfinder.scrapers.phenom import PhenomScraper
from jobfinder.scrapers.recruiterbox import RecruiterBoxScraper

__all__ = [
    "BaseScraper",
    "GenericScraper",
    "GreenhouseScraper",
    "PhenomScraper",
    "RecruiterBoxScraper",
]
