"""
skills/youtube — YouTube Data API v3 client (free tier).
Quota: 10.000 units/day. Search=100u, Insert=1600u, List=1u.
"""
from skills.youtube.youtube_client import YouTubeClient

__all__ = ["YouTubeClient"]
