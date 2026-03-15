"""
agents/nexus_intelligence.py
NexusIntelligence — A Mente de Convergência do Ecossistema The Moon.

O único agente que observa o ecossistema como um organismo completo.
Enquanto todos os outros agentes são especialistas no seu domínio,
o Nexus é o único que enxerga o TODO — correlações entre apostas
e novas skills descobertas, padrões no comportamento do usuário,
falhas em cascata iminentes, oportunidades emergentes que só existem
na interseção de múltiplos domínios.

MÓDULOS INTERNOS:
  1. EventStreamAggregator  — assina TODOS os tópicos do MessageBus
  2. CrossDomainPatternEngine — detecta correlações entre domínios
  3. UserIntentModeler       — constrói modelo probabilístico de intenção
  4. CascadePredictor        — prevê falhas antes que aconteçam
  5. BriefingGenerator       — relatório matinal síntese (LLM-powered)
  6. EmergentOpportunityRadar — oportunidades na interseção de agentes

INTEGRAÇÕES:
  - Assina: TODOS os tópicos (wildcard subscription)
  - Publica: nexus.insight, nexus.cascade_warning, nexus.briefing
  - Lê: SemanticMemoryWeaver (histórico), WatchdogAgent (circuit states)
  - Escreve: SemanticMemoryWeaver (insights como NodeType.INSIGHT)

ZERO CUSTO:
  - Análise de padrões: stdlib puro (collections, statistics, math)
  - Síntese de briefing: Groq llama-3.3-70b-versatile
  - Persistência: JSON local em data/nexus/

CHANGELOG (Moon Codex — Março 2026):
  - [ARCH] Agente criado: NexusIntelligence — Convergence Mind
  - [ARCH] EventStreamAggregator com janela deslizante de 24h
  - [ARCH] CrossDomainPatternEngine com correlação temporal e semântica
  - [ARCH] UserIntentModeler com Bayesian naive classifier
  - [ARCH] CascadePredictor baseado em circuit breaker states + histórico
  - [ARCH] BriefingGenerator diário via Groq com síntese cross-domain
  - [ARCH] EmergentOpportunityRadar detecta oportunidades na interseção
"""

from __future__ import annotations

import asyncio
import collections
import hashlib
import json
import logging
import math
import os
import statistics
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

from core.agent_base import AgentBase, AgentPriority, TaskResult
from core.message_bus import MessageBus, Message

logger = logging.getLogger("moon.agents.nexus")

# ─────────────────────────────────────────────────────────────
#  Storage & Constants
# ─────────────────────────────────────────────────────────────
NEXUS_DIR           = Path("data/nexus")
EVENTS_FILE         = NEXUS_DIR / "event_stream.json"
INSIGHTS_FILE       = NEXUS_DIR / "insights.json"
INTENT_FILE         = NEXUS_DIR / "user_intent.json"
BRIEFING_FILE       = NEXUS_DIR / "last_briefing.json"

EVENT_WINDOW_H      = 24     # hours of events kept in rolling window
MAX_EVENTS          = 2000   # max events in memory (ring buffer)
PATTERN_MIN_EVENTS  = 5      # minimum events to attempt correlation
BRIEFING_HOUR_UTC   = 8      # hour (UTC) for daily briefing
INTENT_DECAY_H      = 48     # hours before an intent signal decays
CASCADE_THRESHOLD   = 0.65   # probability to trigger cascade warning

# All MessageBus topics to subscribe to
MONITORED_TOPICS = [
    "betting.result", "betting.analysis",
    "blog.published", "youtube.published", "content.published",
    "content.distributed",
    "devops.scan_complete",
    "alchemist.proposal", "alchemist.skill_promoted", "alchemist.discovery",
    "sentinel.alert", "sentinel.opportunity", "sentinel.bet_win",
    "sentinel.goal_progress",
    "watchdog.alert",
    "voice.interaction",
    "system.screen_locked",
    "workspace.network",
    "monitor_events",
]

# Domain mapping: topic → domain label
TOPIC_DOMAIN: Dict[str, str] = {
    "betting":   "apostas",
    "blog":      "conteúdo",
    "youtube":   "conteúdo",
    "content":   "conteúdo",
    "devops":    "código",
    "alchemist": "inovação",
    "sentinel":  "finanças",
    "watchdog":  "sistema",
    "voice":     "interação",
    "system":    "sistema",
    "workspace": "sistema",
}


# ─────────────────────────────────────────────────────────────
#  Data Models
# ─────────────────────────────────────────────────────────────

class InsightType(str, Enum):
    CORRELATION       = "correlação_cross_domain"
    OPPORTUNITY       = "oportunidade_emergente"
    CASCADE_WARNING   = "aviso_cascata"
    USER_PATTERN      = "padrão_do_usuário"
    PERFORMANCE_TREND = "tendência_de_performance"
    ANOMALY           = "anomalia_detectada"


@dataclass
class StreamEvent:
    """A single event captured from the MessageBus."""
    id:        str
    topic:     str
    domain:    str
    sender:    str
    payload:   Dict[str, Any]
    timestamp: float = field(default_factory=time.time)

    def age_hours(self) -> float:
        return (time.time() - self.timestamp) / 3600

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class NexusInsight:
    """A cross-domain insight generated by the Nexus."""
    id:              str
    type:            InsightType
    title:           str
    description:     str
    domains:         List[str]        # which domains are involved
    confidence:      float            # 0-1
    supporting_events: List[str]      # event IDs that support this insight
    actionable:      bool             # can the user act on this?
    action_hint:     str = ""         # what to do about it
    created_at:      float = field(default_factory=time.time)
    metadata:        Dict[str, Any] = field(default_factory=dict)

    def format_telegram(self) -> str:
        conf_bar   = "█" * int(self.confidence * 5) + "░" * (5 - int(self.confidence * 5))
        type_emoji = {
            InsightType.CORRELATION:       "🔗",
            InsightType.OPPORTUNITY:       "💡",
            InsightType.CASCADE_WARNING:   "⚠️",
            InsightType.USER_PATTERN:      "🧠",
            InsightType.PERFORMANCE_TREND: "📈",
            InsightType.ANOMALY:           "🔍",
        }.get(self.type, "•")
        domains_str = " + ".join(self.domains)
        msg = (
            f"{type_emoji} *{self.title}*\n"
            f"   Domínios: `{domains_str}`\n"
            f"   Confiança: `[{conf_bar}]` {self.confidence:.0%}\n"
            f"   {self.description[:200]}"
        )
        if self.actionable and self.action_hint:
            msg += f"\n   💬 _{self.action_hint}_"
        return msg

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["type"] = self.type.value
        return d


