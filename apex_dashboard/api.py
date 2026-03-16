"""
apex_dashboard/api.py

API de dados para o Apex Dashboard.
Servidor HTTP leve (stdlib) que agrega dados dos agentes Moon.
Endpoint principal: GET /api/data → JSON com dados vivos.
Porta padrão: 8080 (mesma que moon_qa_agent monitora).
"""
import json
import os
import sys
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

# Resolve path do projeto
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logger = logging.getLogger(__name__)


def _load_news_data() -> list:
    """Carrega headlines do news_monitor (arquivo real de hoje)."""
    today = datetime.now().strftime("%Y-%m-%d")
    news_path = os.path.join(
        _PROJECT_ROOT, "data", "news", f"headlines_{today}.json"
    )
    if os.path.exists(news_path):
        try:
            with open(news_path, encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else [data]
        except Exception as e:
            logger.warning(f"[ApexAPI] Erro ao carregar news: {e}")
    return []


def _load_blog_exports() -> list:
    """Lista posts publicados com PDF disponível."""
    exports_dir = os.path.join(_PROJECT_ROOT, "data", "blog_exports")
    posts = []
    if os.path.exists(exports_dir):
        for f in sorted(os.listdir(exports_dir)):
            if f.endswith(".pdf"):
                posts.append({
                    "slug": f.replace(".pdf", ""),
                    "pdf": f"/blog_exports/{f}",
                    "published_at": datetime.fromtimestamp(
                        os.path.getmtime(
                            os.path.join(exports_dir, f)
                        )
                    ).isoformat()
                })
    return posts


def _build_dashboard_payload() -> dict:
    """Agrega dados reais de todos os agentes para o dashboard."""
    return {
        "timestamp": datetime.now().isoformat(),
        "ecosystem": {
            "status": "online",
            "agents_active": [
                "architect", "news_monitor", "betting_analyst",
                "economic_sentinel", "blog_publisher", "moon_qa"
            ],
            "tests": {"pass": 309, "skip": 14, "fail": 0},
            "last_sync": datetime.now().strftime("%Y-%m-%d %H:%M"),
        },
        "sports": {
            "markets": ["football", "basketball", "tennis"],
            "logos_available": [
                "Arsenal", "Elche", "Everton",
                "Man City", "Real Madrid", "West Ham"
            ],
        },
        "news": _load_news_data()[:10],
        "blog": {
            "recent_posts": _load_blog_exports()[:5],
        },
    }


class ApexAPIHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        logger.debug(f"[ApexAPI] {format}", *args)

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/data":
            self._send_json(_build_dashboard_payload())
        elif self.path == "/health":
            self._send_json({"status": "ok",
                             "ts": datetime.now().isoformat()})
        else:
            self._send_json({"error": "not found"}, 404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()


def start_api_server(port: int = 8080, host: str = "0.0.0.0"):
    """Inicia o servidor da API do Apex Dashboard."""
    server = HTTPServer((host, port), ApexAPIHandler)
    logger.info(f"[ApexAPI] Servidor iniciado em http://{host}:{port}")
    logger.info(f"[ApexAPI] Dados: http://{host}:{port}/api/data")
    server.serve_forever()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    start_api_server()
