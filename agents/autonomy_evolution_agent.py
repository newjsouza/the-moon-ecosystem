"""
agents/autonomy_evolution_agent.py
AutonomyEvolutionAgent — planejamento de auto-crescimento orientado por evidências.

Objetivo:
  - Medir maturidade de autonomia do ecossistema com dados locais reais.
  - Gerar priorização prática (não genérica) para próximos passos.
  - Executar automaticamente as ações seguras e de alto impacto.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from core.agent_base import AgentBase, AgentPriority, TaskResult
from core.message_bus import MessageBus

logger = logging.getLogger("moon.agents.autonomy_evolution")


class AutonomyEvolutionAgent(AgentBase):
    """Agente de evolução contínua do sistema."""

    REQUIRED_KEYS = (
        "GROQ_API_KEY",
        "GITHUB_TOKEN",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
    )
    OPTIONAL_KEYS = (
        "SUPABASE_URL",
        "SUPABASE_KEY",
        "YOUTUBE_API_KEY",
        "HUGGINGFACE_TOKEN",
        "OPENROUTER_API_KEY",
        "GEMINI_API_KEY",
    )

    def __init__(self, orchestrator=None):
        super().__init__()
        self.name = "AutonomyEvolutionAgent"
        self.priority = AgentPriority.HIGH
        self.description = "Avalia evidências operacionais e dirige auto-crescimento."
        self.orchestrator = orchestrator
        self.message_bus = MessageBus()

        self.jobs_file = Path("config/scheduled_jobs.json")
        self.flows_dir = Path("flows")
        self.templates_dir = Path("flow_templates")
        self.metrics_sessions_dir = Path("data/metrics/sessions")
        self.devops_reports_dir = Path("data/devops_reports")
        self.sentinel_initiatives_file = Path("data/sentinel_initiatives.json")
        self.output_dir = Path("data/autonomy")

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        action = (task or "assess").strip().lower()

        if action in {"assess", "plan", "status"}:
            return await self._assess()
        if action in {"apply", "apply_next_steps", "apply-growth"}:
            top_n = int(kwargs.get("top_n", 3))
            return await self._apply_next_steps(top_n=top_n)
        if action in {"cycle", "assess_and_apply"}:
            top_n = int(kwargs.get("top_n", 3))
            assess_result = await self._assess()
            apply_result = await self._apply_next_steps(top_n=top_n)
            return TaskResult(
                success=assess_result.success and apply_result.success,
                data={
                    "assessment": assess_result.data,
                    "apply": apply_result.data,
                },
            )

        return TaskResult(success=False, error=f"Unknown task: {task}")

    async def _assess(self) -> TaskResult:
        started = time.time()
        assessment = self._generate_assessment()
        report_path = self._persist_report("assessments", "autonomy_assessment", assessment)
        assessment["report_path"] = str(report_path)

        await self.message_bus.publish(
            sender=self.name,
            topic="autonomy.assessment_ready",
            payload={
                "autonomy_score": assessment["autonomy_score"],
                "top_actions": assessment["recommended_actions"][:3],
                "report_path": str(report_path),
            },
        )

        return TaskResult(
            success=True,
            data={
                "autonomy_score": assessment["autonomy_score"],
                "limitations": assessment["limitations"],
                "growth_potential": assessment["growth_potential"],
                "recommended_actions": assessment["recommended_actions"][:5],
                "report_path": str(report_path),
                "assessment": assessment,
            },
            execution_time=time.time() - started,
        )

    async def _apply_next_steps(self, top_n: int = 3) -> TaskResult:
        started = time.time()
        assessment = self._generate_assessment()
        automatable = [a for a in assessment["recommended_actions"] if a.get("automated")]
        selected = automatable[: max(0, top_n)]

        execution_results: List[Dict[str, Any]] = []
        for action in selected:
            run_result = await self._run_automation_action(action["id"])
            execution_results.append(
                {
                    "action_id": action["id"],
                    "title": action["title"],
                    "success": run_result.success,
                    "error": run_result.error,
                    "data": run_result.data,
                }
            )

        success = all(item["success"] for item in execution_results) if execution_results else True
        payload = {
            "autonomy_score": assessment["autonomy_score"],
            "selected_actions": selected,
            "execution_results": execution_results,
            "timestamp": datetime.now().isoformat(),
        }
        report_path = self._persist_report("executions", "autonomy_apply", payload)

        await self.message_bus.publish(
            sender=self.name,
            topic="autonomy.apply_complete",
            payload={
                "success": success,
                "executed": len(execution_results),
                "report_path": str(report_path),
            },
        )

        return TaskResult(
            success=success,
            data={
                "executed_actions": len(execution_results),
                "report_path": str(report_path),
                "execution_results": execution_results,
            },
            execution_time=time.time() - started,
        )

    async def _run_automation_action(self, action_id: str) -> TaskResult:
        if not self.orchestrator:
            return TaskResult(success=False, error="Orchestrator not available")

        action_map = {
            "run_devops_scan": ("AutonomousDevOpsRefactor", "run_scan"),
            "trigger_health_audit": ("MoonSentinelAgent", "health"),
            "trigger_skill_discovery": ("SkillAlchemist", "discover"),
        }
        target = action_map.get(action_id)
        if not target:
            return TaskResult(success=False, error=f"Action '{action_id}' is not automatable")

        agent_name, task = target
        try:
            return await self.orchestrator._call_agent(agent_name, task)
        except Exception as exc:
            return TaskResult(success=False, error=str(exc))

    def _generate_assessment(self) -> Dict[str, Any]:
        jobs = self._collect_jobs_snapshot()
        metrics = self._collect_metrics_snapshot()
        devops = self._collect_devops_snapshot()
        credentials = self._collect_credentials_snapshot()
        initiatives = self._collect_initiatives_snapshot()

        score_components = self._compute_score_components(
            jobs=jobs,
            metrics=metrics,
            devops=devops,
            credentials=credentials,
            initiatives=initiatives,
        )
        autonomy_score = round(
            sum(score_components.values()) * 100.0,
            1,
        )

        limitations = self._collect_limitations(jobs, metrics, devops, credentials)
        growth_potential = self._collect_growth_potential(jobs, metrics, credentials, initiatives)
        actions = self._build_recommended_actions(
            jobs=jobs,
            metrics=metrics,
            devops=devops,
            credentials=credentials,
            initiatives=initiatives,
        )

        return {
            "generated_at": datetime.now().isoformat(),
            "autonomy_score": autonomy_score,
            "score_components": score_components,
            "limitations": limitations,
            "growth_potential": growth_potential,
            "recommended_actions": actions,
            "evidence": {
                "jobs": jobs,
                "metrics": metrics,
                "devops": devops,
                "credentials": credentials,
                "initiatives": initiatives,
            },
        }

    def _collect_jobs_snapshot(self) -> Dict[str, Any]:
        raw = self._load_json(self.jobs_file, default={"jobs": []})
        jobs = raw.get("jobs", []) if isinstance(raw, dict) else []
        enabled_jobs = [j for j in jobs if isinstance(j, dict) and j.get("enabled", False)]
        unresolved_enabled = []
        never_ran = []

        for job in enabled_jobs:
            flow_name = str(job.get("flow_name", "")).strip()
            if not flow_name:
                unresolved_enabled.append(
                    {
                        "job_id": job.get("job_id", "unknown"),
                        "flow_name": flow_name,
                        "reason": "empty flow_name",
                    }
                )
                continue

            job_type = str(job.get("job_type", "flow")).strip().lower()
            if job_type == "template":
                expected_path = self.templates_dir / f"{flow_name}.json"
            else:
                expected_path = self.flows_dir / f"{flow_name}.json"

            if not expected_path.exists():
                unresolved_enabled.append(
                    {
                        "job_id": job.get("job_id", "unknown"),
                        "flow_name": flow_name,
                        "job_type": job_type,
                        "expected_path": str(expected_path),
                    }
                )

            if int(job.get("run_count", 0)) == 0:
                never_ran.append(job.get("job_id", "unknown"))

        enabled_count = len(enabled_jobs)
        resolved_count = max(0, enabled_count - len(unresolved_enabled))
        coverage_ratio = resolved_count / max(1, enabled_count)
        has_autonomy_cycle = any(
            j.get("flow_name") == "autonomy_growth_cycle" and j.get("enabled", False)
            for j in enabled_jobs
            if isinstance(j, dict)
        )

        return {
            "total_jobs": len(jobs),
            "enabled_jobs": enabled_count,
            "resolved_enabled_jobs": resolved_count,
            "coverage_ratio": round(coverage_ratio, 3),
            "unresolved_enabled_jobs": unresolved_enabled,
            "never_ran_job_ids": never_ran,
            "has_autonomy_growth_schedule": has_autonomy_cycle,
        }

    def _collect_metrics_snapshot(self) -> Dict[str, Any]:
        session_files = sorted(
            self.metrics_sessions_dir.glob("session_*.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        chosen: Dict[str, Any] = {}
        chosen_path = ""
        for path in session_files:
            data = self._load_json(path, default={})
            if int(data.get("total_calls", 0)) > 0:
                chosen = data
                chosen_path = str(path)
                break
        if not chosen and session_files:
            chosen_path = str(session_files[0])
            chosen = self._load_json(session_files[0], default={})

        agents = chosen.get("agents", {}) if isinstance(chosen, dict) else {}
        hotspots = []
        if isinstance(agents, dict):
            for name, item in agents.items():
                if not isinstance(item, dict):
                    continue
                calls = int(item.get("calls", 0))
                rate = float(item.get("success_rate", 1.0))
                if calls >= 3 and rate < 0.8:
                    hotspots.append(
                        {
                            "agent": name,
                            "calls": calls,
                            "success_rate": rate,
                            "status": item.get("status", "unknown"),
                            "last_error": item.get("last_error", ""),
                        }
                    )
        hotspots.sort(key=lambda x: x["success_rate"])

        timestamp = chosen.get("timestamp", 0.0) if isinstance(chosen, dict) else 0.0
        return {
            "has_signal": int(chosen.get("total_calls", 0)) > 0 if isinstance(chosen, dict) else False,
            "session_file": chosen_path,
            "session_age_hours": round(self._hours_since(timestamp), 2),
            "overall_success_rate": float(chosen.get("overall_success_rate", 1.0))
            if isinstance(chosen, dict)
            else 1.0,
            "total_calls": int(chosen.get("total_calls", 0)) if isinstance(chosen, dict) else 0,
            "total_errors": int(chosen.get("total_errors", 0)) if isinstance(chosen, dict) else 0,
            "degraded_agents": hotspots[:5],
        }

    def _collect_devops_snapshot(self) -> Dict[str, Any]:
        report_files = sorted(
            self.devops_reports_dir.glob("scan_*.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if not report_files:
            return {
                "available": False,
                "age_hours": 9999.0,
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
                "issues_found": 0,
                "report_file": "",
            }

        latest = report_files[0]
        data = self._load_json(latest, default={})
        summary = data.get("summary", {}) if isinstance(data, dict) else {}

        return {
            "available": True,
            "report_file": str(latest),
            "age_hours": round(
                self._hours_since(
                    data.get("timestamp", latest.stat().st_mtime) if isinstance(data, dict) else latest.stat().st_mtime
                ),
                2,
            ),
            "critical": int(summary.get("critical", 0)) if isinstance(summary, dict) else 0,
            "high": int(summary.get("high", 0)) if isinstance(summary, dict) else 0,
            "medium": int(summary.get("medium", 0)) if isinstance(summary, dict) else 0,
            "low": int(summary.get("low", 0)) if isinstance(summary, dict) else 0,
            "issues_found": len(data.get("issues", []))
            if isinstance(data, dict) and isinstance(data.get("issues", []), list)
            else 0,
        }

    def _collect_credentials_snapshot(self) -> Dict[str, Any]:
        required_present = [k for k in self.REQUIRED_KEYS if os.getenv(k)]
        required_missing = [k for k in self.REQUIRED_KEYS if not os.getenv(k)]
        optional_present = [k for k in self.OPTIONAL_KEYS if os.getenv(k)]
        optional_missing = [k for k in self.OPTIONAL_KEYS if not os.getenv(k)]

        return {
            "required_present": required_present,
            "required_missing": required_missing,
            "optional_present": optional_present,
            "optional_missing": optional_missing,
            "required_coverage": round(len(required_present) / max(1, len(self.REQUIRED_KEYS)), 3),
            "optional_coverage": round(len(optional_present) / max(1, len(self.OPTIONAL_KEYS)), 3),
        }

    def _collect_initiatives_snapshot(self) -> Dict[str, Any]:
        initiatives = self._load_json(self.sentinel_initiatives_file, default=[])
        if not isinstance(initiatives, list):
            initiatives = []

        now = time.time()
        recent = [item for item in initiatives if now - float(item.get("timestamp", 0.0)) <= 86400]
        by_type: Dict[str, int] = {}
        for item in recent:
            kind = str(item.get("type", "unknown"))
            by_type[kind] = by_type.get(kind, 0) + 1

        return {
            "last_24h_total": len(recent),
            "last_24h_by_type": by_type,
        }

    def _compute_score_components(
        self,
        *,
        jobs: Dict[str, Any],
        metrics: Dict[str, Any],
        devops: Dict[str, Any],
        credentials: Dict[str, Any],
        initiatives: Dict[str, Any],
    ) -> Dict[str, float]:
        reliability = float(metrics.get("overall_success_rate", 1.0))
        if not metrics.get("has_signal", False):
            reliability = 0.60

        schedule_integrity = float(jobs.get("coverage_ratio", 1.0))
        credentials_readiness = float(credentials.get("required_coverage", 0.0))

        devops_penalty = min(
            0.90,
            float(devops.get("critical", 0)) * 0.35
            + float(devops.get("high", 0)) * 0.10
            + min(float(devops.get("age_hours", 0.0)) / 72.0, 1.0) * 0.25,
        )
        devops_health = max(0.0, 1.0 - devops_penalty)

        initiative_signal = min(1.0, float(initiatives.get("last_24h_total", 0)) / 4.0)
        if initiatives.get("last_24h_total", 0) == 0:
            initiative_signal = 0.40

        return {
            "reliability": round(reliability * 0.32, 4),
            "schedule_integrity": round(schedule_integrity * 0.23, 4),
            "credentials_readiness": round(credentials_readiness * 0.20, 4),
            "devops_health": round(devops_health * 0.15, 4),
            "initiative_signal": round(initiative_signal * 0.10, 4),
        }

    def _collect_limitations(
        self,
        jobs: Dict[str, Any],
        metrics: Dict[str, Any],
        devops: Dict[str, Any],
        credentials: Dict[str, Any],
    ) -> List[str]:
        limitations = []
        missing_required = credentials.get("required_missing", [])
        if missing_required:
            limitations.append(
                f"Credenciais críticas ausentes: {', '.join(missing_required)}."
            )
        if jobs.get("unresolved_enabled_jobs"):
            limitations.append(
                f"{len(jobs['unresolved_enabled_jobs'])} automações habilitadas sem flow/template resolvido."
            )
        if not metrics.get("has_signal"):
            limitations.append(
                "Telemetria com baixa sinalização (total_calls=0 no snapshot mais recente)."
            )
        if float(devops.get("age_hours", 0)) > 24:
            limitations.append(
                f"Último DevOps scan está desatualizado ({devops.get('age_hours')}h)."
            )
        if devops.get("available") and int(devops.get("critical", 0)) > 0:
            limitations.append(
                f"DevOps scan recente ainda reporta {devops.get('critical')} achados críticos."
            )
        if metrics.get("degraded_agents"):
            worst = metrics["degraded_agents"][0]
            limitations.append(
                f"Agente degradado detectado: {worst['agent']} (success_rate={worst['success_rate']:.2f})."
            )
        return limitations

    def _collect_growth_potential(
        self,
        jobs: Dict[str, Any],
        metrics: Dict[str, Any],
        credentials: Dict[str, Any],
        initiatives: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "automation_leverage": round(
                min(1.0, jobs.get("enabled_jobs", 0) / 8.0),
                3,
            ),
            "integration_readiness": credentials.get("optional_coverage", 0.0),
            "learning_velocity": round(
                min(1.0, initiatives.get("last_24h_total", 0) / 6.0),
                3,
            ),
            "resilience_headroom": round(
                max(0.0, 1.0 - float(metrics.get("overall_success_rate", 1.0))),
                3,
            ),
        }

    def _build_recommended_actions(
        self,
        *,
        jobs: Dict[str, Any],
        metrics: Dict[str, Any],
        devops: Dict[str, Any],
        credentials: Dict[str, Any],
        initiatives: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        actions: List[Dict[str, Any]] = []

        def add_action(
            action_id: str,
            priority: int,
            title: str,
            rationale: str,
            *,
            automated: bool,
            command: str,
        ) -> None:
            actions.append(
                {
                    "id": action_id,
                    "priority": priority,
                    "title": title,
                    "rationale": rationale,
                    "automated": automated,
                    "command": command,
                }
            )

        missing_required = credentials.get("required_missing", [])
        if missing_required:
            add_action(
                "fill_required_credentials",
                100,
                "Completar credenciais críticas",
                (
                    "Sem essas chaves, partes essenciais de autonomia ficam em modo degradado: "
                    + ", ".join(missing_required)
                ),
                automated=False,
                command="Atualizar .env com credenciais obrigatórias",
            )

        if jobs.get("unresolved_enabled_jobs"):
            add_action(
                "repair_unresolved_automations",
                95,
                "Corrigir automações habilitadas sem destino válido",
                "Há jobs ativos apontando para flow/template ausente, causando perda silenciosa de execução.",
                automated=False,
                command="Revisar config/scheduled_jobs.json e arquivos em flows/ e flow_templates/",
            )

        if (not devops.get("available")) or float(devops.get("age_hours", 0)) > 24:
            add_action(
                "run_devops_scan",
                90,
                "Executar varredura DevOps corretiva",
                "Atualiza diagnóstico de código/dependências e destrava auto-correções priorizadas.",
                automated=True,
                command="AutonomousDevOpsRefactor.run_scan",
            )

        if devops.get("available") and float(devops.get("age_hours", 0)) <= 24 and int(devops.get("critical", 0)) > 0:
            add_action(
                "tune_devops_rules",
                88,
                "Reduzir falso-positivo da análise DevOps",
                (
                    "O scan está recente, mas reporta muitos críticos. "
                    "É preciso calibrar heurísticas para evitar ciclos de correção improdutivos."
                ),
                automated=False,
                command="Ajustar CodexComplianceChecker/ASTAnalyzer e severidades",
            )

        if metrics.get("degraded_agents"):
            add_action(
                "trigger_health_audit",
                85,
                "Executar auditoria de saúde dos agentes",
                "Existem agentes com taxa de sucesso abaixo de 80%; auditoria detecta circuitos e falhas recorrentes.",
                automated=True,
                command="MoonSentinelAgent.health",
            )

        if int(initiatives.get("last_24h_total", 0)) == 0:
            add_action(
                "trigger_skill_discovery",
                70,
                "Disparar descoberta de novas habilidades",
                "Sem iniciativas recentes, o sistema perde velocidade de aprendizado e expansão.",
                automated=True,
                command="SkillAlchemist.discover",
            )

        if not jobs.get("has_autonomy_growth_schedule", False):
            add_action(
                "enable_autonomy_growth_schedule",
                65,
                "Garantir agenda do ciclo de auto-crescimento",
                "A evolução contínua depende de recorrência automática para virar rotina operacional.",
                automated=False,
                command="Adicionar job para flow autonomy_growth_cycle",
            )

        actions.sort(key=lambda item: item["priority"], reverse=True)
        return actions

    def _persist_report(self, folder: str, prefix: str, payload: Dict[str, Any]) -> Path:
        target_dir = self.output_dir / folder
        target_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_path = target_dir / filename
        with open(report_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
        return report_path

    @staticmethod
    def _load_json(path: Path, default: Any) -> Any:
        try:
            if not path.exists():
                return default
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception as exc:
            logger.debug(f"Could not load JSON from {path}: {exc}")
            return default

    @staticmethod
    def _hours_since(value: Any) -> float:
        if value is None:
            return 9999.0
        now = time.time()

        if isinstance(value, (int, float)):
            return max(0.0, (now - float(value)) / 3600.0)

        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value).timestamp()
                return max(0.0, (now - parsed) / 3600.0)
            except Exception:
                return 9999.0

        return 9999.0
