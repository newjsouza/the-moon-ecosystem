"""Testes unitários para WebMCPAgent — sem I/O real (mocks)."""
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
import pytest

from agents.webmcp_agent import WebMCPAgent
from skills.webmcp.schemas import WebPage, SearchResult
from skills.webmcp.fetcher import needs_browser
from skills.webmcp.extractor import parse_html


# ── Fixtures ──────────────────────────────────────────────────

FAKE_HTML = """<html><head><title>Test Page</title></head>
<body><p>Hello Moon</p><a href="https://example.com">link</a></body></html>"""

FAKE_SEARCH = SearchResult(
    query="test",
    results=[
        {"title": "Result 1", "url": "https://example.com", "snippet": "snippet 1"},
        {"title": "Result 2", "url": "https://other.com", "snippet": "snippet 2"},
    ],
    total_found=2,
)

FAKE_PAGE = WebPage(
    url="https://example.com",
    title="Test Page",
    content="Hello Moon",
    links=["https://example.com"],
    fetched_at="2026-03-17T00:00:00+00:00",
)


# ── Testes: schemas ───────────────────────────────────────────

def test_webpage_defaults():
    p = WebPage(url="http://x.com", title="X", content="c")
    assert p.links == []
    assert p.rendered is False


def test_searchresult_defaults():
    sr = SearchResult(query="q")
    assert sr.results == []
    assert sr.source == "duckduckgo"


# ── Testes: extractor ─────────────────────────────────────────

def test_parse_html_extracts_title():
    page = parse_html("http://test.com", FAKE_HTML)
    assert page.title == "Test Page"


def test_parse_html_extracts_content():
    page = parse_html("http://test.com", FAKE_HTML)
    assert "Hello Moon" in page.content


def test_parse_html_extracts_links():
    page = parse_html("http://test.com", FAKE_HTML)
    assert "https://example.com" in page.links


def test_parse_html_truncates_content():
    big_html = "<html><body>" + "x" * 20000 + "</body></html>"
    page = parse_html("http://test.com", big_html)
    assert len(page.content) <= 8000


# ── Testes: fetcher.needs_browser ────────────────────────────

def test_needs_browser_twitter():
    assert needs_browser("https://twitter.com/elonmusk") is True


def test_needs_browser_instagram():
    assert needs_browser("https://www.instagram.com/nasa/") is True


def test_needs_browser_simple_site():
    assert needs_browser("https://python.org") is False


def test_needs_browser_news_site():
    assert needs_browser("https://g1.globo.com/noticia") is False


# ── Testes: WebMCPAgent._execute ─────────────────────────────

@pytest.mark.asyncio
async def test_execute_search_mode():
    agent = WebMCPAgent()
    with patch(
        "skills.webmcp.search_engine.search_duckduckgo",
        new_callable=AsyncMock,
        return_value=FAKE_SEARCH,
    ):
        result = await agent._execute("search:python async")
    assert result.success is True
    assert result.data["mode"] == "search"
    assert result.data["total_found"] == 2


@pytest.mark.asyncio
async def test_execute_free_text_is_search():
    agent = WebMCPAgent()
    with patch(
        "skills.webmcp.search_engine.search_duckduckgo",
        new_callable=AsyncMock,
        return_value=FAKE_SEARCH,
    ):
        result = await agent._execute("noticias Bitcoin hoje")
    assert result.success is True
    assert result.data["mode"] == "search"


@pytest.mark.asyncio
async def test_execute_fetch_mode():
    agent = WebMCPAgent()
    with patch("skills.webmcp.fetcher.fetch_page", new_callable=AsyncMock, return_value=FAKE_PAGE):
        result = await agent._execute("fetch:https://example.com")
    assert result.success is True
    assert result.data["mode"] == "fetch"
    assert result.data["title"] == "Test Page"


@pytest.mark.asyncio
async def test_execute_fetch_js_heavy_delegates():
    agent = WebMCPAgent()
    with patch.object(agent, "_delegate_to_browser_pilot", new_callable=AsyncMock) as mock_del:
        mock_del.return_value = {"mode": "deep_via_browser_pilot", "url": "https://twitter.com/x"}
        result = await agent._execute("fetch:https://twitter.com/x")
    assert result.success is True
    mock_del.assert_called_once_with("https://twitter.com/x")


@pytest.mark.asyncio
async def test_execute_search_and_fetch():
    agent = WebMCPAgent()
    with patch(
        "skills.webmcp.search_engine.search_duckduckgo",
        new_callable=AsyncMock,
        return_value=FAKE_SEARCH,
    ), patch("skills.webmcp.fetcher.fetch_page", new_callable=AsyncMock, return_value=FAKE_PAGE):
        result = await agent._execute("search_and_fetch:LLM open source 2026")
    assert result.success is True
    assert result.data["mode"] == "search_and_fetch"
    assert "pages" in result.data


@pytest.mark.asyncio
async def test_execute_deep_mode_unavailable():
    agent = WebMCPAgent()
    result = await agent._execute("deep:https://instagram.com/nasa")
    assert result.success is True
    assert "deep" in result.data["mode"]


@pytest.mark.asyncio
async def test_execute_returns_taskresult_on_error():
    agent = WebMCPAgent()
    with patch(
        "skills.webmcp.search_engine.search_duckduckgo",
        new_callable=AsyncMock,
        side_effect=Exception("network error"),
    ):
        result = await agent._execute("search:qualquer coisa")
    assert result.success is False
    assert "network error" in result.error


@pytest.mark.asyncio
async def test_execution_time_populated():
    agent = WebMCPAgent()
    with patch(
        "skills.webmcp.search_engine.search_duckduckgo",
        new_callable=AsyncMock,
        return_value=FAKE_SEARCH,
    ):
        result = await agent._execute("search:test")
    assert result.execution_time >= 0.0
