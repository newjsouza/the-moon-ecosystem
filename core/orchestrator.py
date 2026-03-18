"""
core/orchestrator.py
Central orchestrator for The Moon ecosystem.
Unifies agents, skills, channels, and the autonomous loop.

CHANGELOG (Moon Codex — Março 2026):
  - [FIX CRÍTICO] Corrigido `await` ausente em message_bus.publish() no proactive loop
  - [FIX CRÍTICO] Strip de code fences reescrito com regex para suportar fences tipadas
  - [ARCH] Roteamento migrado para CommandRegistry — extensível sem tocar no core
  - [RESILIÊNCIA] AgentCircuitBreaker implementado por agente (máx 3 falhas antes de abrir)
  - [RESILIÊNCIA] Timeout configurável por chamada de agente via _call_agent()
  - [CONCORRÊNCIA] asyncio.Lock adicionado para _opencode_ready (race condition eliminada)
  - [OBSERVABILIDADE] Health check expandido para todos os agentes registrados
  - [UX] _format_help() gerado dinamicamente a partir do registry + skills registradas
  - [PROATIVO] Loop só faz broadcast quando há conteúdo relevante (sem spam)
  - [GRACEFUL DEGRADATION] Startup de agentes/canais com resultado granular por item
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional

from groq import AsyncGroq
from core.config import Config

from channels.base import ChannelBase
from core.agent_base import AgentBase, AgentPriority, TaskResult
from core.message_bus import MessageBus
from core.verification.graph import CodeVerificationGraph
from core.verification.state import VerificationState
from core.verification.graph import CodeVerificationGraph
from core.verification.state import VerificationState
from core.workspace.manager import WorkspaceManager
from skills.skill_base import SkillBase
from core.session_manager import get_session_manager  # Já existente
from core.moon_flow import get_flow_registry, MoonFlow  # Nova importação

logger = logging.getLogger("moon.core.orchestrator")

# ─────────────────────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────────────────────
AGENT_CALL_TIMEOUT = 30          # seconds before a single agent call is cancelled
CIRCUIT_BREAKER_THRESHOLD = 3    # consecutive failures before circuit opens
CIRCUIT_BREAKER_RESET = 120      # seconds until an open circuit tries to recover
PROACTIVE_INTERVAL = 60          # seconds between proactive cycles


# ─────────────────────────────────────────────────────────────
#  Circuit Breaker
# ─────────────────────────────────────────────────────────────

@dataclass
class _CircuitState:
    failures: int = 0
    opened_at: float = 0.0
    open: bool = False

    def record_success(self) -> None:
        self.failures = 0
        self.open = False

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= CIRCUIT_BREAKER_THRESHOLD:
            self.open = True
            self.opened_at = time.monotonic()
            logger.warning(f"Circuit OPENED after {self.failures} failures.")

    def is_callable(self) -> bool:
        if not self.open:
            return True
        if time.monotonic() - self.opened_at >= CIRCUIT_BREAKER_RESET:
            logger.info("Circuit attempting RESET (half-open).")
            self.open = False  # half-open: allow one probe
            return True
        return False


# ─────────────────────────────────────────────────────────────
#  Command Registry
# ─────────────────────────────────────────────────────────────

@dataclass
class _CommandEntry:
    """Metadata for a registered command."""
    handler: Callable[..., Coroutine]
    description: str
    usage: str
    category: str
    prefix_match: bool = False   # True = startswith, False = exact match


class CommandRegistry:
    """
    Declarative command routing table.
    Replaces the giant if/elif chain in _route_command.
    Register commands with @registry.command(...).
    """

    def __init__(self) -> None:
        self._exact: Dict[str, _CommandEntry] = {}
        self._prefix: List[tuple[str, _CommandEntry]] = []

    def command(
        self,
        trigger: str,
        *,
        description: str,
        usage: str,
        category: str = "Geral",
        prefix_match: bool = False,
    ) -> Callable:
        def decorator(fn: Callable) -> Callable:
            entry = _CommandEntry(fn, description, usage, category, prefix_match)
            if prefix_match:
                self._prefix.append((trigger.lower(), entry))
                self._prefix.sort(key=lambda x: len(x[0]), reverse=True)
            else:
                self._exact[trigger.lower()] = entry
            return fn
        return decorator

    def resolve(self, text: str) -> Optional[tuple[_CommandEntry, str]]:
        """
        Returns (entry, remainder_text) for the best matching command,
        or None if no command matches.
        """
        lower = text.strip().lower()

        if lower in self._exact:
            return self._exact[lower], text.strip()

        for prefix, entry in self._prefix:
            if lower.startswith(prefix):
                remainder = text.strip()[len(prefix):].strip()
                return entry, remainder

        return None

    def categories(self) -> Dict[str, List[_CommandEntry]]:
        """Groups all commands by category for help generation."""
        cats: Dict[str, List[_CommandEntry]] = {}
        for entry in list(self._exact.values()) + [e for _, e in self._prefix]:
            cats.setdefault(entry.category, []).append(entry)
        return cats


# ─────────────────────────────────────────────────────────────
#  Orchestrator
# ─────────────────────────────────────────────────────────────

class Orchestrator:
    """
    Central orchestrator for The Moon ecosystem.

    Responsibilities:
      - Agent & skill lifecycle (register / start / stop)
      - Channel message gateway with command routing
      - Proactive autonomous loop
      - Agent health monitoring with circuit breakers
      - Code verification via LangGraph
    """

    def __init__(self) -> None:
        self._agents: Dict[str, AgentBase] = {}
        self.skills: Dict[str, SkillBase] = {}
        self.channels: List[ChannelBase] = []

        self.verification_graph = CodeVerificationGraph()
        self.message_bus = MessageBus()
        self.workspace_manager = WorkspaceManager()

        self._autonomous_task: Optional[asyncio.Task] = None
        self._health_check_task: Optional[asyncio.Task] = None

        # ── Per-agent circuit breakers ───────────────────────────
        self._circuits: Dict[str, _CircuitState] = {}

        # ── Shared LLM Client (Groq) ─────────────────────────────
        config = Config()
        api_key = config.get("llm.api_key")
        if api_key and api_key != "COLE_O_SEU_TOKEN_AQUI":
            self.llm = AsyncGroq(api_key=api_key)
        else:
            self.llm = None
            logger.warning("GROQ_API_KEY not found or invalid. LLM features may be restricted.")

        # ── OpenCode availability (guarded by lock) ──────────────
        self._opencode_ready = False
        self._opencode_lock = asyncio.Lock()

        self.registry = CommandRegistry()
        self.message_bus.subscribe("devops.scan_complete", self._handle_devops_scan_complete)
        
        # ── Session Manager ──────────────────────────────────────
        self.session_manager = get_session_manager()
        
        # ── Flow Registry ────────────────────────────────────────
        self.flow_registry = get_flow_registry()
        self._load_default_flows()
        
        # ── Channel Gateway (Phase 5) ────────────────────────────
        from core.channel_gateway import get_channel_gateway
        self.channel_gateway = get_channel_gateway()
        
        # Register the telegram adapter
        from agents.telegram.bot import register_telegram_adapter
        register_telegram_adapter()
        
        # Initialize skill registry from Phase 3
        from core.skill_manifest import get_skill_registry
        self.skill_registry = get_skill_registry()
        self.skill_registry.discover("skills")
        
        logger.info("Orchestrator initialized with all systems")

    # ═══════════════════════════════════════════════════════════
    #  Registration
    # ═══════════════════════════════════════════════════════════

    def register_agent(self, agent: AgentBase) -> None:
        self._agents[agent.name] = agent
        self._circuits[agent.name] = _CircuitState()
        logger.info(f"Registered agent: {agent.name}")

    def get_agent(self, name: str) -> Optional[AgentBase]:
        return self._agents.get(name)

    def register_skill(self, skill: SkillBase) -> None:
        self.skills[skill.name] = skill
        logger.info(f"Registered skill: {skill.name}")

    def register_channel(self, channel: ChannelBase) -> None:
        channel.set_callback(self.handle_channel_message)
        self.channels.append(channel)
        logger.info(f"Registered channel: {channel.name}")

    # ═══════════════════════════════════════════════════════════
    #  Lifecycle
    # ═══════════════════════════════════════════════════════════

    async def start(self) -> None:
        """Starts all channels and the autonomous proactive loop."""
        logger.info("Starting Orchestrator services...")

        init_results = await asyncio.gather(
            *[self._safe_init_agent(a) for a in self._agents.values()],
            return_exceptions=True,
        )
        for name, result in zip(self._agents.keys(), init_results):
            if isinstance(result, Exception):
                logger.error(f"Agent '{name}' init failed — continuing: {result}")

        await self.workspace_manager.create_room("orchestrator", "Core System")
        for name in list(self._agents.keys()) + [s.name for s in self.skills.values()]:
            try:
                await self.workspace_manager.create_room(name, name)
            except Exception as exc:
                logger.warning(f"Workspace creation failed for '{name}': {exc}")

        channel_results = await asyncio.gather(
            *[ch.start() for ch in self.channels],
            return_exceptions=True,
        )
        for ch, result in zip(self.channels, channel_results):
            if isinstance(result, Exception):
                logger.error(f"Channel '{ch.name}' start failed: {result}")

        self._autonomous_task = asyncio.create_task(
            self._proactive_loop(), name="moon.proactive_loop"
        )
        self._health_check_task = asyncio.create_task(
            self._health_check_loop(), name="moon.health_check"
        )

        try:
            from core.services.workspace_monitor import start_monitor_service
            asyncio.create_task(
                start_monitor_service(self.message_bus, self.workspace_manager),
                name="moon.workspace_monitor",
            )
        except ImportError:
            logger.warning("workspace_monitor service not available — skipping.")

        logger.info("Orchestrator is ONLINE. All systems active.")

    async def stop(self) -> None:
        """Stops all background tasks, channels, and agents."""
        logger.info("Stopping Orchestrator services...")

        for task in (self._autonomous_task, self._health_check_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        await asyncio.gather(
            *[ch.stop() for ch in self.channels], return_exceptions=True
        )

        for agent in self._agents.values():
            try:
                await agent.shutdown()
            except Exception as exc:
                logger.error(f"Error shutting down agent '{agent.name}': {exc}")

        logger.info("Orchestrator stopped.")

    @staticmethod
    async def _safe_init_agent(agent: AgentBase) -> None:
        await agent.initialize()

    # ═══════════════════════════════════════════════════════════
    #  Agent call helpers (timeout + circuit breaker)
    # ═══════════════════════════════════════════════════════════

    async def _call_agent(
        self,
        agent_name: str,
        task: str,
        timeout: float = AGENT_CALL_TIMEOUT,
        **kwargs: Any,
    ) -> TaskResult:
        """
        Safe agent invocation with:
          - Existence check
          - Circuit breaker guard
          - Configurable timeout
          - Automatic circuit state update
        """
        agent = self._agents.get(agent_name)
        if agent is None:
            return TaskResult(success=False, error=f"Agent '{agent_name}' not registered.")

        circuit = self._circuits[agent_name]
        if not circuit.is_callable():
            return TaskResult(
                success=False,
                error=f"Agent '{agent_name}' circuit is OPEN — temporarily unavailable.",
            )

        await self.message_bus.publish(
            sender="orchestrator",
            topic="workspace.network",
            payload={"type": "agent_start", "task": task, "agent": agent_name},
            target=agent_name,
        )

        try:
            result: TaskResult = await asyncio.wait_for(
                agent.execute(task, **kwargs), timeout=timeout
            )
        except asyncio.TimeoutError:
            circuit.record_failure()
            msg = f"Agent '{agent_name}' timed out after {timeout}s."
            logger.warning(msg)
            return TaskResult(success=False, error=msg)
        except Exception as exc:
            circuit.record_failure()
            logger.error(f"Agent '{agent_name}' raised: {exc}")
            return TaskResult(success=False, error=str(exc))

        if result.success:
            circuit.record_success()
        else:
            circuit.record_failure()

        await self.message_bus.publish(
            sender=agent_name,
            topic="workspace.network",
            payload={"type": "agent_done", "success": result.success},
            target="orchestrator",
        )
        return result

    # ═══════════════════════════════════════════════════════════
    #  Command Registry — Built-in commands
    # ═══════════════════════════════════════════════════════════

    def _register_builtin_commands(self) -> None:
        """Registers all built-in slash commands into the CommandRegistry."""
        reg = self.registry

        @reg.command("/status", description="Status do sistema", usage="/status", category="Sistema")
        async def cmd_status(remainder: str, metadata: dict) -> str:
            return self._format_status()

        @reg.command("/help", description="Lista de comandos", usage="/help", category="Sistema")
        async def cmd_help(remainder: str, metadata: dict) -> str:
            return self._format_help()

        @reg.command("/project", description="Resumo do projeto", usage="/project", category="Sistema")
        async def cmd_project(remainder: str, metadata: dict) -> str:
            return await self._project_summary()

        @reg.command("/rooms", description="Status das salas de agentes", usage="/rooms", category="Sistema")
        async def cmd_rooms(remainder: str, metadata: dict) -> str:
            return self._format_rooms_status()

        @reg.command("/cmd ", description="Executar comando shell", usage="/cmd <comando>", category="Terminal", prefix_match=True)
        async def cmd_shell(remainder: str, metadata: dict) -> str:
            if not remainder:
                return "⚠️ Uso: `/cmd <comando>`"
            return await self._exec_shell(remainder)

        @reg.command("/git ", description="Operações Git", usage="/git <comando>", category="Terminal", prefix_match=True)
        async def cmd_git(remainder: str, metadata: dict) -> str:
            if not remainder:
                return "⚠️ Uso: `/git <comando>`"
            return await self._exec_shell(f"git {remainder}")

        @reg.command("/file ", description="Ler arquivo", usage="/file <caminho>", category="Arquivos", prefix_match=True)
        async def cmd_file(remainder: str, metadata: dict) -> str:
            if not remainder:
                return "⚠️ Uso: `/file <caminho>`"
            return await self._exec_file_read(remainder)

        @reg.command("/ls", description="Listar diretório", usage="/ls [caminho]", category="Arquivos", prefix_match=True)
        async def cmd_ls(remainder: str, metadata: dict) -> str:
            return await self._exec_file_action("ls", path=remainder or ".")

        @reg.command("/tree", description="Árvore do projeto", usage="/tree [caminho]", category="Arquivos", prefix_match=True)
        async def cmd_tree(remainder: str, metadata: dict) -> str:
            return await self._exec_file_action("tree", path=remainder or ".")

        @reg.command("/search ", description="Buscar no código", usage="/search <texto>", category="Arquivos", prefix_match=True)
        async def cmd_search(remainder: str, metadata: dict) -> str:
            if not remainder:
                return "⚠️ Uso: `/search <texto>`"
            return await self._exec_file_action("search", query=remainder)

        @reg.command("/edit ", description="Editar arquivo via LLM", usage="/edit <caminho> <instrução>", category="Arquivos", prefix_match=True)
        async def cmd_edit(remainder: str, metadata: dict) -> str:
            parts = remainder.split(" ", 1)
            if len(parts) < 2:
                return "⚠️ Uso: `/edit <caminho> <instrução>`"
            return await self._exec_edit(parts[0], parts[1])

        @reg.command("/skill ", description="Executar skill", usage="/skill <nome>", category="Skills", prefix_match=True)
        async def cmd_skill(remainder: str, metadata: dict) -> str:
            skill_name = remainder.lower()
            if skill_name in self.skills:
                result = await self.skills[skill_name].execute({"query": remainder})
                return f"✅ Skill `{skill_name}` executada:\n```\n{result}\n```"
            available = ", ".join(self.skills.keys()) or "nenhuma"
            return f"❌ Skill `{skill_name}` não encontrada.\nDisponíveis: {available}"

        @reg.command("/alchemist ", description="Controle do SkillAlchemist", usage="/alchemist [status|discover]", category="Alquimia", prefix_match=True)
        async def cmd_alchemist(remainder: str, metadata: dict) -> str:
            return await self._call_agent("SkillAlchemist", remainder)

        @reg.command("/nexus", description="Relatório de Inteligência Nexus", usage="/nexus [briefing]", category="Nexus", prefix_match=True)
        async def cmd_nexus(remainder: str, metadata: dict) -> str:
            return await self._call_agent("NexusIntelligence", remainder or "status")

    # ═══════════════════════════════════════════════════════════
    #  Message Gateway
    # ═══════════════════════════════════════════════════════════

    async def _normalize_channel_message(self, raw: dict) -> dict:
        """Converte mensagem de qualquer canal para formato interno Moon."""
        return {
            "text": raw.get("text", ""),
            "user_id": raw.get("user_id", "unknown"),
            "channel_type": raw.get("channel_type", "internal"),
            "channel_id": raw.get("channel_id", ""),
            "session_id": raw.get("session_id", ""),
        }


    async def handle_channel_message(self, text: str, metadata: Dict[str, Any]) -> None:
        source = metadata.get("source", "unknown")
        logger.info(f"Message from [{source}]: {text[:80]}...")

        await self.message_bus.publish(
            sender=source,
            topic="workspace.network",
            payload={"type": "user_message", "text": text},
            target="orchestrator",
        )

        metadata = await self._enrich_with_web_context(text, metadata)
        response = await self._route_command(text, metadata)

        for channel in self.channels:
            if channel.name == source:
                await channel.send_message(response, recipient_id=metadata.get("chat_id"))
                break


    async def _enrich_with_web_context(
        self, text: str, metadata: dict
    ) -> dict:
        """
        Pré-processador WebMCP: detecta queries que precisam de dados
        externos e injeta contexto em metadata["web_context"].
        Falha silenciosa — nunca bloqueia o fluxo principal.
        """
        try:
            from skills.webmcp.web_context import needs_web_data, fetch_web_context
            if needs_web_data(text):
                ctx = await fetch_web_context(text)
                if ctx:
                    metadata = {**metadata, "web_context": ctx}
        except Exception:
            pass
        return metadata


    async def _route_command(self, text: str, metadata: Dict[str, Any]) -> str:
        """Routes text to the CommandRegistry or falls back to LlmAgent."""
        match = self.registry.resolve(text)
        if match:
            entry, remainder = match
            try:
                return await entry.handler(remainder, metadata)
            except Exception as exc:
                logger.error(f"Command handler error for '{text[:40]}': {exc}")
                return f"⚠️ Erro interno ao processar comando: {exc}"

        result = await self._call_agent("LlmAgent", text)
        if result.success:
            response = result.data.get("response", "Processado sem resposta.")
            return response[:4000] + "\n\n…(truncado)" if len(response) > 4000 else response

        return f"🌙 Recebi: `{text}`\n\nUse `/help` para ver os comandos disponíveis.\n\n⚠️ LLM: {result.error}"

    # ═══════════════════════════════════════════════════════════
    #  Command Handlers
    # ═══════════════════════════════════════════════════════════

    async def _exec_shell(self, command: str) -> str:
        result = await self._call_agent("TerminalAgent", command, command=command)
        if result.success:
            output = result.data.get("output", "(sem output)")
            output = output[:3500] + "\n…(truncado)" if len(output) > 3500 else output
            return f"```\n$ {command}\n{output}\n```"
        return f"❌ {result.error}"

    async def _exec_file_read(self, path: str) -> str:
        result = await self._call_agent("FileManagerAgent", "read", action="read", path=path)
        if result.success:
            content = result.data.get("content", "")
            lines = result.data.get("lines", 0)
            fname = result.data.get("path", path).split("/")[-1]
            return f"📄 *{fname}* ({lines} linhas)\n\n```\n{content}\n```"
        return f"❌ {result.error}"

    async def _exec_file_action(self, action: str, **kwargs: Any) -> str:
        result = await self._call_agent("FileManagerAgent", action, action=action, **kwargs)
        if not result.success:
            return f"❌ {result.error}"
        d = result.data
        if action == "ls":
            return f"📂 *{d.get('path', '')}* ({d.get('count', 0)} itens)\n\n{d.get('listing', '')}"
        if action == "search":
            return f"🔍 `{d.get('query', '')}` ({d.get('count', 0)} resultados)\n\n```\n{d.get('results', '')}\n```"
        if action == "tree":
            return f"🌳 Estrutura\n\n```\n{d.get('tree', '')}\n```"
        return str(d)

    async def _exec_edit(self, path: str, instruction: str) -> str:
        """LLM-assisted file editing with robust code-fence stripping."""
        read = await self._call_agent("FileManagerAgent", "read", action="read", path=path)
        if not read.success:
            return f"❌ Não foi possível ler o arquivo: {read.error}"

        content = read.data.get("content", "")
        filename = read.data.get("path", path)

        edit_prompt = (
            f"You are editing the file `{filename}`.\n"
            f"Current content:\n```\n{content[:3000]}\n```\n\n"
            f"Apply this change: {instruction}\n\n"
            f"Return ONLY the complete new file content, no preamble, no markdown fences."
        )

        async with self._opencode_lock:
            use_opencode = self._opencode_ready

        if use_opencode and "OpenCodeAgent" in self._agents:
            cost = await self._call_agent("WatchdogAgent", "check_cost", model="opencode")
            if not cost.success:
                return f"🛡️ {cost.error}"
            llm_result = await self._call_agent(
                "OpenCodeAgent", edit_prompt, specialty="coding"
            )
        else:
            llm_result = await self._call_agent("LlmAgent", edit_prompt)

        if not llm_result.success:
            return f"⚠️ LLM error: {llm_result.error}"

        new_content = self._strip_code_fences(llm_result.data.get("response", ""))

        write = await self._call_agent(
            "FileManagerAgent", "write", action="write", path=path, content=new_content
        )
        if write.success:
            return f"✅ `{path}` editado com sucesso!\n\n_{instruction}_"
        return f"❌ Erro ao salvar: {write.error}"

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        """
        Removes leading/trailing code fences.
        Handles: ```python, ```js, ```, ``` (typed or plain).
        """
        stripped = re.sub(r"^```[a-zA-Z0-9]*\n?", "", text.strip())
        stripped = re.sub(r"\n?```$", "", stripped.strip())
        return stripped.strip()

    # ═══════════════════════════════════════════════════════════
    #  Formatting helpers
    # ═══════════════════════════════════════════════════════════

    async def _project_summary(self) -> str:
        status = self.get_status()
        async with self._opencode_lock:
            oc = "✅ Online" if self._opencode_ready else "⚠️ Offline"
        return (
            "🌙 *The Moon — Projeto*\n\n"
            f"🤖 Agentes ({status['agents_online']}): {', '.join(status['agents'])}\n"
            f"🛠 Skills ({status['skills_online']}): {', '.join(status['skills']) or 'nenhuma'}\n"
            f"📡 Canais ({status['channels_online']}): {', '.join(status['channels'])}\n"
            f"🔄 Loop proativo: {'✅ Ativo' if status['proactive_loop'] else '❌ Inativo'}\n"
            f"🤖 OpenCode: {oc}"
        )

    def _format_rooms_status(self) -> str:
        rooms = self.workspace_manager.get_all_rooms_status()
        if not rooms:
            return "📭 Nenhuma sala de reunião ativa."
        lines = ["🏢 *Escritório Transparente — Salas*\n"]
        for rid, s in rooms.items():
            icon = "🟢" if s["meeting_active"] else "⚪"
            line = f"{icon} *{rid.upper()}* | Líder: {s['leader']}"
            if s.get("sub_agents"):
                line += f"\n   └ Sub-agentes: {', '.join(s['sub_agents'])}"
            if s.get("computer_ready"):
                line += "\n   └ 💻 Computador: Online"
            lines.append(line)
        return "\n".join(lines)

    def _format_status(self) -> str:
        status = self.get_status()
        open_circuits = [n for n, c in self._circuits.items() if c.open]
        alert = ""
        if open_circuits:
            alert = f"\n⚠️ Circuitos abertos: {', '.join(open_circuits)}"
        return (
            "🌙 *The Moon — Status*\n\n"
            f"• Agentes: *{status['agents_online']}* online\n"
            f"• Skills: *{status['skills_online']}* registradas\n"
            f"• Canais: *{status['channels_online']}* ativos\n"
            f"• Loop Proativo: *{'Ativo' if status['proactive_loop'] else 'Inativo'}*"
            f"{alert}"
        )

    def _format_help(self) -> str:
        """Dynamically generated help from CommandRegistry + registered skills."""
        cats = self.registry.categories()
        lines = ["🌙 *The Moon — Comandos*\n"]

        category_order = ["Sistema", "Terminal", "Arquivos", "Skills", "Geral"]
        category_icons = {
            "Sistema": "📊",
            "Terminal": "💻",
            "Arquivos": "📁",
            "Skills": "⚙️",
            "Geral": "🔧",
        }

        for cat in category_order:
            entries = cats.get(cat)
            if not entries:
                continue
            icon = category_icons.get(cat, "•")
            lines.append(f"{icon} *{cat}*")
            seen = set()
            for e in entries:
                if e.usage not in seen:
                    lines.append(f"  `{e.usage}` — {e.description}")
                    seen.add(e.usage)

        if self.skills:
            lines.append("\n🛠 *Skills disponíveis*")
            for name in self.skills:
                lines.append(f"  `/skill {name}`")

        lines.append("\n💬 *Texto livre* — Groq Cloud (llama-3.3-70b)")
        return "\n".join(lines)

    # ═══════════════════════════════════════════════════════════
    #  Execution (public API)
    # ═══════════════════════════════════════════════════════════

    async def execute(
        self,
        task: str,
        agent_name: str = None,
        priority: AgentPriority = AgentPriority.MEDIUM,
        **kwargs: Any,
    ) -> TaskResult:
        if agent_name:
            return await self._call_agent(agent_name, task, **kwargs)
        return TaskResult(success=False, error="No agent_name provided.")

    async def execute_skill(self, skill_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if skill_name not in self.skills:
            return {"error": f"Skill '{skill_name}' not found"}

        await self.message_bus.publish(
            sender="orchestrator",
            topic="workspace.network",
            payload={"type": "skill_start", "skill": skill_name},
            target=skill_name,
        )
        result = await self.skills[skill_name].execute(params)
        await self.message_bus.publish(
            sender=skill_name,
            topic="workspace.network",
            payload={"type": "skill_done", "skill": skill_name},
            target="orchestrator",
        )
        return result

    # ═══════════════════════════════════════════════════════════
    #  Proactive Loop
    # ═══════════════════════════════════════════════════════════

    async def _proactive_loop(self) -> None:
        logger.info("Proactive loop started.")
        await asyncio.sleep(10)

        while True:
            try:
                await self.message_bus.publish(
                    sender="Orchestrator",
                    topic="monitor_events",
                    payload={
                        "type": "thought",
                        "agent": "Orchestrator",
                        "content": "Analisando estado do sistema e buscando oportunidades de automação...",
                    },
                    target="monitor",
                )
                await self._run_proactive_cycle()
                await asyncio.sleep(PROACTIVE_INTERVAL)
            except asyncio.CancelledError:
                logger.info("Proactive loop cancelled.")
                break
            except Exception as exc:
                logger.error(f"Proactive loop error: {exc}")
                await asyncio.sleep(PROACTIVE_INTERVAL)

    async def _run_proactive_cycle(self) -> None:
        """
        Proactive cycle: gathers meaningful events and broadcasts only if there
        is content worth sending (no spam on empty cycles).
        """
        logger.info("Running proactive cycle...")
        status = self.get_status()
        report_lines: List[str] = []

        async with self._opencode_lock:
            oc_ready = self._opencode_ready

        if oc_ready and "OpenCodeAgent" in self._agents:
            result = await self._call_agent(
                "OpenCodeAgent", "Latest AI and automation news", specialty="research"
            )
            if result.success:
                report_lines.append("📡 *Pesquisa autônoma concluída via OpenCode (Nemotron 3 Super).*")
            else:
                logger.warning(f"OpenCode research failed: {result.error}")

        elif "ResearcherAgent" in self._agents:
            result = await self._call_agent(
                "ResearcherAgent", "Latest AI and automation news", action="research"
            )
            if result.success:
                report_lines.append("📡 *Pesquisa autônoma concluída.*")

        if "BettingAnalystAgent" in self._agents:
            result = await self._call_agent("BettingAnalystAgent", "daily_tips")
            if result.success:
                report_lines.append("⚽ *Análise esportiva disponível.*")

        open_circuits = [n for n, c in self._circuits.items() if c.open]
        if open_circuits:
            report_lines.append(f"⚠️ *Agentes com falha*: {', '.join(open_circuits)}")

        if not report_lines:
            logger.info("Proactive cycle: nothing to report — skipping broadcast.")
            return

        report_lines.insert(0, "🔄 *Relatório Proativo — The Moon*\n")
        report_lines.append(
            f"\n_Agentes: {status['agents_online']} | "
            f"Skills: {status['skills_online']} | "
            f"Canais: {status['channels_online']}_"
        )
        await self.broadcast("\n".join(report_lines))

    # ═══════════════════════════════════════════════════════════
    #  Health Check Loop
    # ═══════════════════════════════════════════════════════════

    async def _health_check_loop(self) -> None:
        """Periodically pings all registered agents and updates circuit states."""
        while True:
            try:
                await self._check_all_agents_health()
            except Exception as exc:
                logger.error(f"Health check loop error: {exc}")
            await asyncio.sleep(60)

    async def _check_all_agents_health(self) -> None:
        """Pings each agent and refreshes OpenCode availability."""
        for name, agent in self._agents.items():
            try:
                if hasattr(agent, "ping"):
                    ok: bool = await asyncio.wait_for(agent.ping(), timeout=5)
                    if ok:
                        self._circuits[name].record_success()
                    else:
                        self._circuits[name].record_failure()
            except Exception:
                self._circuits[name].record_failure()
                logger.warning(f"Health check ping failed for '{name}'.")

        # Inject circuit breaker states into NexusIntelligence
        nexus = self.get_agent("NexusIntelligence")
        if nexus:
            open_circuits = [k for k, v in self._circuits.items() if v.open]
            setattr(nexus, "_open_circuits", open_circuits)

        if "OpenCodeAgent" in self._agents:
            try:
                models = await asyncio.wait_for(
                    self._agents["OpenCodeAgent"].list_models(), timeout=10
                )
                async with self._opencode_lock:
                    self._opencode_ready = bool(models)
                if self._opencode_ready:
                    logger.info(f"OpenCode ONLINE — models: {', '.join(models)}")
                else:
                    logger.warning("OpenCode returned empty model list.")
            except Exception as exc:
                async with self._opencode_lock:
                    self._opencode_ready = False
                logger.error(f"OpenCode health check failed: {exc}")

    # ═══════════════════════════════════════════════════════════
    #  Broadcast
    # ═══════════════════════════════════════════════════════════

    async def broadcast(self, message: str) -> None:
        for channel in self.channels:
            try:
                await channel.send_message(message)
            except Exception as exc:
                logger.error(f"Broadcast error on '{channel.name}': {exc}")

    # ═══════════════════════════════════════════════════════════
    #  GitHub Auto-Sync Hook
    # ═══════════════════════════════════════════════════════════

    async def _post_execution_sync(
        self,
        task_description: str = "",
        force: bool = False
    ) -> None:
        """
        Hook pós-execução: sincroniza com GitHub se houver mudanças.
        Chamado automaticamente após cada ciclo de execução do Orchestrator.
        Falha silenciosamente — nunca interrompe o fluxo principal.
        """
        try:
            from core.services.auto_sync import get_auto_sync
            sync = get_auto_sync()

            if not force and not sync.is_dirty():
                return  # Nada a fazer

            # Montar mensagem baseada na task executada
            msg = None
            if task_description:
                # Limitar a 72 chars (convenção de commits)
                short_desc = task_description[:50].replace("\n", " ")
                msg = f"auto: {short_desc}"

            result = await sync.sync_now(message=msg)

            if result.success and result.committed:
                logger.info(
                    f"Orchestrator: auto-sync OK — "
                    f"{len(result.files_changed)} arquivo(s) "
                    f"commit={result.commit_sha}"
                )
                # Publicar evento na MessageBus para rastreabilidade
                await self._publish_sync_event(result)
            elif not result.success:
                logger.warning(f"Orchestrator: auto-sync falhou: {result.error}")

        except Exception as exc:
            logger.warning(f"Orchestrator._post_execution_sync: {exc}")

    async def _publish_sync_event(self, result) -> None:
        """Publica evento de sync na MessageBus."""
        try:
            payload = {
                "type": "github_sync",
                "committed": result.committed,
                "pushed": result.pushed,
                "files": result.files_changed,
                "sha": result.commit_sha,
                "timestamp": result.timestamp,
            }
            await self.message_bus.publish(
                "orchestrator", "system.sync", payload
            )
        except Exception:
            pass  # Não crítico

    # ═══════════════════════════════════════════════════════════
    #  Status
    # ═══════════════════════════════════════════════════════════

    def get_status(self) -> Dict[str, Any]:
        return {
            "agents_online": len(self._agents),
            "skills_online": len(self.skills),
            "channels_online": len(self.channels),
            "agents": list(self._agents.keys()),
            "skills": list(self.skills.keys()),
            "channels": [ch.name for ch in self.channels],
            "proactive_loop": (
                self._autonomous_task is not None
                and not self._autonomous_task.done()
            ),
            "open_circuits": [n for n, c in self._circuits.items() if c.open],
        }

    # ═══════════════════════════════════════════════════════════
    #  Code Verification
    # ═══════════════════════════════════════════════════════════

    async def evaluate_solutions(
        self, task_description: str, context: Dict[str, Any]
    ) -> str:
        """
        Tree-of-Thoughts: delegates to LlmAgent to produce and rank 3 approaches,
        then returns the highest-scored plan.
        """
        logger.info(f"ToT evaluation for: {task_description[:60]}...")

        tot_prompt = (
            f"Task: {task_description}\n"
            f"Context: {context}\n\n"
            "Generate 3 distinct architectural approaches (Conservative, Optimized, Experimental). "
            "For each: name, summary, risk (Low/Med/High), gain (Low/Med/High). "
            "Select the best trade-off and end with: SELECTED: <approach name>"
        )

        result = await self._call_agent("LlmAgent", tot_prompt, timeout=45)
        if result.success:
            response = result.data.get("response", "")
            match = re.search(r"SELECTED:\s*(.+)", response)
            if match:
                return match.group(1).strip()
            return response

        logger.warning("ToT LLM call failed — defaulting to Optimized approach.")
        return "Abordagem 2: Otimizada (High-Performance)"

    def verify_code(self, code: str, skill_context: str) -> Dict[str, Any]:
        """Runs code through the LangGraph verification loop."""
        state = VerificationState(
            original_command="Internal Verification",
            skill_name=skill_context,
            current_code=code,
        )
        final_state = self.verification_graph.run(state)
        return {
            "status": final_state.status.value,
            "code": final_state.final_code,
            "score": final_state.quality_score,
            "errors": final_state.error_message,
        }

    def _get_session_context(self, user_id: str = None, channel: str = None, workspace: str = None, mode: str = "user") -> dict:
        session_id = self.session_manager.build_session_id(mode, user_id or "", channel or "", workspace or "")
        return self.session_manager.get_session(session_id)

    def _set_session_context(self, data: dict, user_id: str = None, channel: str = None, workspace: str = None, mode: str = "user") -> None:
        session_id = self.session_manager.build_session_id(mode, user_id or "", channel or "", workspace or "")
        self.session_manager.set_session(session_id, data)

    async def _handle_flow_command(self, args: str, metadata: dict) -> str:
        parts = args.strip().split(None, 1)
        flow_name = parts[0] if parts else ""
        ctx = {"topic": parts[1]} if len(parts) > 1 else {}
        flow = self.flow_registry.get(flow_name)
        if not flow:
            available = ", ".join(self.flow_registry.list_flows())
            return f"Flow '{flow_name}' não encontrado. Disponíveis: {available}"
        result = await flow.execute(ctx, self)
        if result.success:
            return f"✅ Flow '{flow_name}' executado com sucesso em {result.total_time:.2f}s"
        else:
            return f"❌ Flow '{flow_name}' falhou: {result.error}"

    def _load_default_flows(self) -> None:
        import pathlib
        flows_dir = pathlib.Path("flows")
        if flows_dir.exists():
            for f in flows_dir.glob("*.json"):
                try:
                    flow = self.flow_registry.load_from_file(str(f))
                    self.flow_registry.register(flow)
                except Exception as e:
                    pass  # silencioso, nunca bloqueia startup

    async def _handle_devops_scan_complete(self, message: Dict[str, Any]) -> None:
        """
        Handles the completion of a DevOps scan.
        Logs the summary and can be expanded for health-based decisions.
        """
        summary = message.get("summary", {})
        count = summary.get("total_issues", 0)
        critical = summary.get("critical", 0)
        
        logger.info(f"DevOps Scan Complete: {count} issues found ({critical} critical).")
        
        if critical > 0:
            logger.warning(f"CRITICAL implementation debt detected! Check data/devops_reports/")
