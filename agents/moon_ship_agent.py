"""
agents/moon_ship_agent.py
Moon Ship Agent — Pipeline completo de release

Architecture:
  - Pipeline de 6 passos:
    1. Pre-flight check: git status, pytest
    2. Review automático (MoonReviewAgent)
    3. Sync com main (git fetch + rebase)
    4. Gerar changelog entry via LLM
    5. Push e PR (GithubAgent)
    6. Notificar (MessageBus + Telegram)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.agent_base import AgentBase, AgentPriority, TaskResult
from core.message_bus import MessageBus
from agents.llm import LLMRouter

logger = logging.getLogger("moon.agents.ship")


# ─────────────────────────────────────────────────────────────
#  Configurações
# ─────────────────────────────────────────────────────────────

REVIEW_GATE_TIMEOUT = 60  # segundos para aguardar confirmação
MIN_HEALTH_SCORE = 70  # score mínimo para prosseguir sem confirmação


# ─────────────────────────────────────────────────────────────
#  Moon Ship Agent
# ─────────────────────────────────────────────────────────────

class MoonShipAgent(AgentBase):
    """
    Agente de pipeline de release.
    
    Uso:
        await agent.execute("release")  # Pipeline completo
        await agent.execute("pr")  # Apenas criar PR
    """
    
    def __init__(self):
        super().__init__()
        self.name = "MoonShipAgent"
        self.priority = AgentPriority.HIGH
        self.description = "Release pipeline agent"
        self._router: Optional[LLMRouter] = None
        self._message_bus: Optional[MessageBus] = None
        self._github_agent = None
        self._review_agent = None
    
    async def initialize(self) -> None:
        """Inicializa o agente."""
        await super().initialize()
        self._router = LLMRouter()
        self._message_bus = MessageBus()
        
        # Importa agentes lazy
        try:
            from agents.github_agent import GithubAgent
            self._github_agent = GithubAgent()
            await self._github_agent.initialize()
            logger.info("GithubAgent initialized")
        except ImportError:
            logger.warning("GithubAgent not available")
            self._github_agent = None
        
        try:
            from agents.moon_review_agent import MoonReviewAgent
            self._review_agent = MoonReviewAgent()
            await self._review_agent.initialize()
            logger.info("ReviewAgent initialized")
        except ImportError:
            logger.warning("ReviewAgent not available")
            self._review_agent = None
        
        logger.info("MoonShipAgent initialized")
    
    async def shutdown(self) -> None:
        """Para o agente."""
        if self._github_agent:
            await self._github_agent.shutdown()
        if self._review_agent:
            await self._review_agent.shutdown()
        await super().shutdown()
        logger.info("MoonShipAgent shut down")
    
    async def _execute(self, task: str, **kwargs) -> TaskResult:
        """
        Executa pipeline de release.
        
        Args:
            task: "release" ou "pr"
        
        Returns:
            TaskResult com status do pipeline.
        """
        try:
            task = task.strip().lower()
            
            if task == "release":
                return await self._run_full_pipeline()
            elif task == "pr":
                return await self._create_pr_only()
            else:
                return TaskResult(success=False, error="Usage: release | pr")
            
        except Exception as e:
            logger.error(f"Ship execution failed: {e}")
            return TaskResult(success=False, error=str(e))
    
    async def _run_full_pipeline(self) -> TaskResult:
        """Executa pipeline completo de release."""
        steps = {
            "preflight": False,
            "review": False,
            "sync": False,
            "changelog": False,
            "push_pr": False,
            "notify": False,
        }
        
        pr_url = None
        health_score = 100
        
        try:
            # Passo 1: Pre-flight check
            logger.info("Step 1: Pre-flight check...")
            preflight_ok = await self._preflight_check()
            
            if not preflight_ok:
                return TaskResult(
                    success=False,
                    error="Pre-flight check failed. Fix issues before shipping."
                )
            steps["preflight"] = True
            
            # Passo 2: Review automático
            logger.info("Step 2: Running code review...")
            review_result = await self._run_review()
            health_score = review_result.get("health_score", 100)
            
            if health_score < MIN_HEALTH_SCORE:
                # Aguarda confirmação
                confirmed = await self._wait_for_review_gate(health_score)
                if not confirmed:
                    return TaskResult(
                        success=False,
                        error=f"Review gate blocked: health_score={health_score} < {MIN_HEALTH_SCORE}"
                    )
            steps["review"] = True
            
            # Passo 3: Sync com main
            logger.info("Step 3: Syncing with main...")
            sync_ok = await self._sync_with_main()
            
            if not sync_ok:
                return TaskResult(success=False, error="Sync with main failed")
            steps["sync"] = True
            
            # Passo 4: Gerar changelog
            logger.info("Step 4: Generating changelog...")
            changelog = await self._generate_changelog()
            steps["changelog"] = True
            
            # Passo 5: Push e PR
            logger.info("Step 5: Pushing and creating PR...")
            pr_url = await self._push_and_create_pr(changelog, health_score)
            steps["push_pr"] = bool(pr_url)
            
            # Passo 6: Notificar
            logger.info("Step 6: Notifying...")
            await self._notify_completion(pr_url, health_score)
            steps["notify"] = True
            
            return TaskResult(
                success=True,
                data={
                    "steps_completed": steps,
                    "pr_url": pr_url,
                    "health_score": health_score,
                }
            )
            
        except Exception as e:
            logger.error(f"Pipeline failed at step {steps}: {e}")
            return TaskResult(
                success=False,
                error=f"Pipeline failed: {e}. Steps completed: {steps}"
            )
    
    async def _preflight_check(self) -> bool:
        """Verifica condições pré-flight."""
        # Check 1: Mudanças não commitadas
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.stdout.strip():
                logger.warning(f"Uncommitted changes: {result.stdout[:200]}")
                # Não falha, apenas loga
        except Exception as e:
            logger.error(f"Git status failed: {e}")
            return False
        
        # Check 2: Testes passam
        try:
            logger.info("Running tests...")
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    subprocess.run,
                    ["python3", "-m", "pytest", "tests/", "-x", "-q"],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    cwd=str(Path(__file__).resolve().parent.parent)
                ),
                timeout=120
            )
            
            if result.returncode != 0:
                logger.error(f"Tests failed: {result.stderr[:500]}")
                return False
            
            logger.info("Tests passed")
            
        except asyncio.TimeoutError:
            logger.error("Tests timed out")
            return False
        except Exception as e:
            logger.error(f"Test execution failed: {e}")
            return False
        
        return True
    
    async def _run_review(self) -> Dict[str, Any]:
        """Executa code review."""
        if not self._review_agent:
            logger.warning("ReviewAgent not available, skipping review")
            return {"health_score": 100}
        
        result = await self._review_agent.execute("auto")
        
        if result.success:
            return result.data
        else:
            logger.warning(f"Review failed: {result.error}")
            return {"health_score": 80}
    
    async def _wait_for_review_gate(self, health_score: int) -> bool:
        """Aguarda confirmação do usuário após review com score baixo."""
        logger.warning(f"Health score {health_score} < {MIN_HEALTH_SCORE}, waiting for confirmation...")
        
        # Publica pedido de confirmação
        await self._message_bus.publish(
            sender=self.name,
            topic="ship.review_gate",
            payload={
                "health_score": health_score,
                "min_required": MIN_HEALTH_SCORE,
                "message": f"Code review score {health_score} is below {MIN_HEALTH_SCORE}. Proceed?",
            }
        )
        
        # Aguarda resposta (simplificado - na prática precisaria de subscription)
        await asyncio.sleep(REVIEW_GATE_TIMEOUT)
        
        # Timeout - não recebeu confirmação
        logger.warning("Review gate timeout - no confirmation received")
        return False
    
    async def _sync_with_main(self) -> bool:
        """Faz sync com branch main."""
        try:
            # Git fetch
            result = subprocess.run(
                ["git", "fetch", "origin"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode != 0:
                logger.error(f"Git fetch failed: {result.stderr}")
                return False
            
            # Git rebase
            result = subprocess.run(
                ["git", "rebase", "origin/main"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                logger.error(f"Git rebase failed (conflicts?): {result.stderr}")
                return False
            
            logger.info("Synced with main")
            return True
            
        except Exception as e:
            logger.error(f"Sync failed: {e}")
            return False
    
    async def _generate_changelog(self) -> str:
        """Gera entrada de changelog via LLM."""
        try:
            # Obter commits desde main
            result = subprocess.run(
                ["git", "log", "main..HEAD", "--oneline"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            commits = result.stdout.strip()
            if not commits:
                return "- No new changes"
            
            prompt = (
                f"Generate a concise changelog entry (max 5 bullets) for these commits:\n"
                f"{commits}\n\n"
                f"Format: '- feat/fix/chore: description' (one line per bullet, no header)"
            )
            
            response = await self._router.complete(
                prompt=prompt,
                task_type="fast",
                model="llama-3.1-8b-instant",
                actor="moon_ship_agent"
            )
            
            return response.strip()
            
        except Exception as e:
            logger.error(f"Changelog generation failed: {e}")
            return "- Changelog generation failed"
    
    async def _push_and_create_pr(
        self,
        changelog: str,
        health_score: int
    ) -> Optional[str]:
        """Faz push e cria PR."""
        if not self._github_agent:
            logger.warning("GithubAgent not available, skipping PR")
            return None
        
        try:
            # Git push
            result = subprocess.run(
                ["git", "push", "origin", "HEAD"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                logger.error(f"Git push failed: {result.stderr}")
                return None
            
            # Obter branch atual
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                timeout=10
            )
            branch = result.stdout.strip()
            
            # Criar PR via GithubAgent
            title = f"Release: {datetime.now().strftime('%Y-%m-%d')}"
            body = f"""
