"""
Unit tests for radar scanner skills — all HTTP mocked.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from skills.radar import RadarItem
from skills.radar.github_trending import scan_github_trending
from skills.radar.huggingface_scanner import scan_huggingface_models, scan_huggingface_spaces
from skills.radar.rss_scanner import scan_rss_feeds, RADAR_FEEDS
from skills.radar.llm_releases_scanner import scan_openrouter_free_models, scan_groq_models
from skills.radar.pypi_scanner import scan_pypi_new_packages


class TestRadarItem:
    def test_hash_generated_on_init(self):
        item = RadarItem(source="s", title="t", description="d", url="u")
        assert len(item.item_hash) == 16

    def test_same_inputs_same_hash(self):
        a = RadarItem(source="s", title="t", description="d", url="u")
        b = RadarItem(source="s", title="t", description="d", url="u")
        assert a.item_hash == b.item_hash

    def test_different_urls_different_hash(self):
        a = RadarItem(source="s", title="t", description="d", url="u1")
        b = RadarItem(source="s", title="t", description="d", url="u2")
        assert a.item_hash != b.item_hash

    def test_explicit_hash_not_overwritten(self):
        item = RadarItem(source="s", title="t", description="d", url="u", item_hash="custom")
        assert item.item_hash == "custom"


class TestGithubTrending:
    def test_returns_empty_on_error(self):
        async def run():
            with patch("httpx.AsyncClient") as mock:
                mock.return_value.__aenter__ = AsyncMock(return_value=mock.return_value)
                mock.return_value.__aexit__ = AsyncMock(return_value=False)
                mock.return_value.get = AsyncMock(side_effect=Exception("network"))
                return await scan_github_trending()
        assert asyncio.run(run()) == []

    def test_parses_valid_response(self):
        async def run():
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {"items": [
                {"full_name": "u/r", "description": "desc", "html_url": "https://github.com/u/r", "created_at": ""}
            ]}
            with patch("httpx.AsyncClient") as mock:
                mock.return_value.__aenter__ = AsyncMock(return_value=mock.return_value)
                mock.return_value.__aexit__ = AsyncMock(return_value=False)
                mock.return_value.get = AsyncMock(return_value=mock_resp)
                return await scan_github_trending()
        result = asyncio.run(run())
        assert len(result) == 1
        assert result[0].category == "code_repository"


class TestRssScanner:
    def test_known_feeds_configured(self):
        assert "hacker_news_top" in RADAR_FEEDS
        assert "arxiv_ai" in RADAR_FEEDS
        assert "huggingface_blog" in RADAR_FEEDS

    def test_unknown_key_returns_empty(self):
        assert asyncio.run(scan_rss_feeds(feed_keys=["nonexistent_xyz"])) == []

    def test_returns_empty_on_parse_error(self):
        async def run():
            with patch("feedparser.parse", side_effect=Exception("parse error")):
                return await scan_rss_feeds(feed_keys=["hacker_news_top"])
        assert asyncio.run(run()) == []


class TestLlmScanners:
    def test_openrouter_returns_empty_on_error(self):
        async def run():
            with patch("httpx.AsyncClient") as mock:
                mock.return_value.__aenter__ = AsyncMock(return_value=mock.return_value)
                mock.return_value.__aexit__ = AsyncMock(return_value=False)
                mock.return_value.get = AsyncMock(side_effect=Exception("err"))
                return await scan_openrouter_free_models()
        assert asyncio.run(run()) == []

    def test_groq_skipped_without_token(self, monkeypatch):
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        assert asyncio.run(scan_groq_models()) == []


class TestPypiScanner:
    def test_keyword_filtering(self):
        async def run():
            fake = MagicMock()
            fake.entries = [
                MagicMock(title="llm-tools 1.0", summary="LLM utility", link="https://pypi.org/p/llm-tools", published=""),
                MagicMock(title="csv-reader 2.0", summary="CSV utilities only here", link="https://pypi.org/p/csv", published=""),
            ]
            with patch("feedparser.parse", return_value=fake):
                return await scan_pypi_new_packages(keywords=["llm"])
        result = asyncio.run(run())
        assert len(result) == 1
        assert "llm-tools" in result[0].title