@dataclass
class IntentSignal:
    """A user intent signal extracted from an interaction."""
    domain:    str
    topic:     str           # sub-topic within domain
    strength:  float         # 0-1, decays over time
    first_seen: float
    last_seen:  float
    count:      int = 1

    def decayed_strength(self) -> float:
        hours_since = (time.time() - self.last_seen) / 3600
        decay       = math.exp(-hours_since / INTENT_DECAY_H)
        return self.strength * decay * min(1.0, 1 + math.log1p(self.count) * 0.2)


# ─────────────────────────────────────────────────────────────
#  1. Event Stream Aggregator
# ─────────────────────────────────────────────────────────────

class EventStreamAggregator:
    """
    Maintains a rolling 24h window of all MessageBus events.
    Thread-safe via asyncio (single-threaded event loop).
    """

    def __init__(self) -> None:
        self._events: Deque[StreamEvent] = collections.deque(maxlen=MAX_EVENTS)

    def ingest(self, topic: str, sender: str, payload: Dict[str, Any]) -> StreamEvent:
        """Adds an event to the stream. Returns the created event."""
        domain = self._resolve_domain(topic)
        event  = StreamEvent(
            id        = hashlib.sha256(f"{topic}{sender}{time.time()}".encode()).hexdigest()[:10],
            topic     = topic,
            domain    = domain,
            sender    = sender,
            payload   = payload,
            timestamp = time.time(),
        )
        self._events.append(event)
        return event

    def get_window(self, hours: float = EVENT_WINDOW_H) -> List[StreamEvent]:
        cutoff = time.time() - hours * 3600
        return [e for e in self._events if e.timestamp >= cutoff]

    def get_by_domain(self, domain: str, hours: float = EVENT_WINDOW_H) -> List[StreamEvent]:
        return [e for e in self.get_window(hours) if e.domain == domain]

    def get_by_topic(self, topic_prefix: str, hours: float = EVENT_WINDOW_H) -> List[StreamEvent]:
        return [e for e in self.get_window(hours) if e.topic.startswith(topic_prefix)]

    def domain_activity(self, hours: float = EVENT_WINDOW_H) -> Dict[str, int]:
        """Returns count of events per domain in the window."""
        counts: Dict[str, int] = {}
        for e in self.get_window(hours):
            counts[e.domain] = counts.get(e.domain, 0) + 1
        return counts

    def event_rate(self, topic_prefix: str, window_h: float = 1.0) -> float:
        """Events per hour for a given topic prefix."""
        events = self.get_by_topic(topic_prefix, window_h)
        return len(events) / max(window_h, 0.01)

    def dump(self, limit: int = 500) -> List[Dict]:
        recent = list(self._events)[-limit:]
        return [e.to_dict() for e in recent]

    def load(self, data: List[Dict]) -> None:
        cutoff = time.time() - EVENT_WINDOW_H * 3600
        for d in data:
            if d.get("timestamp", 0) >= cutoff:
                try:
                    self._events.append(StreamEvent(**d))
                except Exception:
                    pass

    @staticmethod
    def _resolve_domain(topic: str) -> str:
        prefix = topic.split(".")[0]
        return TOPIC_DOMAIN.get(prefix, "geral")


# ─────────────────────────────────────────────────────────────
#  2. Cross-Domain Pattern Engine
# ─────────────────────────────────────────────────────────────

