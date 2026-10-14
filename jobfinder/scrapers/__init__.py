"""Scrapers package."""

from jobfinder.scrapers.base import BaseScraper
from jobfinder.scrapers.generic import GenericScraper
from jobfinder.scrapers.greenhouse import GreenhouseScraper
from jobfinder.scrapers.phenom import PhenomScraper

__all__ = ["BaseScraper", "GenericScraper", "GreenhouseScraper", "PhenomScraper"]
