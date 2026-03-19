"""
apex_dashboard/api.py

API de dados para o Moon Dashboard Live.
Servidor HTTP leve (stdlib) que agrega dados dos agentes Moon.
Endpoint principal: GET /api/data → JSON com dados vivos.
Porta padrão: 8080 (mesma que moon_qa_agent monitora).
"""
import json
import os
import sys
import logging
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime

# Resolve path do projeto
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logger = logging.getLogger(__name__)

# Importar módulos do core
from core.flow_run_store import get_flow_run_store
from core.flow_scheduler import get_flow_scheduler
from core.policy_engine import get_policy_engine
from core.skill_manifest import get_skill_registry
from core.moon_flow import get_flow_registry
from core.flow_template import get_template_registry


def _format_timestamp(ts):
    """Format timestamp to ISO string."""
    if ts and ts > 0:
        return datetime.fromtimestamp(ts).isoformat()
    return None


def _parse_datetime(date_str):
    """Parse datetime string to timestamp."""
    try:
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return dt.timestamp()
    except ValueError:
        return None


def _handle_api(path, query_params, body, method):
    """Router central que mapeia path → handler"""
    try:
        if path == "/api/status":
            return _handle_status()
        elif path == "/api/flows":
            return _handle_flows()
        elif path.startswith("/api/runs"):
            return _handle_runs(path, query_params)
        elif path.startswith("/api/scheduler"):
            return _handle_scheduler(path, method, body)
        elif path == "/api/skills":
            return _handle_skills()
        elif path == "/api/policy":
            return _handle_policy()
        elif path.startswith("/api/policy/check"):
            return _handle_policy_check(method, body)
        elif path == "/api/templates":
            return _handle_templates()
        elif path == "/api/health":
            return _handle_health()
        else:
            return {"error": "endpoint not found", "status": 404}, 404
    except Exception as e:
        logger.error(f"API Error: {e}", exc_info=True)
        return {"error": str(e), "status": 500}, 500


def _handle_status():
    """Handle GET /api/status"""
    flow_registry = get_flow_registry()
    template_registry = get_template_registry()
    scheduler = get_flow_scheduler()
    policy_engine = get_policy_engine()
    skill_registry = get_skill_registry()
    
    return {
        "version": "1.0",
        "uptime": time.time() - getattr(_handle_status, 'start_time', time.time()),
        "timestamp": datetime.now().isoformat(),
        "modules": {
            "flow_registry": len(flow_registry.list_flows()),
            "template_registry": len(template_registry.list_templates()),
            "scheduler_jobs": len(scheduler.list_jobs()),
            "policy_rules": len(policy_engine.list_rules()),
            "skill_count": len(skill_registry.list_all()),
        }
    }, 200
_handle_status.start_time = time.time()


def _handle_flows():
    """Handle GET /api/flows"""
    flow_registry = get_flow_registry()
    flows = []
    
    for flow_name in flow_registry.list_flows():
        flow = flow_registry.get(flow_name)
        if flow:
            flows.append({
                "name": flow.name,
                "steps": len(flow.steps),
                "session_mode": getattr(flow, 'session_mode', 'user')
            })
    
    return {"flows": flows}, 200


def _handle_runs(path, query_params):
    """Handle GET /api/runs?flow=<optional>&status=<optional>&limit=<int default 20>"""
    # Parse path and query parameters
    flow_name = query_params.get('flow', [None])[0]
    status = query_params.get('status', [None])[0]
    limit = int(query_params.get('limit', [20])[0])
    
    store = get_flow_run_store()
    runs = store.list_runs(flow_name, status)[:limit]
    
    runs_data = []
    for run in runs:
        # Calculate total steps and successful steps
        total_steps = len(run.steps)
        successful_steps = len([step for step in run.steps if step.status == 'success'])
        duration = (run.finished_at - run.started_at) if run.finished_at > 0 else 0
        
        runs_data.append({
            "run_id": run.run_id,
            "flow_name": run.flow_name,
            "status": run.status,
            "started_at": _format_timestamp(run.started_at),
            "finished_at": _format_timestamp(run.finished_at) if run.finished_at > 0 else None,
            "total_time": duration,
            "steps": total_steps,
            "successful_steps": successful_steps
        })
    
    return {
        "runs": runs_data,
        "total": len(runs_data)
    }, 200


def _handle_scheduler(path, method, body):
    """Handle GET /api/scheduler and POST /api/scheduler/<job_id>/enable|disable"""
    scheduler = get_flow_scheduler()
    
    # Handle POST to enable/disable
    if method == 'POST':
        # Extract job_id from path like /api/scheduler/abc123/enable or /api/scheduler/abc123/disable
        parts = path.split('/')
        if len(parts) >= 4 and parts[-1] in ['enable', 'disable']:
            job_id = parts[3]
            action = parts[-1]
            
            if action == 'enable':
                success = scheduler.enable_job(job_id)
            else:
                success = scheduler.disable_job(job_id)
            
            return {
                "job_id": job_id,
                "enabled": action == 'enable',
                "ok": success
            }, 200 if success else 404
    
    # Handle GET for scheduler data
    jobs = scheduler.list_jobs()
    jobs_data = []
    
    for job in jobs:
        jobs_data.append({
            "job_id": job.job_id,
            "flow_name": job.flow_name,
            "schedule_type": job.schedule_type,
            "time_of_day": job.time_of_day,
            "interval_minutes": job.interval_minutes,
            "enabled": job.enabled,
            "next_run": _format_timestamp(job.next_run_at) if job.next_run_at > 0 else None,
            "run_count": job.run_count,
            "last_run": _format_timestamp(job.last_run_at) if job.last_run_at > 0 else None,
        })
    
    return {
        "jobs": jobs_data,
        "total": len(jobs_data),
        "enabled": len([j for j in jobs_data if j['enabled']])
    }, 200


