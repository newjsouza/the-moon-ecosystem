"""
YouTubeClient — YouTube Data API v3 wrapper.
Free tier: 10.000 units/day.
  - search.list:   100 units
  - videos.list:     1 unit
  - videos.insert: 1600 units
  - channels.list:   1 unit

Requires: YOUTUBE_API_KEY (Data API — read-only)
Optional: YOUTUBE_OAUTH_CREDENTIALS (for upload — OAuth2)
"""
import os
import logging
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class VideoMetadata:
    """Structured metadata for a YouTube video."""
    video_id: str
    title: str
    description: str
    channel_id: str
    channel_title: str
    published_at: str
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    duration: str = ""
    tags: list = field(default_factory=list)
    thumbnail_url: str = ""


@dataclass
class TrendingTopic:
    """A trending topic extracted from YouTube."""
    title: str
    video_id: str
    view_count: int
    channel_title: str
    relevance_score: float = 0.0
    keywords: list = field(default_factory=list)


class YouTubeClient:
    """
    Async YouTube Data API v3 client.
    Handles quota tracking, caching, and graceful degradation.
    """

    API_BASE = "https://www.googleapis.com/youtube/v3"
    QUOTA_DAILY_LIMIT = 10000

    def __init__(self):
        self.api_key = os.environ.get("YOUTUBE_API_KEY", "")
        self.logger = logging.getLogger(self.__class__.__name__)
        self._quota_used = 0
        self._cache: dict = {}

        if not self.api_key:
            self.logger.warning(
                "YOUTUBE_API_KEY not set — YouTubeClient in degraded mode"
            )

    def _check_quota(self, cost: int) -> bool:
        """Check if quota allows the operation."""
        if self._quota_used + cost > self.QUOTA_DAILY_LIMIT:
            self.logger.error(
                f"Quota exceeded: {self._quota_used}/{self.QUOTA_DAILY_LIMIT} "
                f"(needs {cost} more units)"
            )
            return False
        return True

    async def search_trending(
        self,
        query: str,
        max_results: int = 10,
        region_code: str = "BR",
        relevance_language: str = "pt",
        order: str = "viewCount",
    ) -> list:
        """
        Search trending videos on YouTube.
        Cost: 100 units per call.
        """
        if not self.api_key:
            return self._mock_trending(query, max_results)

        if not self._check_quota(100):
            return []

        import aiohttp

        params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "order": order,
            "maxResults": max_results,
            "regionCode": region_code,
            "relevanceLanguage": relevance_language,
            "key": self.api_key,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.API_BASE}/search",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    self._quota_used += 100
                    return self._parse_search_results(data, query)
        except Exception as e:
            self.logger.error(f"search_trending failed: {e}")
            return []

    async def get_video_stats(self, video_id: str) -> Optional[VideoMetadata]:
        """
        Get video statistics and metadata.
        Cost: 1 unit per call.
        """
        if not self.api_key:
            return None

        if not self._check_quota(1):
            return None

        cache_key = f"stats:{video_id}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        import aiohttp

        params = {
            "part": "snippet,statistics,contentDetails",
            "id": video_id,
            "key": self.api_key,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.API_BASE}/videos",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    self._quota_used += 1

                    items = data.get("items", [])
                    if not items:
                        return None

                    meta = self._parse_video_metadata(items[0])
                    self._cache[cache_key] = meta
                    return meta
        except Exception as e:
            self.logger.error(f"get_video_stats failed: {e}")
            return None

    async def get_channel_info(self, channel_id: str) -> dict:
        """
        Get channel statistics.
        Cost: 1 unit per call.
        """
        if not self.api_key or not self._check_quota(1):
            return {}

        import aiohttp

        params = {
            "part": "snippet,statistics",
            "id": channel_id,
            "key": self.api_key,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.API_BASE}/channels",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    self._quota_used += 1
                    items = data.get("items", [])
                    if not items:
                        return {}
                    stats = items[0].get("statistics", {})
                    snippet = items[0].get("snippet", {})
                    return {
                        "channel_id": channel_id,
                        "title": snippet.get("title", ""),
                        "description": snippet.get("description", "")[:300],
                        "subscriber_count": int(stats.get("subscriberCount", 0)),
                        "video_count": int(stats.get("videoCount", 0)),
                        "view_count": int(stats.get("viewCount", 0)),
                    }
        except Exception as e:
            self.logger.error(f"get_channel_info failed: {e}")
            return {}

    def get_quota_status(self) -> dict:
        """Return current quota usage."""
        return {
            "used": self._quota_used,
            "limit": self.QUOTA_DAILY_LIMIT,
            "remaining": self.QUOTA_DAILY_LIMIT - self._quota_used,
            "percentage": round(self._quota_used / self.QUOTA_DAILY_LIMIT * 100, 1),
        }

    def _parse_search_results(self, data: dict, query: str) -> list:
        """Parse YouTube search API response into TrendingTopic list."""
        topics = []
        for item in data.get("items", []):
            snippet = item.get("snippet", {})
            video_id = item.get("id", {}).get("videoId", "")
            if not video_id:
                continue

            title = snippet.get("title", "")
            keywords = [
                w.lower() for w in title.split()
                if len(w) > 3 and w.lower() not in
                {"para", "como", "esse", "esta", "uma", "com"}
            ]

            topics.append(TrendingTopic(
                title=title,
                video_id=video_id,
                view_count=0,
                channel_title=snippet.get("channelTitle", ""),
                relevance_score=self._score_relevance(title, query),
                keywords=keywords[:8],
            ))
        return topics

    def _parse_video_metadata(self, item: dict) -> VideoMetadata:
        """Parse YouTube videos API item into VideoMetadata."""
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        details = item.get("contentDetails", {})

        thumbnails = snippet.get("thumbnails", {})
        thumb = (thumbnails.get("maxres") or
                 thumbnails.get("high") or
                 thumbnails.get("default") or {})

        return VideoMetadata(
            video_id=item.get("id", ""),
            title=snippet.get("title", ""),
            description=snippet.get("description", "")[:500],
            channel_id=snippet.get("channelId", ""),
            channel_title=snippet.get("channelTitle", ""),
            published_at=snippet.get("publishedAt", ""),
            view_count=int(stats.get("viewCount", 0)),
            like_count=int(stats.get("likeCount", 0)),
            comment_count=int(stats.get("commentCount", 0)),
            duration=details.get("duration", ""),
            tags=snippet.get("tags", [])[:10],
            thumbnail_url=thumb.get("url", ""),
        )

    def _score_relevance(self, title: str, query: str) -> float:
        """Simple relevance score based on query word overlap."""
        query_words = set(query.lower().split())
        title_words = set(title.lower().split())
        if not query_words:
            return 0.5
        overlap = len(query_words & title_words)
        return min(1.0, overlap / len(query_words) + 0.3)

    def _mock_trending(self, query: str, n: int) -> list:
        """Degraded mode: return empty list with warning."""
        self.logger.warning(
            "YouTubeClient in degraded mode (no API key) — "
            "returning empty trending list"
        )
        return []