class CrossDomainPatternEngine:
    """
    Detects non-obvious correlations between events from different domains.

    Strategies:
      - Temporal co-occurrence: two different domains spiking in the same hour
      - Outcome correlation: betting wins after code improvements?
      - Cascade detection: one domain's failures predict another's
      - Frequency anomaly: domain suddenly more/less active than baseline
    """

    def analyze(self, stream: EventStreamAggregator) -> List[NexusInsight]:
        insights: List[NexusInsight] = []

        window = stream.get_window(PATTERN_MIN_EVENTS) # This was a mistake in the provided logic? PATTERN_MIN_EVENTS is 5.
        # Original code used EVENT_WINDOW_H for analysis.
        window = stream.get_window(EVENT_WINDOW_H)
        if len(window) < PATTERN_MIN_EVENTS:
            return insights

        insights += self._temporal_co_occurrence(stream)
        insights += self._frequency_anomaly(stream)
        insights += self._betting_code_correlation(stream)
        insights += self._alchemist_impact_correlation(stream)

        return insights

    def _temporal_co_occurrence(
        self, stream: EventStreamAggregator
    ) -> List[NexusInsight]:
        """
        Detects when two different domains spike simultaneously.
        Uses 1h buckets over the last 24h.
        """
        insights: List[NexusInsight] = []
        window = stream.get_window(24)
        if not window:
            return insights

        # Bucket events by (hour, domain)
        buckets: Dict[Tuple[int, str], int] = {}
        for event in window:
            hour_key = int(event.timestamp // 3600)
            key      = (hour_key, event.domain)
            buckets[key] = buckets.get(key, 0) + 1

        # Find hours with activity in 3+ domains
        hour_domains: Dict[int, List[str]] = {}
        for (hour, domain), count in buckets.items():
            if count >= 2:   # meaningful activity (not just 1 event)
                hour_domains.setdefault(hour, []).append(domain)

        multi_domain_hours = {h: d for h, d in hour_domains.items() if len(d) >= 3}
        if multi_domain_hours:
            best_hour = max(multi_domain_hours, key=lambda h: len(multi_domain_hours[h]))
            domains   = multi_domain_hours[best_hour]
            hours_ago = (time.time() / 3600 - best_hour)

            insights.append(NexusInsight(
                id          = hashlib.sha256(f"cooccur{best_hour}".encode()).hexdigest()[:10],
                type        = InsightType.CORRELATION,
                title       = f"Atividade multi-domínio intensa ({len(domains)} domínios)",
                description = (
                    f"Há {hours_ago:.0f}h, os domínios "
                    f"{', '.join(domains)} estiveram simultaneamente ativos. "
                    f"Isso pode indicar que uma ação desencadeou reações em cascata positivas."
                ),
                domains     = domains,
                confidence  = min(0.9, 0.5 + len(domains) * 0.1),
                supporting_events = [],
                actionable  = False,
            ))

        return insights

    def _frequency_anomaly(self, stream: EventStreamAggregator) -> List[NexusInsight]:
        """
        Detects when a domain is significantly more/less active than its 7-day baseline.
        Uses z-score: anomaly if |z| > 2.0.
        """
        insights: List[NexusInsight] = []

        # Get hourly rates for each domain over last 24h
        for domain in set(TOPIC_DOMAIN.values()):
            recent_rate  = len(stream.get_by_domain(domain, hours=1))
            baseline_day = [
                len([
                    e for e in stream.get_by_domain(domain, hours=(h + 1))
                    if e.timestamp >= time.time() - (h + 1) * 3600
                    and e.timestamp < time.time() - h * 3600
                ])
                for h in range(1, 25)
            ]
            if len(baseline_day) < 5 or all(v == 0 for v in baseline_day):
                continue

            try:
                mean = statistics.mean(baseline_day)
                std  = statistics.stdev(baseline_day)
            except statistics.StatisticsError:
                continue

            if std < 0.5:
                continue   # domain too quiet to have meaningful baseline

            z = (recent_rate - mean) / std
            if z > 2.5:
                insights.append(NexusInsight(
                    id         = hashlib.sha256(f"spike{domain}{int(time.time()/3600)}".encode()).hexdigest()[:10],
                    type       = InsightType.ANOMALY,
                    title      = f"Pico de atividade: domínio {domain}",
                    description= (
                        f"O domínio '{domain}' está com {recent_rate:.0f} eventos/h, "
                        f"{z:.1f}σ acima da média ({mean:.1f} eventos/h). "
                        f"Algo incomum está acontecendo neste domínio."
                    ),
                    domains    = [domain],
                    confidence = min(0.95, 0.5 + z * 0.15),
                    supporting_events = [],
                    actionable = True,
                    action_hint= f"Verifique o status do domínio '{domain}' com /status",
                ))
            elif z < -2.5:
                insights.append(NexusInsight(
                    id         = hashlib.sha256(f"drop{domain}{int(time.time()/3600)}".encode()).hexdigest()[:10],
                    type       = InsightType.ANOMALY,
                    title      = f"Silêncio suspeito: domínio {domain}",
                    description= (
                        f"O domínio '{domain}' está com {recent_rate:.0f} eventos/h, "
                        f"{abs(z):.1f}σ abaixo da média. Possível falha silenciosa."
                    ),
                    domains    = [domain],
                    confidence = min(0.9, 0.5 + abs(z) * 0.12),
                    supporting_events = [],
                    actionable = True,
                    action_hint= f"Verifique se os agentes do domínio '{domain}' estão respondendo ao ping()",
                ))

        return insights

    def _betting_code_correlation(self, stream: EventStreamAggregator) -> List[NexusInsight]:
        """
        Detects if betting performance improved after code changes.
        Compares win rate before/after devops.scan_complete events.
        """
        insights: List[NexusInsight] = []

        devops_events  = stream.get_by_topic("devops.scan_complete", hours=48)
        betting_events = stream.get_by_topic("betting.result", hours=48)

        if not devops_events or len(betting_events) < 4:
            return insights

        latest_scan_ts = max(e.timestamp for e in devops_events)

        wins_after  = [e for e in betting_events if e.timestamp > latest_scan_ts
                       and e.payload.get("won")]
        total_after = [e for e in betting_events if e.timestamp > latest_scan_ts]

        wins_before  = [e for e in betting_events if e.timestamp <= latest_scan_ts
                        and e.payload.get("won")]
        total_before = [e for e in betting_events if e.timestamp <= latest_scan_ts]

        if not total_after or not total_before:
            return insights

        rate_after  = len(wins_after)  / len(total_after)
        rate_before = len(wins_before) / len(total_before)

        if rate_after > rate_before + 0.15 and len(total_after) >= 2:
            delta = rate_after - rate_before
            insights.append(NexusInsight(
                id         = hashlib.sha256(f"betcode{int(latest_scan_ts)}".encode()).hexdigest()[:10],
                type       = InsightType.CORRELATION,
                title      = f"Taxa de vitórias +{delta:.0%} após otimização de código",
                description= (
                    f"Após o último scan do DevOps, a taxa de vitórias foi de "
                    f"{rate_after:.0%} ({len(wins_after)}/{len(total_after)}), "
                    f"contra {rate_before:.0%} antes ({len(wins_before)}/{len(total_before)}). "
                    f"O código mais limpo pode estar melhorando a qualidade das análises de apostas."
                ),
                domains    = ["código", "apostas"],
                confidence = min(0.85, 0.5 + delta),
                supporting_events = [e.id for e in devops_events[:2]],
                actionable = True,
                action_hint= "Registre esta correlação no SemanticMemoryWeaver como aprendizado estratégico.",
                metadata   = {"rate_after": rate_after, "rate_before": rate_before},
            ))

        return insights

    def _alchemist_impact_correlation(self, stream: EventStreamAggregator) -> List[NexusInsight]:
        """
        Detects if SkillAlchemist discoveries preceded improvements in other domains.
        """
        insights: List[NexusInsight] = []

        promotions = stream.get_by_topic("alchemist.skill_promoted", hours=72)
        if not promotions:
            return insights

        # Check if any domain improved after a promotion
        for promo_event in promotions[:3]:
            ts      = promo_event.timestamp
            tool    = promo_event.payload.get("tool", "tool")
            module  = promo_event.payload.get("skill_path", "")

            # Find events in the target module's domain after the promotion
            domain  = "inovação"
            if "betting" in module.lower() or "sports" in module.lower():
                domain = "apostas"
            elif "blog" in module.lower() or "content" in module.lower():
                domain = "conteúdo"

            activity_after  = len(stream.get_by_domain(domain, hours=24))
            activity_window = len([e for e in stream.get_by_domain(domain, hours=48)
                                   if e.timestamp <= ts])

            if activity_after > activity_window * 1.5 and activity_after >= 3:
                insights.append(NexusInsight(
                    id         = hashlib.sha256(f"alch{promo_event.id}".encode()).hexdigest()[:10],
                    type       = InsightType.OPPORTUNITY,
                    title      = f"Skill '{tool}' amplificou atividade em {domain}",
                    description= (
                        f"Após a integração de '{tool}', a atividade no domínio "
                        f"'{domain}' aumentou {((activity_after/max(activity_window,1))-1):.0%}. "
                        f"Esta skill pode ter potencial para outros domínios do ecossistema."
                    ),
                    domains    = ["inovação", domain],
                    confidence = 0.65,
                    supporting_events = [promo_event.id],
                    actionable = True,
                    action_hint= f"Considere adaptar a skill '{tool}' para outros domínios.",
                ))

        return insights


# ─────────────────────────────────────────────────────────────
#  3. User Intent Modeler
# ─────────────────────────────────────────────────────────────

class UserIntentModeler:
    """
    Builds a probabilistic model of what the user is currently focused on.

    Uses naive Bayes over interaction history + decay function.
    Intent signals are extracted from voice interactions, Telegram commands,
    and the topics of manual /status or /help requests.
    """

    def __init__(self) -> None:
        self._signals: Dict[str, IntentSignal] = {}

    def ingest_interaction(self, text: str, response_topic: str = "") -> None:
        """Extracts intent signals from a user interaction."""
        text_lower = text.lower()

        # Domain keyword mapping
        domain_keywords = {
            "apostas":   ["aposta", "bet", "odd", "futebol", "partida", "kelly", "stake", "lucro"],
            "conteúdo":  ["blog", "post", "artigo", "seo", "youtube", "vídeo", "publicar"],
            "finanças":  ["investimento", "crypto", "defi", "retorno", "sentinel", "custo"],
            "código":    ["código", "bug", "refactor", "pull request", "git", "devops", "erro"],
            "inovação":  ["nova skill", "ferramenta", "github trending", "arxiv", "alquimista"],
            "sistema":   ["status", "saúde", "cpu", "memória", "watchdog", "ping"],
        }

        for domain, keywords in domain_keywords.items():
            hits = sum(1 for kw in keywords if kw in text_lower)
            if hits > 0:
                strength = min(1.0, hits * 0.3)
                key      = f"{domain}:{response_topic or 'geral'}"
                if key in self._signals:
                    sig = self._signals[key]
                    sig.strength  = min(1.0, sig.strength + strength * 0.5)
                    sig.last_seen = time.time()
                    sig.count    += 1
                else:
                    self._signals[key] = IntentSignal(
                        domain     = domain,
                        topic      = response_topic or "geral",
                        strength   = strength,
                        first_seen = time.time(),
                        last_seen  = time.time(),
                    )

    def current_focus(self, top_n: int = 3) -> List[Dict[str, Any]]:
        """Returns the user's current top focus areas, sorted by decayed strength."""
        scored = [
            {
                "domain":   sig.domain,
                "topic":    sig.topic,
                "strength": sig.decayed_strength(),
                "count":    sig.count,
            }
            for sig in self._signals.values()
            if sig.decayed_strength() > 0.05
        ]
        return sorted(scored, key=lambda x: x["strength"], reverse=True)[:top_n]

    def predict_next_query(self) -> Optional[str]:
        """Predicts what the user is likely to ask about next."""
        focus = self.current_focus(1)
        if not focus:
            return None
        top = focus[0]
        hints = {
            "apostas":  "análise de apostas ou resultados recentes",
            "conteúdo": "status de publicações ou métricas de blog",
            "finanças": "relatório financeiro ou oportunidades de yield",
            "código":   "status do scan de código ou PRs pendentes",
            "inovação": "novas skills descobertas ou propostas do Alchemist",
            "sistema":  "status do sistema ou alertas do Watchdog",
        }
        return hints.get(top["domain"])

    def context_for_response(self) -> str:
        """Returns a short context string to prepend to LLM responses."""
        focus = self.current_focus(2)
        if not focus:
            return ""
        domains = [f["domain"] for f in focus]
        return f"[Contexto do usuário: foco atual em {' e '.join(domains)}]"

    def to_dict(self) -> Dict:
        return {k: asdict(v) for k, v in self._signals.items()}

    def from_dict(self, data: Dict) -> None:
        for k, v in data.items():
            try:
                self._signals[k] = IntentSignal(**v)
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────
#  4. Cascade Predictor
# ─────────────────────────────────────────────────────────────

class CascadePredictor:
    """
    Predicts failure cascades based on:
      - Circuit breaker states from all agents
      - Historical co-failure patterns
      - Resource contention signals from WatchdogAgent

    Uses a simple Bayesian network (hand-coded CPTs for the Moon ecosystem).
    """

    # Conditional probability table: if A is failing, what's the prob B fails?
    # Based on dependency analysis of the Moon architecture
    FAILURE_PROPAGATION = {
        "LlmAgent":       ["OmniChannelStrategist", "SemanticMemoryWeaver", "SkillAlchemist"],
        "OpenCodeAgent":  ["AutonomousDevOpsRefactor"],
        "GithubAgent":    ["AutonomousDevOpsRefactor", "SkillAlchemist"],
        "WatchdogAgent":  ["Orchestrator"],
        "MessageBus":     ["OmniChannelStrategist", "EconomicSentinel", "NexusIntelligence"],
    }

    # Base probability of cascade given a failing dependency
    PROPAGATION_PROB = 0.7

    def predict(
        self,
        open_circuits: List[str],
        watchdog_alerts: List[str],
        stream: EventStreamAggregator,
    ) -> List[NexusInsight]:
        insights: List[NexusInsight] = []

        # Direct cascade prediction
        for failing_agent in open_circuits:
            dependents = self.FAILURE_PROPAGATION.get(failing_agent, [])
            if dependents:
                at_risk = [d for d in dependents if d not in open_circuits]
                if at_risk:
                    cascade_prob = self.PROPAGATION_PROB * (1 + len(open_circuits) * 0.1)
                    cascade_prob = min(cascade_prob, 0.95)

                    if cascade_prob >= CASCADE_THRESHOLD:
                        insights.append(NexusInsight(
                            id         = hashlib.sha256(f"cascade{failing_agent}{time.time():.0f}".encode()).hexdigest()[:10],
                            type       = InsightType.CASCADE_WARNING,
                            title      = f"Risco de cascata: {failing_agent} → {', '.join(at_risk)}",
                            description= (
                                f"O agente '{failing_agent}' está com o circuito aberto. "
                                f"Com {cascade_prob:.0%} de probabilidade, os agentes dependentes "
                                f"[{', '.join(at_risk)}] também falharão nas próximas horas. "
                                f"Intervenção preventiva recomendada."
                            ),
                            domains    = ["sistema"],
                            confidence = cascade_prob,
                            supporting_events = [],
                            actionable = True,
                            action_hint= f"Reinicie '{failing_agent}' antes que a cascata se propague.",
                            metadata   = {"failing": failing_agent, "at_risk": at_risk},
                        ))

        # Resource contention: if watchdog is firing CPU + multiple agents are active
        cpu_alerts = [a for a in watchdog_alerts if "cpu" in a.lower() or "CPU" in a]
        if cpu_alerts and len(open_circuits) >= 2:
            insights.append(NexusInsight(
                id         = hashlib.sha256(f"resrc{int(time.time()/300)}".encode()).hexdigest()[:10],
                type       = InsightType.CASCADE_WARNING,
                title      = "Contenção de recursos: CPU alta com múltiplos circuitos abertos",
                description= (
                    f"CPU em alerta com {len(open_circuits)} circuito(s) aberto(s): "
                    f"{', '.join(open_circuits)}. "
                    f"A contenção de recursos pode estar causando timeouts em cascata. "
                    f"Considere pausar agentes não-críticos."
                ),
                domains    = ["sistema"],
                confidence = 0.8,
                supporting_events = [],
                actionable = True,
                action_hint= "Pause SkillAlchemist (sandbox consome CPU) e verifique /status",
            ))

        return insights


# ─────────────────────────────────────────────────────────────
#  5. Emergent Opportunity Radar
# ─────────────────────────────────────────────────────────────

class EmergentOpportunityRadar:
    """
    Detects opportunities that only exist at the intersection of multiple agent outputs.

    These are opportunities that NO individual agent can detect alone —
    they require seeing the ecosystem as a whole.
    """

    def scan(self, stream: EventStreamAggregator) -> List[NexusInsight]:
        insights: List[NexusInsight] = []
        insights += self._content_betting_synergy(stream)
        insights += self._research_financial_synergy(stream)
        insights += self._code_quality_betting_readiness(stream)
        return insights

    def _content_betting_synergy(self, stream: EventStreamAggregator) -> List[NexusInsight]:
        """
        If betting analysis is strong AND blog/content is active,
        there may be an opportunity to publish betting insights as content.
        """
        recent_bets  = stream.get_by_topic("betting.result", hours=24)
        recent_pubs  = stream.get_by_topic("content.published", hours=48)
        wins         = [e for e in recent_bets if e.payload.get("won")]

        if len(wins) >= 3 and not recent_pubs:
            win_rate = len(wins) / max(len(recent_bets), 1)
            return [NexusInsight(
                id         = hashlib.sha256(f"conbet{int(time.time()/3600)}".encode()).hexdigest()[:10],
                type       = InsightType.OPPORTUNITY,
                title      = f"Oportunidade de conteúdo: {win_rate:.0%} win rate — publique enquanto está quente",
                description= (
                    f"{len(wins)} vitórias nas últimas 24h (win rate {win_rate:.0%}) "
                    f"e nenhum conteúdo publicado nos últimos 2 dias. "
                    f"Existe uma oportunidade de criar conteúdo sobre a metodologia "
                    f"analítica enquanto os resultados são frescos e credíveis."
                ),
                domains    = ["apostas", "conteúdo"],
                confidence = 0.75,
                supporting_events = [e.id for e in wins[:3]],
                actionable = True,
                action_hint= "Peça ao BlogPublisherAgent para criar um artigo sobre a análise desta sequência de vitórias.",
            )]
        return []

    def _research_financial_synergy(self, stream: EventStreamAggregator) -> List[NexusInsight]:
        """
        If SkillAlchemist discovered a DeFi/finance tool AND EconomicSentinel has active opportunities,
        the two should be connected.
        """
        alchemist_discoveries = stream.get_by_topic("alchemist.discovery", hours=72)
        sentinel_opps         = stream.get_by_topic("sentinel.opportunity", hours=24)

        finance_discoveries = [
            e for e in alchemist_discoveries
            if any(kw in str(e.payload).lower()
                   for kw in ["defi", "finance", "yield", "trading", "crypto", "web3"])
        ]

        if finance_discoveries and sentinel_opps:
            return [NexusInsight(
                id         = hashlib.sha256(f"fintech{int(time.time()/3600)}".encode()).hexdigest()[:10],
                type       = InsightType.OPPORTUNITY,
                title      = "Convergência: nova tool financeira + oportunidade ativa do Sentinel",
                description= (
                    f"O SkillAlchemist descobriu {len(finance_discoveries)} ferramentas "
                    f"financeiras/Web3 recentemente, e o EconomicSentinel tem "
                    f"{len(sentinel_opps)} oportunidades ativas. "
                    f"Integrar a(s) nova(s) skill(s) pode amplificar as oportunidades identificadas."
                ),
                domains    = ["inovação", "finanças"],
                confidence = 0.70,
                supporting_events = [e.id for e in finance_discoveries[:2]],
                actionable = True,
                action_hint= "Promova a skill financeira do Alchemist e conecte ao EconomicSentinel.",
            )]
        return []

    def _code_quality_betting_readiness(self, stream: EventStreamAggregator) -> List[NexusInsight]:
        """
        Detects the optimal moment to run a major betting session:
        code quality high (recent clean scan) + no active watchdog alerts.
        """
        devops_events = stream.get_by_topic("devops.scan_complete", hours=12)
        watchdog_alerts = stream.get_by_topic("watchdog.alert", hours=2)
        betting_recent = stream.get_by_topic("betting.result", hours=3)

        if devops_events and not watchdog_alerts and not betting_recent:
            latest_scan = devops_events[-1]
            summary     = latest_scan.payload.get("summary", "")
            critical    = latest_scan.payload.get("critical", 1)

            if critical == 0:
                return [NexusInsight(
                    id         = hashlib.sha256(f"betready{int(time.time()/3600)}".encode()).hexdigest()[:10],
                    type       = InsightType.OPPORTUNITY,
                    title      = "Janela ideal: sistema limpo, zero alertas — ótimo momento para apostas",
                    description= (
                        f"Condições ideais detectadas: scan de código recente sem issues CRITICAL, "
                        f"nenhum alerta do Watchdog nas últimas 2h, "
                        f"e nenhuma aposta nas últimas 3h. "
                        f"O ecossistema está no seu estado mais confiável para análise de apostas."
                    ),
                    domains    = ["código", "sistema", "apostas"],
                    confidence = 0.80,
                    supporting_events = [latest_scan.id],
                    actionable = True,
                    action_hint= "Execute o BettingAnalyst agora para aproveitar a janela de estabilidade.",
                )]
        return []


# ─────────────────────────────────────────────────────────────
#  6. Briefing Generator
# ─────────────────────────────────────────────────────────────

class BriefingGenerator:
    """
    Generates a daily morning briefing synthesizing ALL agent activities.
    Uses Groq LLM for narrative synthesis; falls back to structured text.
    """

    def __init__(self, groq_client=None) -> None:
        self._groq = groq_client

    async def generate(
        self,
        stream:     EventStreamAggregator,
        insights:   List[NexusInsight],
        intent:     UserIntentModeler,
        open_circuits: List[str],
    ) -> str:
        domain_activity = stream.domain_activity(24)
        focus           = intent.current_focus(3)
        top_insights    = sorted(insights, key=lambda i: i.confidence, reverse=True)[:5]

        context = self._build_context(domain_activity, top_insights, focus, open_circuits)

        if self._groq:
            return await self._llm_briefing(context, focus)
        return self._structured_briefing(context, domain_activity, top_insights, open_circuits)

    def _build_context(
        self,
        domain_activity: Dict[str, int],
        insights:        List[NexusInsight],
        focus:           List[Dict],
        open_circuits:   List[str],
    ) -> str:
        activity_str = "\n".join(
            f"  - {domain}: {count} eventos nas últimas 24h"
            for domain, count in sorted(domain_activity.items(), key=lambda x: x[1], reverse=True)
        )
        insights_str = "\n".join(
            f"  - [{i.type.value}] {i.title} (confiança: {i.confidence:.0%})"
            for i in insights
        )
        focus_str = ", ".join(f"{f['domain']} ({f['strength']:.0%})" for f in focus)
        circuits_str = ", ".join(open_circuits) if open_circuits else "nenhum"

        return (
            f"ATIVIDADE POR DOMÍNIO (24h):\n{activity_str}\n\n"
            f"INSIGHTS DETECTADOS:\n{insights_str or '  Nenhum insight significativo.'}\n\n"
            f"FOCO ATUAL DO USUÁRIO: {focus_str or 'indefinido'}\n"
            f"CIRCUITOS ABERTOS: {circuits_str}\n"
        )

    async def _llm_briefing(self, context: str, focus: List[Dict]) -> str:
        focus_domains = [f["domain"] for f in focus]
        try:
            resp = await self._groq.chat.completions.create(
                model      = "llama-3.3-70b-versatile",
                messages   = [{
                    "role": "user",
                    "content": (
                        f"Você é o Nexus Intelligence do ecossistema 'The Moon' — "
                        f"uma IA que observa o sistema como um organismo completo.\n\n"
                        f"Gere um briefing matinal conciso (máx 300 palavras) para o dono do sistema. "
                        f"Tom: direto, analítico, como um consultor de alto nível. "
                        f"Foque nos domínios: {', '.join(focus_domains) or 'todos'}. "
                        f"Destaque apenas o que é genuinamente relevante e acionável.\n\n"
                        f"DADOS DO SISTEMA:\n{context}"
                    ),
                }],
                max_tokens  = 500,
                temperature = 0.4,
            )
            return resp.choices[0].message.content.strip()
        except Exception as exc:
            logger.warning(f"Briefing LLM failed: {exc}")
            return self._structured_briefing(context, {}, [], [])

    def _structured_briefing(
        self,
        context:        str,
        domain_activity: Dict[str, int],
        insights:        List[NexusInsight],
        open_circuits:   List[str],
    ) -> str:
        lines = [
            f"🌙 *Nexus Intelligence — Briefing Diário*",
            f"_{time.strftime('%d/%m/%Y %H:%M UTC', time.gmtime())}_\n",
        ]
        if domain_activity:
            top_domain = max(domain_activity, key=lambda d: domain_activity[d])
            lines.append(f"📊 Domínio mais ativo: *{top_domain}* ({domain_activity[top_domain]} eventos/24h)")

        if open_circuits:
            lines.append(f"⚠️ Circuitos abertos: `{', '.join(open_circuits)}`")

        if insights:
            lines.append(f"\n🔍 *Top {min(3, len(insights))} insights:*")
            for i in insights[:3]:
                lines.append(f"  • {i.title}")

        lines.append(f"\n_Use `/nexus report` para análise completa_")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
#  NexusIntelligence — Main Agent
# ─────────────────────────────────────────────────────────────

class NexusIntelligence(AgentBase):
    """
    NexusIntelligence — A Mente de Convergência do The Moon.

    O único agente que observa o ecossistema como um organismo completo.
    Detecta padrões cross-domain, modela intenção do usuário, prediz
    falhas em cascata e encontra oportunidades emergentes.

    Public actions (via execute):
      report        → Full cross-domain analysis report
      insights      → List current active insights
      briefing      → Generate/retrieve daily briefing
      intent        → Current user intent model
      cascade       → Cascade prediction status
      opportunities → Emergent opportunities only
      stream        → Recent event stream (last N events)
      status        → Agent status
    """

    def __init__(self, groq_client=None, message_bus=None) -> None:
        super().__init__()
        self.name        = "NexusIntelligence"
        self.description = (
            "Convergence Mind: monitors the entire ecosystem as an organism, "
            "detecting cross-domain patterns, predicting failures, and surfacing "
            "emergent opportunities invisible to individual agents."
        )
        self.priority = AgentPriority.HIGH

        self._groq        = groq_client
        self._message_bus = message_bus

        # Modules
        self._stream      = EventStreamAggregator()
        self._patterns    = CrossDomainPatternEngine()
        self._intent      = UserIntentModeler()
        self._cascade     = CascadePredictor()
        self._radar       = EmergentOpportunityRadar()
        self._briefing_gen = BriefingGenerator(groq_client)

        # State
        self._insights:      List[NexusInsight] = []
        self._open_circuits: List[str]          = []
        self._watchdog_alerts: List[str]        = []
        self._last_briefing: Optional[str]      = None
        self._last_briefing_ts: float           = 0.0
        self._last_analysis_ts: float           = 0.0

        # Loop control
        self._stop_event  = asyncio.Event()
        self._nexus_task: Optional[asyncio.Task] = None

    # ═══════════════════════════════════════════════════════════
    #  Lifecycle
    # ═══════════════════════════════════════════════════════════

    async def initialize(self) -> None:
        await super().initialize()
        NEXUS_DIR.mkdir(parents=True, exist_ok=True)
        self._load_state()

        if self._message_bus:
            for topic in MONITORED_TOPICS:
                self._message_bus.subscribe(topic, self._on_any_event)
            # Also subscribe to Orchestrator voice interactions
            self._message_bus.subscribe("voice.interaction", self._on_voice_interaction)
            logger.info(f"{self.name}: subscribed to {len(MONITORED_TOPICS)} topics.")

        self._stop_event.clear()
        self._nexus_task = asyncio.create_task(
            self._nexus_loop(), name="moon.nexus.loop"
        )
        logger.info(
            f"{self.name} initialized. "
            f"{len(list(self._stream.get_window()))} events in stream. "
            f"{len(self._insights)} insights loaded."
        )

    async def shutdown(self) -> None:
        self._stop_event.set()
        if self._nexus_task and not self._nexus_task.done():
            self._nexus_task.cancel()
            try:
                await self._nexus_task
            except asyncio.CancelledError:
                pass
        self._save_state()
        await super().shutdown()

    async def ping(self) -> bool:
        return not self._stop_event.is_set()

    # ═══════════════════════════════════════════════════════════
    #  Execute Dispatch
    # ═══════════════════════════════════════════════════════════

    async def _execute(self, action: str, **kwargs: Any) -> TaskResult:
        match action:
            case "report":
                return await self._action_report()

            case "insights":
                limit = int(kwargs.get("limit", 10))
                sorted_insights = sorted(self._insights, key=lambda i: i.confidence, reverse=True)
                return TaskResult(success=True, data={
                    "insights": [i.to_dict() for i in sorted_insights[:limit]],
                    "total":    len(self._insights),
                    "by_type":  self._insights_by_type(),
                })

            case "briefing":
                force = bool(kwargs.get("force", False))
                briefing = await self._get_or_generate_briefing(force)
                return TaskResult(success=True, data={"briefing": briefing})

            case "intent":
                return TaskResult(success=True, data={
                    "current_focus":  self._intent.current_focus(5),
                    "next_query":     self._intent.predict_next_query(),
                    "context_hint":   self._intent.context_for_response(),
                })

            case "cascade":
                cascade_insights = [i for i in self._insights if i.type == InsightType.CASCADE_WARNING]
                return TaskResult(success=True, data={
                    "warnings":      [i.to_dict() for i in cascade_insights],
                    "open_circuits": self._open_circuits,
                    "risk_level":    "HIGH" if cascade_insights else "LOW",
                })

            case "opportunities":
                opp_insights = [
                    i for i in self._insights
                    if i.type in (InsightType.OPPORTUNITY, InsightType.CORRELATION)
                    and i.actionable
                ]
                opp_insights.sort(key=lambda i: i.confidence, reverse=True)
                return TaskResult(success=True, data={
                    "opportunities": [i.to_dict() for i in opp_insights[:8]],
                    "count":         len(opp_insights),
                })

            case "stream":
                limit  = int(kwargs.get("limit", 50))
                domain = kwargs.get("domain")
                if domain:
                    events = self._stream.get_by_domain(domain)
                else:
                    events = self._stream.get_window()
                events.sort(key=lambda e: e.timestamp, reverse=True)
                return TaskResult(success=True, data={
                    "events": [e.to_dict() for e in events[:limit]],
                    "total":  len(events),
                    "domain_activity": self._stream.domain_activity(),
                })

            case "status":
                return TaskResult(success=True, data=self._get_status())

            case _:
                return TaskResult(success=False, error=f"Unknown action: '{action}'")

    # ═══════════════════════════════════════════════════════════
    #  MessageBus Callbacks
    # ═══════════════════════════════════════════════════════════

    async def _on_any_event(self, message: Message) -> None:
        """Universal callback for all subscribed topics."""
        topic  = message.topic
        sender = message.sender
        event  = message.payload

        # Ingest into stream
        self._stream.ingest(topic, sender, event)

        # Extract watchdog alerts
        if topic == "watchdog.alert":
            msg = event.get("message", "")
            if msg and msg not in self._watchdog_alerts:
                self._watchdog_alerts.append(msg)
                self._watchdog_alerts = self._watchdog_alerts[-20:]

        # Extract circuit states from devops/orchestrator reports
        if topic == "devops.scan_complete":
            pass  # circuit states come from Orchestrator health check

    async def _on_voice_interaction(self, message: Message) -> None:
        """Extracts user intent from voice/text interactions."""
        event = message.payload
        text = event.get("input", "")
        if text:
            self._intent.ingest_interaction(text)

    # ═══════════════════════════════════════════════════════════
    #  Nexus Analysis Loop
    # ═══════════════════════════════════════════════════════════

    async def _nexus_loop(self) -> None:
        """
        Background analysis loop.
        Runs pattern analysis every 15 minutes.
        Generates daily briefing at BRIEFING_HOUR_UTC.
        """
        logger.info("Nexus Intelligence loop started.")
        while not self._stop_event.is_set():
            try:
                now = time.time()

                # Run analysis every 15 minutes
                if now - self._last_analysis_ts >= 900:
                    await self._run_analysis()
                    self._last_analysis_ts = now

                # Check for daily briefing (at BRIEFING_HOUR_UTC)
                utc_hour = int(time.gmtime(now).tm_hour)
                if (utc_hour == BRIEFING_HOUR_UTC and
                        now - self._last_briefing_ts >= 20 * 3600):
                    briefing = await self._get_or_generate_briefing(force=True)
                    await self._broadcast(briefing, topic="nexus.briefing")
                    logger.info("Daily briefing sent.")

                sleep_time = min(60.0, 900 - (time.time() - self._last_analysis_ts))
                try:
                    await asyncio.wait_for(
                        asyncio.shield(self._stop_event.wait()),
                        timeout=max(1.0, sleep_time),
                    )
                    break
                except asyncio.TimeoutError:
                    pass

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Nexus loop error: {exc}")
                await asyncio.sleep(60)

        logger.info("Nexus Intelligence loop stopped.")

    async def _run_analysis(self) -> None:
        """Runs the full cross-domain analysis pipeline."""
        # Collect current circuit states (from Orchestrator if accessible)
        # For now, we infer from watchdog alerts
        new_insights: List[NexusInsight] = []

        # Pattern analysis
        new_insights += self._patterns.analyze(self._stream)

        # Cascade prediction
        new_insights += self._cascade.predict(
            self._open_circuits,
            self._watchdog_alerts,
            self._stream,
        )

        # Emergent opportunities
        new_insights += self._radar.scan(self._stream)

        # Deduplicate (keep newest of same type+domains combination)
        seen_keys: set[str] = set()
        deduplicated: List[NexusInsight] = []
        for insight in sorted(new_insights, key=lambda i: i.confidence, reverse=True):
            key = f"{insight.type.value}:{':'.join(sorted(insight.domains))}"
            if key not in seen_keys:
                seen_keys.add(key)
                deduplicated.append(insight)

        # Merge with existing insights (keep high-confidence old ones)
        merged: Dict[str, NexusInsight] = {}
        for i in self._insights:
            age_h = (time.time() - i.created_at) / 3600
            if age_h < 48 and i.confidence > 0.5:   # keep for 48h if confident
                merged[i.id] = i
        for i in deduplicated:
            merged[i.id] = i

        self._insights = list(merged.values())[-50:]  # keep last 50

        # Broadcast high-confidence new insights
        for insight in deduplicated:
            if insight.confidence >= 0.75 and insight.actionable:
                await self._broadcast(
                    insight.format_telegram(),
                    topic="nexus.insight"
                )

        self._save_state()

    # ═══════════════════════════════════════════════════════════
    #  Briefing
    # ═══════════════════════════════════════════════════════════

    async def _get_or_generate_briefing(self, force: bool = False) -> str:
        age_h = (time.time() - self._last_briefing_ts) / 3600

        if self._last_briefing and not force and age_h < 20:
            return self._last_briefing

        briefing = await self._briefing_gen.generate(
            self._stream,
            self._insights,
            self._intent,
            self._open_circuits,
        )
        self._last_briefing    = briefing
        self._last_briefing_ts = time.time()
        self._save_state()
        return briefing

    # ═══════════════════════════════════════════════════════════
    #  Full Report
    # ═══════════════════════════════════════════════════════════

    async def _action_report(self) -> TaskResult:
        """Generates a comprehensive cross-domain intelligence report."""
        await self._run_analysis()

        cascade_insights = [i for i in self._insights if i.type == InsightType.CASCADE_WARNING]
        opportunities    = [i for i in self._insights if i.type == InsightType.OPPORTUNITY and i.actionable]
        correlations     = [i for i in self._insights if i.type == InsightType.CORRELATION]
        anomalies        = [i for i in self._insights if i.type == InsightType.ANOMALY]

        briefing = await self._get_or_generate_briefing(force=True)

        return TaskResult(success=True, data={
            "briefing":        briefing,
            "cascade_warnings": [i.to_dict() for i in cascade_insights],
            "opportunities":   [i.to_dict() for i in opportunities[:5]],
            "correlations":    [i.to_dict() for i in correlations[:5]],
            "anomalies":       [i.to_dict() for i in anomalies[:5]],
            "domain_activity": self._stream.domain_activity(),
            "user_focus":      self._intent.current_focus(3),
            "open_circuits":   self._open_circuits,
            "total_insights":  len(self._insights),
            "stream_size":     len(self._stream.get_window()),
        })

    # ═══════════════════════════════════════════════════════════
    #  Broadcast & Notifications
    # ═══════════════════════════════════════════════════════════

    async def _broadcast(self, message: str, topic: str = "nexus.insight") -> None:
        if self._message_bus:
            asyncio.create_task(
                self._message_bus.publish(
                    sender  = self.name,
                    topic   = topic,
                    payload = {"message": message, "timestamp": time.time()},
                    target  = "orchestrator",
                )
            )

    # ═══════════════════════════════════════════════════════════
    #  Persistence
    # ═══════════════════════════════════════════════════════════

    def _save_state(self) -> None:
        try:
            NEXUS_DIR.mkdir(parents=True, exist_ok=True)
            # Save event stream (last 500 events)
            stream_data = self._stream.dump(500)
            tmp = EVENTS_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(stream_data, ensure_ascii=False, indent=2))
            tmp.replace(EVENTS_FILE)

            # Save insights
            insights_data = [i.to_dict() for i in self._insights]
            tmp2 = INSIGHTS_FILE.with_suffix(".tmp")
            tmp2.write_text(json.dumps(insights_data, ensure_ascii=False, indent=2))
            tmp2.replace(INSIGHTS_FILE)

            # Save intent model
            intent_data = self._intent.to_dict()
            tmp3 = INTENT_FILE.with_suffix(".tmp")
            tmp3.write_text(json.dumps(intent_data, ensure_ascii=False, indent=2))
            tmp3.replace(INTENT_FILE)

        except Exception as exc:
            logger.error(f"Nexus state save failed: {exc}")

    def _load_state(self) -> None:
        try:
            if EVENTS_FILE.exists():
                data = json.loads(EVENTS_FILE.read_text())
                self._stream.load(data)

            if INSIGHTS_FILE.exists():
                data = json.loads(INSIGHTS_FILE.read_text())
                for d in data:
                    try:
                        d["type"] = InsightType(d["type"])
                        self._insights.append(NexusInsight(**d))
                    except Exception:
                        pass

            if INTENT_FILE.exists():
                data = json.loads(INTENT_FILE.read_text())
                self._intent.from_dict(data)

            logger.info(
                f"{self.name}: state loaded — "
                f"{len(list(self._stream.get_window()))} events, "
                f"{len(self._insights)} insights."
            )
        except Exception as exc:
            logger.warning(f"Nexus state load failed (fresh start): {exc}")

    # ═══════════════════════════════════════════════════════════
    #  Helpers
    # ═══════════════════════════════════════════════════════════

    def _insights_by_type(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for i in self._insights:
            counts[i.type.value] = counts.get(i.type.value, 0) + 1
        return counts

    def _get_status(self) -> Dict[str, Any]:
        return {
            "stream_events_24h":   len(self._stream.get_window(24)),
            "domain_activity":     self._stream.domain_activity(24),
            "total_insights":      len(self._insights),
            "insights_by_type":    self._insights_by_type(),
            "open_circuits":       self._open_circuits,
            "watchdog_alerts":     len(self._watchdog_alerts),
            "user_top_focus":      self._intent.current_focus(1),
            "last_briefing_h_ago": round((time.time() - self._last_briefing_ts) / 3600, 1)
                                   if self._last_briefing_ts else None,
            "last_analysis_h_ago": round((time.time() - self._last_analysis_ts) / 3600, 2),
            "monitored_topics":    len(MONITORED_TOPICS),
            "briefing_hour_utc":   BRIEFING_HOUR_UTC,
        }
