"""
Sports skills module for The Moon ecosystem.
Exports the main client for sports data access.
"""
from .api_client import FootballDataClient
from .manager import SportsManager

__all__ = ["FootballDataClient", "SportsManager"]