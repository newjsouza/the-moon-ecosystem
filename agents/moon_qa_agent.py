"""
agents/moon_qa_agent.py
Moon QA Agent — QA visual autônomo via browser headless

Architecture:
  - Pipeline diff-aware:
    1. git diff --name-only → identifica rotas afetadas
    2. Verifica apps rodando (portas 3000, 8080, etc.)
    3. Para cada app online:
       - goto(url)
       - screenshot()
       - console()
       - snapshot()
       - Navega por links internos
    4. Gera JSON em data/qa_reports/{timestamp}_qa_report.json
    5. Publica em "qa.report_generated" e "nexus.event"
  - Modo schedule: QA automático a cada 6 horas
"""
from __future__ import annotations

import asyncio
import httpx
import json
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.agent_base import AgentBase, AgentPriority, TaskResult
from core.message_bus import MessageBus

logger = logging.getLogger("moon.agents.qa")


# ─────────────────────────────────────────────────────────────
#  Configurações
# ─────────────────────────────────────────────────────────────

# Mapeamento de arquivos → portas/URLs
APP_ROUTES = {
    "workspace_monitor": {"port": 3000, "path": "/"},
    "apex_dashboard": {"port": 8080, "path": "/"},
    "meu_blog": {"port": 8000, "path": "/"},
    "dashboard": {"port": 3000, "path": "/"},
}

DEFAULT_APPS = [
    {"name": "workspace_monitor", "url": "http://localhost:3000"},
    {"name": "apex_dashboard", "url": "http://localhost:8080"},
]


# ─────────────────────────────────────────────────────────────
#  Moon QA Agent
# ─────────────────────────────────────────────────────────────

