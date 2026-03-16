"""tests/test_apex_dashboard_api.py — Testes da API do Apex Dashboard"""

import pytest
import json
from unittest.mock import patch
from datetime import datetime


class TestApexDashboardAPI:

    def test_build_payload_estrutura_correta(self):
        """Payload tem estrutura esperada."""
        from apex_dashboard.api import _build_dashboard_payload
        payload = _build_dashboard_payload()
        assert "timestamp" in payload
        assert "ecosystem" in payload
        assert "sports" in payload
        assert "news" in payload
        assert "blog" in payload

    def test_build_payload_ecosystem_status(self):
        """Ecosystem status é online."""
        from apex_dashboard.api import _build_dashboard_payload
        payload = _build_dashboard_payload()
        assert payload["ecosystem"]["status"] == "online"
        assert isinstance(payload["ecosystem"]["agents_active"], list)
        assert len(payload["ecosystem"]["agents_active"]) > 0

    def test_build_payload_sports_markets(self):
        """Sports markets contém futebol, basquete, tênis."""
        from apex_dashboard.api import _build_dashboard_payload
        payload = _build_dashboard_payload()
        assert "football" in payload["sports"]["markets"]
        assert "basketball" in payload["sports"]["markets"]
        assert "tennis" in payload["sports"]["markets"]

    def test_load_news_retorna_lista(self):
        """_load_news_data retorna lista."""
        from apex_dashboard.api import _load_news_data
        news = _load_news_data()
        assert isinstance(news, list)

    def test_load_news_sem_arquivo_retorna_lista_vazia(self):
        """Sem arquivo de news, retorna lista vazia."""
        from apex_dashboard.api import _load_news_data
        with patch("os.path.exists", return_value=False):
            news = _load_news_data()
            assert news == []

    def test_load_blog_exports_retorna_lista(self):
        """_load_blog_exports retorna lista de posts."""
        from apex_dashboard.api import _load_blog_exports
        posts = _load_blog_exports()
        assert isinstance(posts, list)
        for post in posts:
            assert "slug" in post
            assert "pdf" in post

    def test_payload_timestamp_valido(self):
        """Timestamp é ISO datetime válido."""
        from apex_dashboard.api import _build_dashboard_payload
        payload = _build_dashboard_payload()
        # Deve ser parseable como ISO datetime
        dt = datetime.fromisoformat(payload["timestamp"])
        assert dt.year == 2026

    def test_handler_importavel(self):
        """ApexAPIHandler e start_api_server são importáveis."""
        from apex_dashboard.api import ApexAPIHandler, start_api_server
        assert callable(start_api_server)

    def test_payload_tests_contagem(self):
        """Payload contém contagem de testes."""
        from apex_dashboard.api import _build_dashboard_payload
        payload = _build_dashboard_payload()
        tests = payload["ecosystem"]["tests"]
        assert "pass" in tests
        assert "skip" in tests
        assert "fail" in tests
        assert tests["fail"] == 0