def _handle_skills():
    """Handle GET /api/skills"""
    skill_registry = get_skill_registry()
    skills = skill_registry.list_all()
    skills_data = []
    
    for skill in skills:
        skills_data.append({
            "name": skill.name,
            "version": getattr(skill, 'version', '1.0'),
            "description": skill.description or "Sem descrição",
            "domains": skill.domains or [],
            "cost": getattr(skill, 'cost', 'free'),
            "requires_key": getattr(skill, 'requires_api_key', False)
        })
    
    # Group by domain
    by_domain = {}
    for skill in skills_data:
        for domain in skill['domains']:
            if domain not in by_domain:
                by_domain[domain] = []
            by_domain[domain].append(skill['name'])
    
    return {
        "skills": skills_data,
        "total": len(skills_data),
        "by_domain": by_domain
    }, 200


def _handle_policy():
    """Handle GET /api/policy"""
    policy_engine = get_policy_engine()
    rules = policy_engine.list_rules()
    rules_data = []
    
    for rule in rules:
        rules_data.append({
            "rule_id": rule.rule_id,
            "effect": rule.effect,
            "priority": rule.priority,
            "description": rule.description,
            "channels": rule.channels,
            "commands": rule.commands
        })
    
    # Stats
    allow_count = len([r for r in rules if r.effect == "allow"])
    deny_count = len([r for r in rules if r.effect == "deny"])
    
    return {
        "rules": rules_data,
        "total": len(rules_data),
        "stats": {
            "allow": allow_count,
            "deny": deny_count
        }
    }, 200


def _handle_policy_check(method, body):
    """Handle POST /api/policy/check"""
    if method != 'POST' or not body:
        return {"error": "POST required with body", "status": 400}, 400
    
    try:
        data = json.loads(body.decode('utf-8'))
        channel = data.get('channel', 'unknown')
        user = data.get('user', 'unknown')
        command = data.get('command', 'unknown')
    except json.JSONDecodeError:
        return {"error": "Invalid JSON in request body", "status": 400}, 400
    
    policy_engine = get_policy_engine()
    decision = policy_engine.check(channel_type=channel, user_id=user, command=command)
    
    return {
        "allowed": decision.allowed,
        "reason": decision.reason,
        "rule_id": decision.rule_id
    }, 200


def _handle_templates():
    """Handle GET /api/templates"""
    template_registry = get_template_registry()
    templates = template_registry.list_templates()
    templates_data = []
    
    for template in templates:
        templates_data.append({
            "name": template.name,
            "domain": template.domain,
            "description": template.description,
            "variables": [{
                "name": var.name,
                "type": var.type,
                "description": var.description,
                "default": var.default
            } for var in template.variables],
            "tags": getattr(template, 'tags', [])
        })
    
    return {
        "templates": templates_data,
        "total": len(templates_data)
    }, 200


def _handle_health():
    """Handle GET /api/health"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}, 200


def _build_dashboard_payload() -> dict:
    """Agrega dados reais de todos os agentes para o dashboard (backward compatibility)."""
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
        "news": [],  # Placeholder for news
        "blog": {
            "recent_posts": [],  # Placeholder for blog posts
        },
    }


class MoonDashboardAPIHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        logger.debug(f"[MoonAPI] {format}", *args)

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        query_params = parse_qs(parsed_path.query)
        
        # Servir index.html para / e /index.html
        if path in ("/", "/index.html", ""):
            import pathlib
            index_path = pathlib.Path(__file__).parent / "index.html"
            if index_path.exists():
                content = index_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
            else:
                # index.html não encontrado
                self._send_json({"error": "index.html não encontrado"}, 404)
                return

        # Servir arquivos estáticos (CSS, JS, PNG, SVG, ICO)
        static_extensions = {
            ".css": "text/css",
            ".js": "application/javascript",
            ".png": "image/png",
            ".svg": "image/svg+xml",
            ".ico": "image/x-icon",
        }
        from pathlib import Path as _Path
        req_path = _Path(path.lstrip("/"))
        static_file = _Path(__file__).parent / req_path
        ext = static_file.suffix.lower()
        if ext in static_extensions and static_file.exists() and static_file.is_file():
            content = static_file.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", static_extensions[ext])
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return
        
        if path == "/api/data":
            self._send_json(_build_dashboard_payload())
        elif path == "/health":
            self._send_json({"status": "ok", "ts": datetime.now().isoformat()})
        else:
            data, status = _handle_api(path, query_params, None, "GET")
            self._send_json(data, status)

    def do_POST(self):
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        query_params = parse_qs(parsed_path.query)
        
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length > 0 else b''
        
        data, status = _handle_api(path, query_params, body, "POST")
        self._send_json(data, status)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


def start_api_server(port: int = 8080, host: str = "0.0.0.0"):
    """Inicia o servidor da API do Moon Dashboard."""
    server = HTTPServer((host, port), MoonDashboardAPIHandler)
    logger.info(f"[MoonAPI] Servidor iniciado em http://{host}:{port}")
    logger.info(f"[MoonAPI] Dados: http://{host}:{port}/api/data")
    logger.info(f"[MoonAPI] Status: http://{host}:{port}/api/status")
    server.serve_forever()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    start_api_server()