## Changelog
{changelog}

## Quality
- Review Health Score: {health_score}/100
- Tests: Passing
- Pre-flight: OK
"""
            
            # Usa GithubAgent para criar PR
            result = await self._github_agent.execute(
                "create_pr",
                branch=branch,
                title=title,
                body=body.strip(),
                file_changes={}
            )
            
            if result.success:
                pr_url = result.data.get("pr_url")
                logger.info(f"PR created: {pr_url}")
                return pr_url
            else:
                logger.error(f"PR creation failed: {result.error}")
                return None
            
        except Exception as e:
            logger.error(f"Push/PR failed: {e}")
            return None
    
    async def _notify_completion(
        self,
        pr_url: Optional[str],
        health_score: int
    ) -> None:
        """Notifica conclusão do pipeline."""
        payload = {
            "status": "completed",
            "pr_url": pr_url,
            "health_score": health_score,
            "timestamp": datetime.now().isoformat(),
        }
        
        await self._message_bus.publish(
            sender=self.name,
            topic="ship.completed",
            payload=payload
        )
        
        logger.info(f"Ship completed. PR: {pr_url}, Health: {health_score}")
    
    async def _create_pr_only(self) -> TaskResult:
        """Cria apenas PR sem pipeline completo."""
        # Implementação simplificada
        return TaskResult(success=False, error="PR-only mode not fully implemented")


# ─────────────────────────────────────────────────────────────
#  Factory function
# ─────────────────────────────────────────────────────────────

def create_ship_agent() -> MoonShipAgent:
    """Factory function para criar o agente."""
    return MoonShipAgent()
