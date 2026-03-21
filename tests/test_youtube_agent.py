"""
Tests for YouTubeAgent and YouTubeClient.
No network calls. No API key required.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from core.agent_base import TaskResult


class TestYouTubeClient:

    def test_import(self):
        from skills.youtube import YouTubeClient
        client = YouTubeClient()
        assert client is not None

    def test_quota_status_initial(self):
        from skills.youtube import YouTubeClient
        client = YouTubeClient()
        status = client.get_quota_status()
        assert status["used"] == 0
        assert status["limit"] == 10000
        assert status["remaining"] == 10000
        assert status["percentage"] == 0.0

    def test_quota_check_allows_within_limit(self):
        from skills.youtube import YouTubeClient
        client = YouTubeClient()
        assert client._check_quota(100) is True

    def test_quota_check_blocks_over_limit(self):
        from skills.youtube import YouTubeClient
        client = YouTubeClient()
        client._quota_used = 9950
        assert client._check_quota(100) is False

    def test_score_relevance_exact_match(self):
        from skills.youtube import YouTubeClient
        client = YouTubeClient()
        score = client._score_relevance("python programming tutorial", "python")
        assert score > 0.5

    def test_score_relevance_no_match(self):
        from skills.youtube import YouTubeClient
        client = YouTubeClient()
        score = client._score_relevance("cooking recipes", "python programming")
        assert score <= 0.5

    def test_degraded_mode_returns_empty_trending(self):
        from skills.youtube import YouTubeClient
        client = YouTubeClient()
        client.api_key = ""
        result = client._mock_trending("python", 5)
        assert isinstance(result, list)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_search_trending_no_key_returns_empty(self):
        from skills.youtube import YouTubeClient
        client = YouTubeClient()
        client.api_key = ""
        result = await client.search_trending("tecnologia")
        assert isinstance(result, list)
        assert len(result) == 0

    def test_parse_search_results_empty(self):
        from skills.youtube import YouTubeClient
        client = YouTubeClient()
        result = client._parse_search_results({"items": []}, "test")
        assert result == []

    def test_parse_video_metadata(self):
        from skills.youtube import YouTubeClient
        client = YouTubeClient()
        item = {
            "id": "abc123",
            "snippet": {
                "title": "Test Video",
                "description": "Test description",
                "channelId": "ch1",
                "channelTitle": "Test Channel",
                "publishedAt": "2026-03-21T00:00:00Z",
                "tags": ["python", "AI"],
                "thumbnails": {"high": {"url": "http://img.jpg"}},
            },
            "statistics": {"viewCount": "1000", "likeCount": "50"},
            "contentDetails": {"duration": "PT8M30S"},
        }
        meta = client._parse_video_metadata(item)
        assert meta.video_id == "abc123"
        assert meta.title == "Test Video"
        assert meta.view_count == 1000
        assert meta.like_count == 50


class TestYouTubeConfig:

    def test_import(self):
        from core.youtube_config import YOUTUBE_DOMAINS, ScriptConfig
        assert "tech" in YOUTUBE_DOMAINS
        assert "economy" in YOUTUBE_DOMAINS

    def test_script_config_defaults(self):
        from core.youtube_config import ScriptConfig
        sc = ScriptConfig(topic="IA em 2026")
        assert sc.topic == "IA em 2026"
        assert sc.language == "pt-BR"
        assert sc.repurpose_to_blog is True
        assert sc.dry_run is False

    def test_script_sections_complete(self):
        from core.youtube_config import SCRIPT_SECTIONS
        assert "hook" in SCRIPT_SECTIONS
        assert "cta" in SCRIPT_SECTIONS
        assert "outro" in SCRIPT_SECTIONS
        assert len(SCRIPT_SECTIONS) == 7


class TestYouTubeAgent:

    def setup_method(self):
        from core.observability.observer import MoonObserver
        MoonObserver.reset_instance()

    def teardown_method(self):
        from core.observability.observer import MoonObserver
        MoonObserver.reset_instance()

    def test_import(self):
        from agents.youtube_agent import YouTubeAgent
        agent = YouTubeAgent()
        assert agent.AGENT_ID == "youtube"

    @pytest.mark.asyncio
    async def test_execute_unknown_command(self):
        from agents.youtube_agent import YouTubeAgent
        agent = YouTubeAgent()
        result = await agent._execute("invalid_cmd")
        assert result.success is False
        assert "Unknown command" in result.error

    @pytest.mark.asyncio
    async def test_execute_script_requires_topic(self):
        from agents.youtube_agent import YouTubeAgent
        agent = YouTubeAgent()
        result = await agent._execute("script")
        assert result.success is False
        assert "topic" in result.error

    @pytest.mark.asyncio
    async def test_execute_quota(self):
        from agents.youtube_agent import YouTubeAgent
        agent = YouTubeAgent()
        result = await agent._execute("quota")
        assert result.success is True
        assert "remaining" in result.data

    @pytest.mark.asyncio
    async def test_execute_script_dry_run(self):
        from agents.youtube_agent import YouTubeAgent
        agent = YouTubeAgent()
        mock_script = (
            "## HOOK\n[0:00] Você sabia que IA pode...\n"
            "## INTRO\n[0:15] Neste vídeo...\n"
            "## CTA\n[7:30] Curta e inscreva-se!"
        )
        with patch.object(agent.llm, "complete",
                          new_callable=AsyncMock,
                          return_value=mock_script):
            result = await agent._execute(
                "script",
                topic="Inteligência Artificial em 2026",
                domain="tech",
                dry_run=True,
            )
        assert result.success is True
        assert result.data["script"] == mock_script
        assert result.data["topic"] == "Inteligência Artificial em 2026"
        assert result.data["word_count"] > 0

    @pytest.mark.asyncio
    async def test_execute_trending_no_key(self):
        from agents.youtube_agent import YouTubeAgent
        agent = YouTubeAgent()
        result = await agent._execute(
            "trending",
            domain="tech"
        )
        assert result.success is True
        assert "topics" in result.data
        assert isinstance(result.data["topics"], list)

    @pytest.mark.asyncio
    async def test_seo_optimization_dry_run(self):
        from agents.youtube_agent import YouTubeAgent
        agent = YouTubeAgent()
        mock_seo = (
            '{"optimized_title": "IA em 2026: O que esperar",'
            '"description": "Análise completa...",'
            '"tags": ["ia", "tecnologia", "2026"],'
            '"main_keyword": "ia",'
            '"secondary_keywords": ["machine learning"],'
            '"thumbnail_text": "IA 2026"}'
        )
        with patch.object(agent.llm, "complete",
                          new_callable=AsyncMock,
                          return_value=mock_seo):
            result = await agent._execute(
                "seo",
                topic="IA em 2026",
                content="Script sobre IA em 2026 e suas implicações..."
            )
        assert result.success is True
        assert "optimized_title" in result.data
        assert "tags" in result.data

    @pytest.mark.asyncio
    async def test_full_pipeline_dry_run(self):
        from agents.youtube_agent import YouTubeAgent
        agent = YouTubeAgent()

        mock_script = "## HOOK\n[0:00] Test hook\n## CTA\n[7:00] Subscribe!"
        mock_seo = (
            '{"optimized_title": "Test Video",'
            '"description": "Test desc",'
            '"tags": ["test"],'
            '"main_keyword": "test",'
            '"secondary_keywords": [],'
            '"thumbnail_text": "TEST"}'
        )

        with patch.object(agent.llm, "complete",
                          new_callable=AsyncMock,
                          side_effect=[mock_script, mock_seo]), \
             patch.object(agent, "_fetch_trending",
                          new_callable=AsyncMock,
                          return_value=[]):
            result = await agent._execute(
                "pipeline",
                topic="Teste Pipeline YouTube",
                domain="tech",
                dry_run=True,
                notify_telegram=False,
                repurpose_to_blog=False,
            )

        assert result.success is True
        assert "steps" in result.data
        assert "script" in result.data["steps"]
        assert "seo" in result.data["steps"]

    @pytest.mark.asyncio
    async def test_repurpose_blog_to_script(self):
        from agents.youtube_agent import YouTubeAgent
        agent = YouTubeAgent()

        mock_script = "[0:00] Hook sobre IA\n## INTRO..."
        with patch.object(agent.llm, "complete",
                          new_callable=AsyncMock,
                          return_value=mock_script):
            result = await agent._execute(
                "repurpose",
                topic="IA em 2026",
                content="Post do blog sobre inteligência artificial em 2026..."
            )
        assert result.success is True
        assert "script" in result.data
        assert result.data["source"] == "blog_repurpose"

    @pytest.mark.asyncio
    async def test_repurpose_requires_content(self):
        from agents.youtube_agent import YouTubeAgent
        agent = YouTubeAgent()
        result = await agent._execute("repurpose", topic="Test")
        assert result.success is False
        assert "content" in result.error
