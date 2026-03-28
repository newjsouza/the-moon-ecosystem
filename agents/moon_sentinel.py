"""
agents/moon_sentinel.py
MoonSentinelAgent — O Núcleo de Vontade do The Moon.

O agente mais proativo do ecossistema. Não espera ser chamado.
Age como um sócio vigilante: observa, detecta, propõe e notifica
ANTES que o usuário precise pedir.

RESPONSABILIDADES:
  1. Vigilância de tendências tecnológicas (a cada 4h)
  2. Monitoramento de saúde do ecossistema (a cada 1h)
  3. Proposta e notificação de novas skills (via SkillAlchemist)
  4. Geração de relatórios de iniciativa (08:00 e 20:00)

ASSINATURA IMUTÁVEL (Moon Codex):
  async def _execute(self, task: str, **kwargs) -> TaskResult
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from core.agent_base import AgentBase, AgentPriority, TaskResult
from core.message_bus import MessageBus

logger = logging.getLogger("moon.agents.sentinel")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# How often each watch cycle runs
TECH_WATCH_INTERVAL_HOURS = 4
HEALTH_WATCH_INTERVAL_MINUTES = 60
INITIATIVES_LOG = Path("data/sentinel_initiatives.json")
REPORTS_DIR = Path("data/sentinel_reports")
RESEARCH_REPORTS_DIR = REPORTS_DIR / "research"
IMPLEMENTATION_REPORTS_DIR = REPORTS_DIR / "implementations"
AUTO_IMPLEMENT_ENV = "MOON_SENTINEL_AUTO_IMPLEMENT"
AUTO_IMPLEMENT_COOLDOWN_SECONDS = int(os.getenv("MOON_SENTINEL_IMPL_COOLDOWN_SECONDS", "1800"))
TELEGRAM_CHUNK_SIZE = 3500
TELEGRAM_DEDUP_SECONDS = int(os.getenv("MOON_SENTINEL_TELEGRAM_DEDUP_SECONDS", "21600"))
PLACEHOLDER_HOSTS = {"example.com", "www.example.com", "localhost", "127.0.0.1", "0.0.0.0"}
PLACEHOLDER_TITLES = {"framework a", "framework b", "video x", "paper xyz", "sem titulo"}


class MoonSentinelAgent(AgentBase):
    """
    The proactive vigilance brain of The Moon.

    Runs autonomous watch cycles and pushes insights to the user
    without waiting to be asked.
    """

    def __init__(self, orchestrator=None) -> None:
        super().__init__()
        self.name = "MoonSentinelAgent"
        self.priority = AgentPriority.HIGH
        self.description = "Proactive vigilance, trend watching, ecosystem health, initiative reports"
        self.orchestrator = orchestrator
        self.message_bus = MessageBus()

        # State
        self._last_tech_watch: float = 0.0
        self._last_health_watch: float = 0.0
        self._last_implementation_cycle: float = 0.0
        self._watch_task: Optional[asyncio.Task] = None
        self._initiatives: List[Dict[str, Any]] = []
        self._last_research_report_file: str = ""
        self._last_implementation_report_file: str = ""
        self._telegram_message_fingerprints: Dict[str, float] = {}

        # Subscribe to events from other agents
        self.message_bus.subscribe("alchemist.skill_proposed", self._on_skill_proposed)
        self.message_bus.subscribe("devops.scan_complete", self._on_devops_scan)

        INITIATIVES_LOG.parent.mkdir(parents=True, exist_ok=True)
        RESEARCH_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        IMPLEMENTATION_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        self._load_initiatives()

    # ═══════════════════════════════════════════════════════════
    #  Lifecycle
    # ═══════════════════════════════════════════════════════════

    async def initialize(self) -> None:
        await super().initialize()
        self._watch_task = asyncio.create_task(
            self._sentinel_loop(), name="moon.sentinel.loop"
        )
        logger.info("MoonSentinelAgent initialized — sentinel loop started 🔭")

    async def shutdown(self) -> None:
        if self._watch_task and not self._watch_task.done():
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass
        self._save_initiatives()
        await super().shutdown()

    # ═══════════════════════════════════════════════════════════
    #  _execute — on-demand interface (Moon Codex contract)
    # ═══════════════════════════════════════════════════════════

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        """Handles on-demand commands from the Orchestrator/Telegram."""
        action = task.strip().lower() if task else "status"

        if action in ("status", ""):
            return TaskResult(success=True, data=self._get_status())

        if action == "tech-watch":
            result = await self._watch_tech_trends()
            return TaskResult(success=True, data={"report": result})

        if action == "implement-research":
            report = await self._implement_from_recent_research()
            if report:
                await self._send_telegram_long(
                    self._format_implementation_report(report),
                    parse_mode=None,
                    dedup_key=f"manual-implement:{report.get('execution_id', '')}",
                )
            else:
                await self._send_telegram_long(
                    "SENTINELA - IMPLEMENTACAO NAO EXECUTADA\n"
                    "Motivo: nao ha relatorio de pesquisa com evidencias reais validadas.",
                    parse_mode=None,
                    dedup_key="manual-implement:no-validated-research",
                )
            return TaskResult(success=bool(report), data={"implementation_report": report})

        if action == "health":
            report = await self._watch_ecosystem_health()
            return TaskResult(success=True, data={"health": report})

        if action == "report" or action == "briefing":
            report = await self._generate_initiative_report(send_telegram=True)
            return TaskResult(success=True, data={"report": report})

        if action == "initiatives":
            return TaskResult(success=True, data={"initiatives": self._initiatives[-20:]})

        return TaskResult(
            success=True,
            data={
                "message": (
                    f"Sentinel recebeu: '{task}'. "
                    "Use: status|tech-watch|implement-research|health|report|initiatives"
                )
            }
        )

    # ═══════════════════════════════════════════════════════════
    #  Sentinel Loop — runs forever in background
    # ═══════════════════════════════════════════════════════════

    async def _sentinel_loop(self) -> None:
        """
        Main autonomous loop.
        Every minute checks if it's time for each watch cycle.
        """
        logger.info("Sentinel loop started — watching the horizon 🌐")
        await asyncio.sleep(15)  # Give system time to boot before first cycle

        while True:
            try:
                now = time.time()

                # Tech trend watch every 4 hours
                if now - self._last_tech_watch >= TECH_WATCH_INTERVAL_HOURS * 3600:
                    await self._watch_tech_trends()
                    self._last_tech_watch = time.time()

                # Ecosystem health watch every 60 minutes
                if now - self._last_health_watch >= HEALTH_WATCH_INTERVAL_MINUTES * 60:
                    await self._watch_ecosystem_health()
                    self._last_health_watch = time.time()

                # Scheduled reports (08:00 and 20:00)
                await self._maybe_scheduled_report()

            except asyncio.CancelledError:
                logger.info("Sentinel loop cancelled.")
                break
            except Exception as e:
                logger.error(f"Sentinel loop error: {e}")

            await asyncio.sleep(60)  # Check every minute

    async def _maybe_scheduled_report(self) -> None:
        """Fires the initiative report at configured hours (default 08:00 and 20:00)."""
        try:
            from core.user_profile import get_user_profile
            profile = get_user_profile()
            hour = datetime.now().hour
            minute = datetime.now().minute

            trigger_hours = {
                profile.preferred_briefing_hour,
                profile.preferred_evening_report_hour,
            }

            if hour in trigger_hours and 0 <= minute < 2:
                # Only fire in the first 2 minutes of the trigger hour
                key = f"report_{datetime.now().strftime('%Y%m%d_%H')}"
                if not self._was_initiative_done_today(key):
                    await self._generate_initiative_report(send_telegram=True)
                    self._log_initiative(key, "scheduled_report", {})

        except Exception as e:
            logger.debug(f"_maybe_scheduled_report error: {e}")

    # ═══════════════════════════════════════════════════════════
    #  1. Tech Trend Watch
    # ═══════════════════════════════════════════════════════════

    async def _watch_tech_trends(self) -> str:
        """
        Fetches and synthesizes tech trends from ResearcherAgent + NewsMonitorAgent.
        Sends top insights to Telegram if notify_on_trend is enabled.
        """
        logger.info("Sentinel: starting tech trend watch cycle 🔭")
        cycle_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        try:
            from core.user_profile import get_user_profile
            profile = get_user_profile()
        except Exception:
            profile = None

        # The user specifically requested tracking these topics:
        base_topics = ["VibeCoding e IA Generativa", "Novidades AI (Anthropic, GPT, Gemini, Groq, Alibaba, DeepSeek)"]
        
        user_topics = (profile.watchlist_topics if profile else [])
        topics = base_topics + [t for t in user_topics if t not in base_topics][:2]

        findings: list[str] = []
        detailed_packets: list[dict[str, Any]] = []

        for topic in topics[:3]:
            packet = await self._research_topic_detailed(topic)
            if packet:
                detailed_packets.append(packet)
                logger.info(f"Sentinel: researched '{topic}' with detailed raw packet")
            await asyncio.sleep(2)

        validation = self._validate_research_packets(detailed_packets)
        validated_packets = validation["valid_packets"]
        rejected_packets = validation["rejected_packets"]

        if not validated_packets:
            rejected_report = self._format_research_rejected_report(
                cycle_id=cycle_id,
                topics=topics[:3],
                rejected_packets=rejected_packets,
            )
            rejected_payload = {
                "cycle_id": cycle_id,
                "topics": topics[:3],
                "status": "rejected_no_real_evidence",
                "validation": validation,
                "summary_report": rejected_report,
                "detailed_report": "",
                "research_packets": [],
                "raw_packets_count": len(detailed_packets),
                "timestamp": datetime.now().isoformat(),
            }
            research_report_file = self._persist_report(
                directory=RESEARCH_REPORTS_DIR,
                prefix="tech_watch",
                payload=rejected_payload,
            )
            self._last_research_report_file = str(research_report_file)
            self._log_initiative(
                f"tech_watch_rejected_{cycle_id}",
                "tech_trend_validation_failed",
                {
                    "cycle_id": cycle_id,
                    "topics": topics[:3],
                    "rejected_count": len(rejected_packets),
                    "raw_packets_count": len(detailed_packets),
                    "detailed_report_file": str(research_report_file),
                },
            )

            if profile is None or (profile.notify_on_trend and profile.should_notify_now()):
                dedup_key = f"trend-rejected:{self._content_signature({'topics': topics[:3], 'rejected': rejected_packets})}"
                await self._send_telegram_long(rejected_report, parse_mode=None, dedup_key=dedup_key)
            logger.info("Sentinel: watch cycle finished without real evidence")
            return rejected_report

        for packet in validated_packets:
            findings.append(f"**{packet.get('topic', 'N/A')}**: {str(packet.get('synthesis', ''))[:260]}")

        content_signature = self._content_signature(
            [
                {
                    "topic": p.get("topic", ""),
                    "synthesis": p.get("synthesis", ""),
                    "references": [r.get("url", "") for r in p.get("references", []) if isinstance(r, dict)],
                }
                for p in validated_packets
            ]
        )
        report = self._format_trend_report(
            findings,
            cycle_id=cycle_id,
            validated_topics=len(validated_packets),
            total_references=validation["total_real_references"],
            content_signature=content_signature,
        )
        detailed_report = self._format_detailed_trend_report(
            validated_packets,
            cycle_id=cycle_id,
            content_signature=content_signature,
            validation=validation,
        )

        research_payload = {
            "cycle_id": cycle_id,
            "topics": topics[:3],
            "status": "validated",
            "findings": findings,
            "summary_report": report,
            "detailed_report": detailed_report,
            "research_packets": validated_packets,
            "validation": validation,
            "content_signature": content_signature,
            "timestamp": datetime.now().isoformat(),
        }
        research_report_file = self._persist_report(
            directory=RESEARCH_REPORTS_DIR,
            prefix="tech_watch",
            payload=research_payload,
        )
        self._last_research_report_file = str(research_report_file)

        # Save full findings for dashboard and post-analysis
        self._log_initiative(
            f"tech_watch_{cycle_id}",
            "tech_trend",
            {
                "cycle_id": cycle_id,
                "topics": topics[:3],
                "findings": findings,
                "validated_topics": len(validated_packets),
                "total_references": validation["total_real_references"],
                "content_signature": content_signature,
                "report": report,
                "detailed_report_file": str(research_report_file),
            },
        )

        # Only notify if profile allows
        if profile is None or (profile.notify_on_trend and profile.should_notify_now()):
            await self._send_telegram(
                report,
                dedup_key=f"trend-summary:{content_signature}",
            )
            if detailed_report:
                await self._send_telegram_long(
                    detailed_report,
                    parse_mode=None,
                    dedup_key=f"trend-detailed:{content_signature}",
                )

        # Optional autonomous implementation cycle based on researched findings
        if self._should_auto_implement():
            implementation_report = await self._auto_implement_research_improvements(
                detailed_packets=validated_packets,
                summary_report=report,
            )
            if implementation_report:
                if profile is None or (profile.notify_on_trend and profile.should_notify_now()):
                    await self._send_telegram_long(
                        self._format_implementation_report(implementation_report),
                        parse_mode=None,
                        dedup_key=f"trend-implementation:{implementation_report.get('execution_id', '')}",
                    )

        return report

    async def _llm_trend_synthesis(self, topics: List[str]) -> List[str]:
        """Fallback: synthesize trends via LLM when ResearcherAgent is unavailable."""
        groq_api_key = os.getenv("GROQ_API_KEY", GROQ_API_KEY)
        if not groq_api_key:
            return []
        try:
            from groq import AsyncGroq
            client = AsyncGroq(api_key=groq_api_key)
            topics_str = ", ".join(topics)
            completion = await client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{
                    "role": "system",
                    "content": (
                        "Você é um analista de tendências tecnológicas especializado em IA e automação. "
                        "Forneça insights concisos e práticos sobre as tendências solicitadas. "
                        "Responda em português BR, em formato de bullet points curtos."
                    )
                }, {
                    "role": "user",
                    "content": (
                        f"Quais são as principais tendências e novidades recentes em: {topics_str}?\n"
                        "Foco em novidades práticas, ferramentas open-source, e oportunidades. "
                        "Máximo 4 pontos, cada um com no máximo 150 caracteres."
                    )
                }],
                max_tokens=600,
                temperature=0.4,
            )
            raw = completion.choices[0].message.content.strip()
            lines = [l.strip().lstrip("•-*").strip() for l in raw.split("\n") if l.strip()]
            return lines[:4]
        except Exception as e:
            logger.warning(f"Sentinel: LLM trend synthesis failed: {e}")
            return []

    def _format_trend_report(
        self,
        findings: List[str],
        *,
        cycle_id: str = "",
        validated_topics: int = 0,
        total_references: int = 0,
        content_signature: str = "",
    ) -> str:
        now = datetime.now().strftime("%d/%m/%Y %H:%M")
        lines = [f"🔭 *Sentinel — Tendências Detectadas*", f"🕐 {now}", ""]
        if cycle_id:
            lines.append(f"🆔 Ciclo: `{cycle_id}`")
        if validated_topics or total_references:
            lines.append(
                f"✅ Validação real: {validated_topics} tópicos, {total_references} evidências verificadas"
            )
        if content_signature:
            lines.append(f"🔐 Assinatura: `{content_signature[:16]}`")
        if lines[-1]:
            lines.append("")
        for i, f in enumerate(findings, 1):
            lines.append(f"{i}. {f[:280]}")
        lines.append("\n_Próxima varredura em 4 horas._")
        return "\n".join(lines)

    async def _research_topic_detailed(self, topic: str) -> Dict[str, Any]:
        """Executa pesquisa de um tópico e retorna pacote estruturado com evidências."""
        if not self.orchestrator:
            return {}

        # Prioridade: DeepWebResearchAgent (GitHub + HF + Arxiv)
        deep_agent = self.orchestrator._agents.get("DeepWebResearchAgent")
        if deep_agent:
            try:
                result = await asyncio.wait_for(
                    deep_agent.execute(
                        "research",
                        query=topic,
                        sources=["github", "huggingface", "arxiv"],
                        max_per_source=5,
                        save_to_memory=True,
                    ),
                    timeout=90.0,
                )
                if result.success and isinstance(result.data, dict):
                    return self._normalize_deep_research_payload(topic, result.data)
            except Exception as e:
                logger.warning(f"Sentinel: deep research failed for '{topic}': {e}")

        # Fallback: ResearcherAgent (web + youtube + deep content)
        researcher = self.orchestrator._agents.get("ResearcherAgent")
        if researcher:
            try:
                result = await asyncio.wait_for(
                    researcher.execute(topic, action="research"),
                    timeout=60.0,
                )
                if result.success and isinstance(result.data, dict):
                    return self._normalize_researcher_payload(topic, result.data)
            except Exception as e:
                logger.warning(f"Sentinel: researcher fallback failed for '{topic}': {e}")

        return {}

    def _normalize_deep_research_payload(self, topic: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        results = payload.get("results", []) if isinstance(payload.get("results"), list) else []
        sources_used = payload.get("sources_used", []) if isinstance(payload.get("sources_used"), list) else []
        references = []
        for item in results[:15]:
            references.append(
                {
                    "source": item.get("source", "unknown"),
                    "title": item.get("title", "")[:120],
                    "url": item.get("url", ""),
                    "description": str(item.get("description", ""))[:240],
                }
            )
        return {
            "topic": topic,
            "source_agent": "DeepWebResearchAgent",
            "sources_used": sources_used,
            "total_results": int(payload.get("total_results", len(results))),
            "synthesis": str(payload.get("synthesis", "")).strip(),
            "references": references,
            "raw_payload": {
                "query": payload.get("query", topic),
                "timestamp": payload.get("timestamp", ""),
            },
        }

    def _normalize_researcher_payload(self, topic: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        vault_file = str(payload.get("vault_file", ""))
        summary = str(payload.get("summary", "")).strip()
        references = []
        synthesis = summary
        sources_used = ["web", "youtube"]
        total_results = 0
        raw_payload: Dict[str, Any] = {"vault_file": vault_file}

        if vault_file and Path(vault_file).exists():
            try:
                with open(vault_file, encoding="utf-8") as handle:
                    vault_data = json.load(handle)
                web_results = vault_data.get("web_results", []) if isinstance(vault_data.get("web_results"), list) else []
                video_results = vault_data.get("video_results", []) if isinstance(vault_data.get("video_results"), list) else []
                synthesis = str(vault_data.get("llm_synthesis", synthesis)).strip()
                total_results = len(web_results) + len(video_results)

                for item in web_results[:6]:
                    references.append(
                        {
                            "source": "web",
                            "title": str(item.get("title", ""))[:120],
                            "url": item.get("link", ""),
                            "description": str(item.get("snippet", ""))[:240],
                        }
                    )
                for item in video_results[:4]:
                    references.append(
                        {
                            "source": "youtube",
                            "title": str(item.get("title", ""))[:120],
                            "url": item.get("link", ""),
                            "description": str(item.get("snippet", ""))[:240],
                        }
                    )
                raw_payload["timestamp"] = vault_data.get("timestamp", "")
            except Exception as e:
                logger.warning(f"Sentinel: failed to parse vault file {vault_file}: {e}")

        return {
            "topic": topic,
            "source_agent": "ResearcherAgent",
            "sources_used": sources_used,
            "total_results": total_results,
            "synthesis": synthesis,
            "references": references,
            "raw_payload": raw_payload,
        }

    @staticmethod
    def _content_signature(payload: Any) -> str:
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def _looks_placeholder_url(url: str) -> bool:
        raw = (url or "").strip().lower()
        if not raw:
            return True
        parsed = urlparse(raw)
        host = parsed.netloc.lower()
        if host in PLACEHOLDER_HOSTS:
            return True
        placeholder_fragments = ("example.com", "your_key_here", "localhost", "127.0.0.1", "/watch?v=abc")
        return any(fragment in raw for fragment in placeholder_fragments)

    @staticmethod
    def _looks_synthetic_synthesis(text: str) -> bool:
        raw = (text or "").strip().lower()
        if len(raw) < 40:
            return True
        blocked = {
            "sem síntese disponível.",
            "sem sintese disponível.",
            "sem sintese disponivel.",
            "descobertas apontam oportunidade de melhorar autonomia e segurança do pipeline.",
            "descobertas apontam oportunidade de melhorar autonomia e seguranca do pipeline.",
        }
        if raw in blocked:
            return True
        return "placeholder" in raw

    def _is_reference_real(self, ref: Dict[str, Any]) -> bool:
        if not isinstance(ref, dict):
            return False
        title = str(ref.get("title", "")).strip().lower()
        url = str(ref.get("url", "")).strip()
        if title in PLACEHOLDER_TITLES:
            return False
        if self._looks_placeholder_url(url):
            return False
        return True

    def _validate_research_packets(self, packets: List[Dict[str, Any]]) -> Dict[str, Any]:
        valid_packets: list[dict[str, Any]] = []
        rejected_packets: list[dict[str, Any]] = []
        total_real_references = 0

        for pkt in packets:
            topic = str(pkt.get("topic", "")).strip() or "N/A"
            synthesis = str(pkt.get("synthesis", "")).strip()
            refs = pkt.get("references", []) if isinstance(pkt.get("references"), list) else []
            real_refs = [ref for ref in refs if self._is_reference_real(ref)]
            total_results = int(pkt.get("total_results", 0) or 0)

            reasons = []
            if not topic or topic == "N/A":
                reasons.append("topic_invalido")
            if total_results <= 0:
                reasons.append("sem_resultados")
            if not real_refs:
                reasons.append("sem_referencias_reais")
            if self._looks_synthetic_synthesis(synthesis):
                reasons.append("sintese_generica_ou_placeholder")

            if reasons:
                rejected_packets.append(
                    {
                        "topic": topic,
                        "reasons": reasons,
                        "total_results": total_results,
                        "references_count": len(refs),
                        "real_references_count": len(real_refs),
                    }
                )
                continue

            sanitized = dict(pkt)
            sanitized["references"] = real_refs
            sanitized["validation"] = {
                "references_count": len(refs),
                "real_references_count": len(real_refs),
                "synthesis_valid": True,
            }
            valid_packets.append(sanitized)
            total_real_references += len(real_refs)

        return {
            "valid_packets": valid_packets,
            "rejected_packets": rejected_packets,
            "total_packets": len(packets),
            "validated_packets_count": len(valid_packets),
            "rejected_packets_count": len(rejected_packets),
            "total_real_references": total_real_references,
        }

    def _format_research_rejected_report(
        self,
        *,
        cycle_id: str,
        topics: List[str],
        rejected_packets: List[Dict[str, Any]],
    ) -> str:
        lines = [
            "SENTINELA - CICLO EXECUTADO SEM EVIDENCIA REAL",
            f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
            f"ID do ciclo: {cycle_id}",
            f"Topicos executados: {', '.join(topics) if topics else 'N/A'}",
            "",
            "Nenhum relatorio detalhado foi publicado porque faltaram evidencias verificaveis.",
            "Auto-implementacao deste ciclo: NAO EXECUTADA",
        ]
        if rejected_packets:
            lines.append("")
            lines.append("Motivos de rejeicao detectados:")
            for item in rejected_packets[:6]:
                lines.append(
                    f"- {item.get('topic', 'N/A')}: {', '.join(item.get('reasons', []))}"
                )
        return "\n".join(lines)

    def _format_detailed_trend_report(
        self,
        packets: List[Dict[str, Any]],
        *,
        cycle_id: str = "",
        content_signature: str = "",
        validation: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Monta relatório detalhado com resultados reais de pesquisa executada."""
        if not packets:
            return ""

        lines = [
            "RELATORIO DETALHADO DE PESQUISA - SENTINELA",
            f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
            "",
        ]
        if cycle_id:
            lines.append(f"ID do ciclo: {cycle_id}")
        if content_signature:
            lines.append(f"Assinatura de conteudo: {content_signature[:16]}")
        if validation:
            lines.append(
                "Validacao: "
                f"{validation.get('validated_packets_count', 0)} topicos validos, "
                f"{validation.get('total_real_references', 0)} referencias reais"
            )
        if len(lines) > 3:
            lines.append("")

        for idx, packet in enumerate(packets, 1):
            lines.append(f"TOPICO {idx}: {packet.get('topic', 'N/A')}")
            lines.append(
                f"Agente: {packet.get('source_agent', 'N/A')} | "
                f"Resultados: {packet.get('total_results', 0)} | "
                f"Fontes: {', '.join(packet.get('sources_used', [])) or 'N/A'}"
            )
            synthesis = str(packet.get("synthesis", "")).strip() or "Sem síntese disponível."
            lines.append(f"Sintese: {synthesis[:900]}")
            refs = packet.get("references", []) if isinstance(packet.get("references"), list) else []
            if refs:
                lines.append("Evidencias coletadas:")
                for ref in refs[:6]:
                    src = ref.get("source", "fonte")
                    title = ref.get("title", "sem titulo")
                    url = ref.get("url", "")
                    lines.append(f"- [{src}] {title}")
                    if url:
                        lines.append(f"  {url}")
            lines.append("")

        return "\n".join(lines).strip()

    def _should_auto_implement(self) -> bool:
        raw = os.getenv(AUTO_IMPLEMENT_ENV, "true").strip().lower()
        enabled = raw in {"1", "true", "yes", "on", "sim"}
        if not enabled:
            return False
        if AUTO_IMPLEMENT_COOLDOWN_SECONDS <= 0:
            return True
        return (time.time() - self._last_implementation_cycle) >= AUTO_IMPLEMENT_COOLDOWN_SECONDS

    def _build_implementation_actions(self, packets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        text_blob = " ".join(str(p.get("synthesis", "")) for p in packets).lower()
        references_count = sum(len(p.get("references", [])) for p in packets if isinstance(p, dict))

        actions = [
            {
                "id": "plan_architecture",
                "title": "Planejamento técnico dos aprimoramentos",
                "agent": "MoonPlanAgent",
                "task": "eng " + self._build_planning_prompt(packets),
                "kwargs": {},
                "reason": "Transformar achados de pesquisa em plano técnico implementável.",
            },
            {
                "id": "autonomy_apply",
                "title": "Aplicação automática de melhorias priorizadas",
                "agent": "AutonomyEvolutionAgent",
                "task": "assess_and_apply",
                "kwargs": {"top_n": 3},
                "reason": "Executar melhorias automáticas de maior impacto no ecossistema.",
            },
        ]

        if references_count > 0:
            actions.append(
                {
                    "id": "skill_discovery",
                    "title": "Descoberta e avaliação de novas ferramentas",
                    "agent": "SkillAlchemist",
                    "task": "discover",
                    "kwargs": {},
                    "reason": "Converter descobertas externas em novas capacidades internas.",
                }
            )

        risk_keywords = ("vulnerab", "security", "risco", "falha", "erro", "bug", "critical")
        if any(k in text_blob for k in risk_keywords):
            actions.append(
                {
                    "id": "devops_auto_fix",
                    "title": "Auto-correção guiada por DevOps",
                    "agent": "AutonomousDevOpsRefactor",
                    "task": "auto_fix",
                    "kwargs": {"issues": [p.get("synthesis", "")[:200] for p in packets[:3]]},
                    "reason": "Sintese da pesquisa indicou riscos técnicos que exigem correção automática.",
                }
            )

        actions.append(
            {
                "id": "code_review",
                "title": "Revisão de segurança e regressão pós-implementação",
                "agent": "MoonReviewAgent",
                "task": "auto",
                "kwargs": {},
                "reason": "Garantir integridade após aplicação automática dos aprimoramentos.",
            }
        )
        return actions

    def _build_planning_prompt(self, packets: List[Dict[str, Any]]) -> str:
        snippets = []
        for pkt in packets[:3]:
            refs = pkt.get("references", []) if isinstance(pkt.get("references"), list) else []
            top_titles = ", ".join(r.get("title", "") for r in refs[:3] if r.get("title"))
            snippets.append(
                f"Tópico: {pkt.get('topic', 'N/A')} | "
                f"Síntese: {str(pkt.get('synthesis', ''))[:280]} | "
                f"Evidências: {top_titles[:240]}"
            )
        joined = " || ".join(snippets)
        return (
            "Defina um plano técnico para implementar melhorias no The Moon a partir destes achados: "
            + joined
        )[:1800]

    async def _auto_implement_research_improvements(
        self,
        detailed_packets: List[Dict[str, Any]],
        summary_report: str,
    ) -> Optional[Dict[str, Any]]:
        if not self.orchestrator:
            return None
        if not detailed_packets:
            return None

        execution_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        packet_validation = self._validate_research_packets(detailed_packets)
        validated_packets = packet_validation["valid_packets"]
        if not validated_packets:
            return None

        actions = self._build_implementation_actions(validated_packets)
        execution_results = []

        for action in actions:
            started_at = time.perf_counter()
            try:
                result = await self.orchestrator._call_agent(
                    action["agent"],
                    action["task"],
                    timeout=180.0,
                    **action.get("kwargs", {}),
                )
            except Exception as e:
                result = TaskResult(success=False, error=str(e))
            duration_sec = round(time.perf_counter() - started_at, 3)

            execution_results.append(
                {
                    "id": action["id"],
                    "title": action["title"],
                    "agent": action["agent"],
                    "reason": action["reason"],
                    "success": result.success,
                    "error": result.error,
                    "duration_sec": duration_sec,
                    "result_summary": str(result.data)[:600] if result.data is not None else "",
                }
            )

        overall_success = all(item["success"] for item in execution_results)
        real_result_count = sum(1 for item in execution_results if item.get("result_summary"))
        payload = {
            "execution_id": execution_id,
            "timestamp": datetime.now().isoformat(),
            "summary_report": summary_report,
            "research_topics": [pkt.get("topic", "N/A") for pkt in validated_packets],
            "validated_packets_count": packet_validation["validated_packets_count"],
            "total_real_references": packet_validation["total_real_references"],
            "source_research_report_file": self._last_research_report_file,
            "actions_planned": actions,
            "actions_executed": execution_results,
            "real_result_count": real_result_count,
            "overall_success": overall_success,
        }
        report_file = self._persist_report(
            directory=IMPLEMENTATION_REPORTS_DIR,
            prefix="implementation",
            payload=payload,
        )
        payload["report_file"] = str(report_file)

        self._last_implementation_cycle = time.time()
        self._last_implementation_report_file = str(report_file)
        self._log_initiative(
            f"research_implementation_{execution_id}",
            "research_implementation",
            {
                "execution_id": execution_id,
                "overall_success": overall_success,
                "report_file": str(report_file),
                "actions_count": len(execution_results),
                "real_result_count": real_result_count,
            },
        )
        return payload

    async def _implement_from_recent_research(self) -> Optional[Dict[str, Any]]:
        """Executa implementação automática usando o relatório de pesquisa mais recente."""
        latest = None
        if self._last_research_report_file and Path(self._last_research_report_file).exists():
            latest = Path(self._last_research_report_file)
        else:
            candidates = sorted(
                RESEARCH_REPORTS_DIR.glob("tech_watch_*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if candidates:
                latest = candidates[0]

        if not latest:
            return None

        try:
            with open(latest, encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception as e:
            logger.warning(f"Sentinel: failed to load latest research report: {e}")
            return None

        packets = payload.get("research_packets", [])
        summary_report = payload.get("summary_report", "")
        if not isinstance(packets, list):
            return None
        validation = self._validate_research_packets(packets)
        if not validation["valid_packets"]:
            logger.info("Sentinel: implement-research aborted (no validated research packets)")
            return None
        return await self._auto_implement_research_improvements(
            validation["valid_packets"],
            summary_report,
        )

    @staticmethod
    def _persist_report(directory: Path, prefix: str, payload: Dict[str, Any]) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        report_file = directory / f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        serializable_payload = dict(payload)
        serializable_payload.setdefault("report_file", str(report_file))
        with open(report_file, "w", encoding="utf-8") as handle:
            json.dump(serializable_payload, handle, ensure_ascii=False, indent=2)
        payload.setdefault("report_file", str(report_file))
        return report_file

    def _format_implementation_report(self, payload: Dict[str, Any]) -> str:
        lines = [
            "RELATORIO FINAL DE IMPLEMENTACAO - SENTINELA",
            f"Data: {payload.get('timestamp', '')}",
            f"ID da execucao: {payload.get('execution_id', '')}",
            f"Topicos: {', '.join(payload.get('research_topics', []))}",
            (
                "Evidencias reais: "
                f"{payload.get('validated_packets_count', 0)} topicos validados, "
                f"{payload.get('total_real_references', 0)} referencias"
            ),
            f"Status geral: {'SUCESSO' if payload.get('overall_success') else 'PARCIAL/FALHA'}",
            (
                "Confirmacao de retorno real: "
                f"{payload.get('real_result_count', 0)}/{len(payload.get('actions_executed', []))} acoes com resultado"
            ),
            "",
            "Execucao por acao:",
        ]
        for item in payload.get("actions_executed", []):
            status = "OK" if item.get("success") else "FALHA"
            lines.append(
                f"- {item.get('title', item.get('id', 'acao'))} | "
                f"Agente: {item.get('agent', 'N/A')} | Status: {status} | "
                f"Duracao: {item.get('duration_sec', 0)}s"
            )
            if item.get("error"):
                lines.append(f"  erro: {str(item.get('error'))[:220]}")
            elif item.get("result_summary"):
                lines.append(f"  resultado: {str(item.get('result_summary'))[:260]}")

        report_file = payload.get("report_file", "")
        if report_file:
            lines.append("")
            lines.append(f"Arquivo completo: {report_file}")
        return "\n".join(lines)

    # ═══════════════════════════════════════════════════════════
    #  2. Ecosystem Health Watch
    # ═══════════════════════════════════════════════════════════

    async def _watch_ecosystem_health(self) -> Dict[str, Any]:
        """
        Monitors agents health. If circuit breakers are open or agents are
        failing, proposes auto-correction and notifies the user.
        """
        logger.info("Sentinel: checking ecosystem health 🩺")
        issues = []
        healthy = []

        if self.orchestrator:
            for name, circuit in self.orchestrator._circuits.items():
                if circuit.open:
                    issues.append(f"⚠️ Agente `{name}` — circuit ABERTO (falhas consecutivas)")
                else:
                    healthy.append(name)

        if issues:
            self._log_initiative("health_issue", "ecosystem_health", {"issues": issues})
            try:
                from core.user_profile import get_user_profile
                profile = get_user_profile()
                if profile.notify_on_health_issue and profile.should_notify_now():
                    msg = (
                        "🩺 *Sentinel — Alerta de Saúde*\n\n"
                        + "\n".join(issues)
                        + "\n\n_Tentando auto-correção via AutonomousDevOpsRefactor..._"
                    )
                    await self._send_telegram(msg)
            except Exception:
                pass

            # Attempt auto-correction
            if self.orchestrator and "AutonomousDevOpsRefactor" in self.orchestrator._agents:
                try:
                    await asyncio.wait_for(
                        self.orchestrator._agents["AutonomousDevOpsRefactor"].execute(
                            "auto_fix", issues=issues
                        ),
                        timeout=30.0,
                    )
                except Exception as e:
                    logger.warning(f"Sentinel: auto-correction attempt failed: {e}")

        return {
            "healthy_agents": len(healthy),
            "issues": issues,
            "checked_at": datetime.now().isoformat(),
        }

    # ═══════════════════════════════════════════════════════════
    #  3. New Skill Proposal (triggered by MessageBus event)
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _extract_payload(message_or_payload: Any) -> Dict[str, Any]:
        """
        MessageBus envia objetos Message; testes podem enviar dict diretamente.
        Esta função normaliza ambos os formatos.
        """
        if isinstance(message_or_payload, dict):
            return message_or_payload
        payload = getattr(message_or_payload, "payload", None)
        return payload if isinstance(payload, dict) else {}

    async def _on_skill_proposed(self, message_or_payload: Any) -> None:
        """
        Called when SkillAlchemist proposes a new skill.
        Evaluates it and, if approved, notifies the user for confirmation
        before integration (respects approve_before_skill_integration).
        """
        payload = self._extract_payload(message_or_payload)
        skill_name = payload.get("skill", "unknown")
        skill_path = payload.get("path", "")
        logger.info(f"Sentinel: new skill proposed — {skill_name}")

        self._log_initiative(
            f"skill_proposed_{skill_name}",
            "skill_discovery",
            {"skill": skill_name, "path": skill_path}
        )

        try:
            from core.user_profile import get_user_profile
            profile = get_user_profile()

            if not (profile.notify_on_new_skill and profile.should_notify_now()):
                return

            if profile.approve_before_skill_integration:
                msg = (
                    f"⚗️ *Sentinel — Nova Skill Descoberta!*\n\n"
                    f"📦 **{skill_name}**\n"
                    f"📁 `{skill_path}`\n\n"
                    f"O SkillAlchemist descobriu e avaliou esta ferramenta.\n"
                    f"Ela passou no sandbox e na verificação de compliance.\n\n"
                    f"✅ Responda *aprovar {skill_name}* para integrar ao ecossistema\n"
                    f"❌ Responda *rejeitar {skill_name}* para descartar"
                )
            else:
                msg = (
                    f"⚗️ *Sentinel — Nova Skill Integrada!*\n\n"
                    f"📦 **{skill_name}** foi integrada automaticamente ao ecossistema.\n"
                    f"📁 `{skill_path}`"
                )

            await self._send_telegram(msg)

        except Exception as e:
            logger.error(f"Sentinel: _on_skill_proposed error: {e}")

    async def _on_devops_scan(self, message_or_payload: Any) -> None:
        """Called when AutonomousDevOpsRefactor completes a scan."""
        payload = self._extract_payload(message_or_payload)
        issues_found = payload.get("issues_found", 0)
        if not issues_found:
            summary = payload.get("summary", {})
            if isinstance(summary, dict):
                issues_found = int(
                    summary.get("critical", 0)
                    + summary.get("high", 0)
                    + summary.get("medium", 0)
                    + summary.get("low", 0)
                )
        if issues_found > 0:
            self._log_initiative(
                f"devops_issues_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "devops_scan",
                payload,
            )
            logger.info(f"Sentinel: DevOps scan found {issues_found} issues")

    # ═══════════════════════════════════════════════════════════
    #  4. Initiative Report (Morning & Evening)
    # ═══════════════════════════════════════════════════════════

    async def _generate_initiative_report(self, send_telegram: bool = True) -> str:
        """
        Generates a rich report of what The Moon did proactively.
        Not just 'N tasks scheduled' — actual value delivered.
        """
        logger.info("Sentinel: generating initiative report 📋")

        try:
            from core.user_profile import get_user_profile
            profile = get_user_profile()
            greeting = profile.greeting()
            name = profile.name
        except Exception:
            greeting = "Olá"
            name = "Johnathan"

        # Collect recent initiatives (last 24h)
        now = time.time()
        recent = [
            i for i in self._initiatives
            if now - i.get("timestamp", 0) < 86400
        ]

        # Build report sections
        sections = []

        # What we discovered
        discoveries = [i for i in recent if i.get("type") == "skill_discovery"]
        if discoveries:
            items = "\n".join(f"  ⚗️ {d['key']}" for d in discoveries[:3])
            sections.append(f"*🔬 Descobertas:*\n{items}")

        # Trends watched
        watches = [i for i in recent if i.get("type") == "tech_trend"]
        if watches:
            sections.append(f"*🔭 Tendências monitoradas:* {len(watches)} ciclos de vigilância")

        # Health checks
        health_issues = [i for i in recent if i.get("type") == "ecosystem_health"]
        if health_issues:
            issue_count = sum(len(i.get("data", {}).get("issues", [])) for i in health_issues)
            sections.append(f"*🩺 Saúde:* {len(health_issues)} verificações, {issue_count} alertas")

        # Automated implementation cycles
        impl_cycles = [i for i in recent if i.get("type") == "research_implementation"]
        if impl_cycles:
            success_count = sum(
                1 for i in impl_cycles if i.get("data", {}).get("overall_success", False)
            )
            sections.append(
                f"*🛠️ Implementações automáticas:* {len(impl_cycles)} ciclos, {success_count} com sucesso total"
            )

        # Reports generated
        reports = [i for i in recent if i.get("type") == "scheduled_report"]

        # Enrich with actual LLM insight if available
        llm_insight = await self._generate_llm_insight(profile if profile else None)

        now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
        hour = datetime.now().hour
        report_type = "☀️ Matinal" if hour < 15 else "🌙 Noturno"

        lines = [
            f"🌕 *The Moon — Relatório {report_type}*",
            f"{greeting}",
            f"🕐 {now_str}",
            "━━━━━━━━━━━━━━━━━━━━━━",
        ]

        if sections:
            lines.append("\n*O que fiz hoje por você:*")
            lines.extend(sections)
        else:
            lines.append("\n*Sistema operando normalmente.*\n_Vigilância contínua ativa._")

        if llm_insight:
            lines.append("\n━━━━━━━━━━━━━━━━━━━━━━")
            lines.append(f"*💡 Insight do Momento:*\n{llm_insight}")

        lines.append("\n━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("_Use /sentinel para mais detalhes._")

        report = "\n".join(lines)

        if send_telegram:
            await self._send_telegram(report)

        return report

    async def _generate_llm_insight(self, profile) -> str:
        """Generates a personalized insight/tip via LLM."""
        groq_api_key = os.getenv("GROQ_API_KEY", GROQ_API_KEY)
        if not groq_api_key:
            return ""
        try:
            from groq import AsyncGroq
            client = AsyncGroq(api_key=groq_api_key)
            interests = ", ".join((profile.interests if profile else []) or ["IA, automação"])
            completion = await client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{
                    "role": "system",
                    "content": (
                        "Você é um assistente de IA proativo. Gere um insight ou dica prática "
                        "e acionável de 1-2 frases para um desenvolvedor focado nos tópicos dados. "
                        "Seja direto, útil e específico. Responda em português BR."
                    )
                }, {
                    "role": "user",
                    "content": f"Interesses: {interests}. Dê um insight valioso e prático para hoje."
                }],
                max_tokens=150,
                temperature=0.7,
            )
            return completion.choices[0].message.content.strip()
        except Exception as e:
            logger.debug(f"Sentinel: LLM insight failed: {e}")
            return ""

    # ═══════════════════════════════════════════════════════════
    #  Telegram Notifier
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _split_telegram_chunks(text: str, max_chars: int = TELEGRAM_CHUNK_SIZE) -> List[str]:
        """Divide textos longos em blocos seguros para Telegram."""
        if len(text) <= max_chars:
            return [text]

        chunks: list[str] = []
        current: list[str] = []
        current_len = 0
        for line in text.splitlines(keepends=True):
            if current_len + len(line) > max_chars and current:
                chunks.append("".join(current).strip())
                current = [line]
                current_len = len(line)
            else:
                current.append(line)
                current_len += len(line)
        if current:
            chunks.append("".join(current).strip())
        return [c for c in chunks if c]

    def _purge_old_telegram_fingerprints(self) -> None:
        if TELEGRAM_DEDUP_SECONDS <= 0:
            return
        now = time.time()
        stale = [
            key
            for key, ts in self._telegram_message_fingerprints.items()
            if now - ts > TELEGRAM_DEDUP_SECONDS
        ]
        for key in stale:
            self._telegram_message_fingerprints.pop(key, None)

    @staticmethod
    def _build_telegram_fingerprint(
        text: str,
        *,
        parse_mode: Optional[str],
        dedup_key: str = "",
    ) -> str:
        normalized = " ".join((text or "").split())
        base = f"{dedup_key}|{parse_mode or 'plain'}|{normalized}"
        return hashlib.sha256(base.encode("utf-8")).hexdigest()

    async def _send_telegram_long(
        self,
        text: str,
        parse_mode: Optional[str] = None,
        dedup_key: str = "",
    ) -> bool:
        """Envia relatório longo em múltiplas mensagens sequenciais."""
        chunks = self._split_telegram_chunks(text, max_chars=TELEGRAM_CHUNK_SIZE)
        if not chunks:
            return False
        delivered_any = False
        for idx, chunk in enumerate(chunks):
            chunk_key = f"{dedup_key}:chunk:{idx + 1}/{len(chunks)}" if dedup_key else ""
            sent = await self._send_telegram(
                chunk,
                parse_mode=parse_mode,
                dedup_key=chunk_key,
            )
            delivered_any = delivered_any or sent
            await asyncio.sleep(0.15)
        return delivered_any

    async def _send_telegram(
        self,
        text: str,
        parse_mode: Optional[str] = "Markdown",
        dedup_key: str = "",
    ) -> bool:
        """Sends a message to Telegram."""
        telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN)
        telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", TELEGRAM_CHAT_ID)

        if not telegram_token or not telegram_chat_id:
            logger.debug("Sentinel: Telegram not configured, skipping notification")
            return False

        self._purge_old_telegram_fingerprints()
        fingerprint = self._build_telegram_fingerprint(
            text[:4096],
            parse_mode=parse_mode,
            dedup_key=dedup_key,
        )
        last_sent = self._telegram_message_fingerprints.get(fingerprint, 0.0)
        if TELEGRAM_DEDUP_SECONDS > 0 and (time.time() - last_sent) <= TELEGRAM_DEDUP_SECONDS:
            logger.info("Sentinel: duplicate Telegram message skipped")
            return True

        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                payload = {
                    "chat_id": telegram_chat_id,
                    "text": text[:4096],
                }
                if parse_mode:
                    payload["parse_mode"] = parse_mode
                resp = await client.post(
                    f"https://api.telegram.org/bot{telegram_token}/sendMessage",
                    json=payload,
                )
                if resp.status_code == 200:
                    self._telegram_message_fingerprints[fingerprint] = time.time()
                    logger.info("Sentinel: Telegram notification sent ✉️")
                    return True
                else:
                    logger.warning(f"Sentinel: Telegram error {resp.status_code}")
                    return False
        except Exception as e:
            logger.error(f"Sentinel: Telegram send failed: {e}")
            return False

    # ═══════════════════════════════════════════════════════════
    #  Initiative Log
    # ═══════════════════════════════════════════════════════════

    def _log_initiative(self, key: str, initiative_type: str, data: Dict[str, Any]) -> None:
        """Records a completed initiative."""
        entry = {
            "key": key,
            "type": initiative_type,
            "data": data,
            "timestamp": time.time(),
            "datetime": datetime.now().isoformat(),
        }
        self._initiatives.append(entry)
        # Keep last 200 entries
        if len(self._initiatives) > 200:
            self._initiatives = self._initiatives[-200:]
        self._save_initiatives()

    def _was_initiative_done_today(self, key: str) -> bool:
        """Checks if an initiative with this key was already logged today."""
        today = datetime.now().strftime("%Y-%m-%d")  # Matches ISO format in stored datetime
        return any(
            i.get("key") == key and today in i.get("datetime", "")
            for i in self._initiatives
        )

    def _load_initiatives(self) -> None:
        try:
            if INITIATIVES_LOG.exists():
                with open(INITIATIVES_LOG, encoding="utf-8") as f:
                    self._initiatives = json.load(f)
        except Exception:
            self._initiatives = []

    def _save_initiatives(self) -> None:
        try:
            with open(INITIATIVES_LOG, "w", encoding="utf-8") as f:
                json.dump(self._initiatives, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Sentinel: failed to save initiatives: {e}")

    # ═══════════════════════════════════════════════════════════
    #  Status
    # ═══════════════════════════════════════════════════════════

    def _get_status(self) -> Dict[str, Any]:
        now = time.time()
        recent_24h = [i for i in self._initiatives if now - i.get("timestamp", 0) < 86400]
        return {
            "agent": "MoonSentinelAgent",
            "status": "active",
            "last_tech_watch": datetime.fromtimestamp(self._last_tech_watch).isoformat()
                if self._last_tech_watch > 0 else "never",
            "last_health_watch": datetime.fromtimestamp(self._last_health_watch).isoformat()
                if self._last_health_watch > 0 else "never",
            "last_research_report_file": self._last_research_report_file,
            "last_implementation_report_file": self._last_implementation_report_file,
            "initiatives_last_24h": len(recent_24h),
            "total_initiatives": len(self._initiatives),
            "next_tech_watch_in_minutes": max(
                0,
                int((self._last_tech_watch + TECH_WATCH_INTERVAL_HOURS * 3600 - now) / 60)
            ) if self._last_tech_watch > 0 else 0,
        }