class MoonQAAgent(AgentBase):
    """
    Agente de QA visual autônomo.
    
    Uso:
        await agent.execute("diff-aware")  # QA baseado no diff
        await agent.execute("manual")  # QA manual em apps configurados
        await agent.execute("url http://localhost:3000")  # QA de URL específica
    """
    
    def __init__(self):
        super().__init__()
        self.name = "MoonQAAgent"
        self.priority = AgentPriority.MEDIUM
        self.description = "Autonomous visual QA agent via browser"
        self._message_bus: Optional[MessageBus] = None
        self._reports_dir: Path = Path(__file__).resolve().parent.parent / "data" / "qa_reports"
        self._browser_agent = None
        self._schedule_task: Optional[asyncio.Task] = None
    
    async def initialize(self) -> None:
        """Inicializa o agente."""
        await super().initialize()
        self._message_bus = MessageBus()
        self._reports_dir.mkdir(parents=True, exist_ok=True)
        
        # Importa MoonBrowserAgent lazy para evitar circular import
        try:
            from agents.moon_browser_agent import MoonBrowserAgent
            self._browser_agent = MoonBrowserAgent()
            await self._browser_agent.initialize()
            logger.info("MoonQAAgent initialized with browser")
        except ImportError:
            logger.warning("MoonBrowserAgent not available - QA limited")
            self._browser_agent = None
        
        logger.info("MoonQAAgent initialized")
    
    async def shutdown(self) -> None:
        """Para o agente."""
        if self._schedule_task:
            self._schedule_task.cancel()
        
        if self._browser_agent:
            await self._browser_agent.shutdown()
        
        await super().shutdown()
        logger.info("MoonQAAgent shut down")
    
    async def _execute(self, task: str, **kwargs) -> TaskResult:
        """
        Executa QA.
        
        Args:
            task: "diff-aware", "manual", ou "url <url>"
        
        Returns:
            TaskResult com relatório de QA.
        """
        try:
            task = task.strip().lower()
            
            if task == "diff-aware":
                report = await self._run_diff_aware_qa()
            elif task == "manual":
                report = await self._run_manual_qa()
            elif task.startswith("url "):
                url = task[4:].strip()
                report = await self._run_url_qa(url)
            else:
                return TaskResult(success=False, error="Usage: diff-aware | manual | url <url>")
            
            # Salvar relatório
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_file = self._reports_dir / f"{timestamp}_qa_report.json"
            report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
            logger.info(f"QA report saved to {report_file}")
            
            # Publicar na MessageBus
            await self._message_bus.publish(
                sender=self.name,
                topic="qa.report_generated",
                payload=report
            )
            
            # Publicar no Nexus para indexação
            await self._message_bus.publish(
                sender=self.name,
                topic="nexus.event",
                payload={
                    "type": "qa_report",
                    "timestamp": report["timestamp"],
                    "overall_health": report["overall_health"],
                    "apps_tested": report["apps_tested"],
                }
            )
            
            return TaskResult(
                success=True,
                data=report
            )
            
        except Exception as e:
            logger.error(f"QA execution failed: {e}")
            return TaskResult(success=False, error=str(e))
    
    async def _run_diff_aware_qa(self) -> Dict[str, Any]:
        """Executa QA baseado no diff do git."""
        # Passo 1: Identificar rotas afetadas
        affected_files = self._get_affected_files()
        apps_to_test = self._identify_affected_apps(affected_files)
        
        if not apps_to_test:
            # Nenhum app afetado, testa todos por padrão
            apps_to_test = DEFAULT_APPS
        
        # Passo 2: Verificar quais apps estão online
        online_apps = await self._check_apps_online(apps_to_test)
        
        # Passo 3: QA Pass para cada app online
        return await self._run_qa_pass(online_apps, trigger="diff-aware")
    
    async def _run_manual_qa(self) -> Dict[str, Any]:
        """Executa QA manual em apps configurados."""
        return await self._run_qa_pass(DEFAULT_APPS, trigger="manual")
    
    async def _run_url_qa(self, url: str) -> Dict[str, Any]:
        """Executa QA em URL específica."""
        app_name = url.split("//")[-1].split(":")[0]
        apps = [{"name": app_name, "url": url}]
        
        online = await self._check_apps_online(apps)
        return await self._run_qa_pass(online, trigger="manual")
    
    def _get_affected_files(self) -> List[str]:
        """Obtém arquivos afetados do git diff."""
        try:
            result = subprocess.run(
                ["git", "diff", "main", "--name-only"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(Path(__file__).resolve().parent.parent)
            )
            return result.stdout.strip().split('\n') if result.stdout else []
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []
    
    def _identify_affected_apps(self, files: List[str]) -> List[Dict[str, str]]:
        """Identifica quais apps testar baseado nos arquivos."""
        apps = []
        seen = set()
        
        for f in files:
            f_lower = f.lower()
            
            for keyword, app_config in APP_ROUTES.items():
                if keyword in f_lower and app_config["port"] not in seen:
                    apps.append({
                        "name": keyword,
                        "url": f"http://localhost:{app_config['port']}{app_config['path']}",
                    })
                    seen.add(app_config["port"])
        
        return apps
    
    async def _check_apps_online(self, apps: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Verifica quais apps estão respondendo."""
        online = []
        
        async with httpx.AsyncClient(timeout=3.0) as client:
            for app in apps:
                try:
                    response = await client.get(app["url"])
                    if response.status_code < 500:
                        online.append(app)
                        logger.info(f"App {app['name']} is online ({response.status_code})")
                    else:
                        logger.warning(f"App {app['name']} returned {response.status_code}")
                except (httpx.ConnectError, httpx.TimeoutException) as e:
                    logger.warning(f"App {app['name']} is offline: {e}")
        
        return online
    
    async def _run_qa_pass(
        self,
        apps: List[Dict[str, str]],
        trigger: str = "manual"
    ) -> Dict[str, Any]:
        """Executa QA pass em lista de apps."""
        timestamp = datetime.now().isoformat()
        
        report = {
            "timestamp": timestamp,
            "trigger": trigger,
            "apps_tested": [],
            "apps_offline": [],
            "screenshots": [],
            "console_errors": {},
            "visual_issues": [],
            "health_scores": {},
            "overall_health": 100,
        }
        
        if not self._browser_agent:
            report["error"] = "Browser agent not available"
            report["overall_health"] = 0
            return report
        
        total_health = 0
        
        for app in apps:
            app_name = app["name"]
            app_url = app["url"]
            
            logger.info(f"Running QA for {app_name} at {app_url}")
            
            try:
                # Navegar para URL
                goto_result = await self._browser_agent.execute(f"goto {app_url}")
                
                if "BROWSER_ERROR" in goto_result.data.get("output", ""):
                    report["apps_offline"].append(app_name)
                    continue
                
                report["apps_tested"].append(app_name)
                
                # Aguardar carregamento
                await asyncio.sleep(2)
                
                # Screenshot
                screenshot_path = f"/tmp/moon_qa_{app_name}_{int(datetime.now().timestamp())}.png"
                screenshot_result = await self._browser_agent.execute(f"screenshot {screenshot_path}")
                
                report["screenshots"].append({
                    "app": app_name,
                    "url": app_url,
                    "path": screenshot_path,
                })
                
                # Console errors
                console_result = await self._browser_agent.execute("console")
                console_output = console_result.data.get("output", "")
                
                error_count = console_output.lower().count("error") + console_output.lower().count("exception")
                report["console_errors"][app_name] = {
                    "count": error_count,
                    "output": console_output[:500] if console_output else "",
                }
                
                # Snapshot
                snapshot_result = await self._browser_agent.execute("snapshot interactive")
                
                # Calcular health score do app
                app_health = 100
                if error_count > 0:
                    app_health -= error_count * 10
                if "BROWSER_ERROR" in goto_result.data.get("output", ""):
                    app_health -= 50
                
                app_health = max(0, app_health)
                report["health_scores"][app_name] = app_health
                total_health += app_health
                
            except Exception as e:
                logger.error(f"QA failed for {app_name}: {e}")
                report["apps_offline"].append(app_name)
        
        # Calcular overall health
        if report["apps_tested"]:
            report["overall_health"] = total_health // len(report["apps_tested"])
        else:
            report["overall_health"] = 0
        
        return report
    
    async def start_scheduled_qa(self, interval_hours: int = 6) -> None:
        """Inicia QA agendado em background."""
        async def scheduled_loop():
            while True:
                await asyncio.sleep(interval_hours * 3600)
                logger.info("Running scheduled QA...")
                await self._execute("diff-aware")
        
        self._schedule_task = asyncio.create_task(
            scheduled_loop(),
            name="moon.qa.scheduled"
        )
        logger.info(f"Scheduled QA started (every {interval_hours}h)")


# ─────────────────────────────────────────────────────────────
#  Factory function
# ─────────────────────────────────────────────────────────────

def create_qa_agent() -> MoonQAAgent:
    """Factory function para criar o agente."""
    return MoonQAAgent()
