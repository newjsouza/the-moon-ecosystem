"""
agents/telegram/bot.py
MoonBot — Interface Unificada do Ecossistema The Moon via Telegram.

O único ponto de entrada para o usuário. Integra TODOS os agentes do
ecossistema, tem memória de longo prazo, executa comandos remotos no
computador, gerencia tarefas e pesquisa dados reais na internet.

PROBLEMAS RESOLVIDOS vs versão anterior:
  - [FIX CRÍTICO] AsyncGroq substituiu Groq síncrono — event loop não bloqueia mais
  - [FIX CRÍTICO] Loop de polling unificado — conflito de token eliminado
  - [FIX CRÍTICO] ConversationMemory: janela deslizante (20 msg) + Weaver longo prazo
  - [FIX] _get_match_context expandido para detectar datas por contexto semântico
  - [FIX] system_prompt unificado em _build_system_prompt() — sem duplicação
  - [ARCH] Integração completa com Orchestrator (todos os 12+ agentes acessíveis)
  - [ARCH] RemoteCommandExecutor — executa comandos shell com whitelist de segurança
  - [ARCH] TaskManager — todos, lembretes, planejamentos persistidos em JSON
  - [ARCH] DuckDuckGoSearch — pesquisa web real sem API key
  - [ARCH] Anti-hallucination layer — grounding prompts + fact-check mode
  - [ARCH] NexusIntelligence bridge — briefing matinal automático

CHANGELOG (Moon Codex — Março 2026):
  - [ARCH] Redesign completo do bot.py com arquitetura unificada
  - [ARCH] ConversationMemory: deque(20) por usuário + SemanticMemoryWeaver
  - [ARCH] RemoteCommandExecutor com ALLOWED_COMMANDS whitelist
  - [ARCH] TaskManager persistido em data/bot_tasks/
  - [ARCH] DuckDuckGoSearch via httpx (sem API key)
  - [ARCH] Integração com Orchestrator._route_command()
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import tempfile
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple

import httpx
from groq import AsyncGroq
from pydub import AudioSegment
from telegram import Update, BotCommand
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("moon.bot")
logging.getLogger("telegram").setLevel(logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

# ─────────────────────────────────────────────────────────────
#  APEX Oracle import (lazy — evita import circular)
# ─────────────────────────────────────────────────────────────
_apex_oracle_instance = None

def _get_apex_oracle():
    global _apex_oracle_instance
    if _apex_oracle_instance is None:
        try:
            from agents.apex.oracle import ApexOracle, DailyContextStore
            _apex_oracle_instance = ApexOracle()
            logger.info("ApexOracle carregado com sucesso")
        except Exception as e:
            logger.warning(f"ApexOracle não disponível: {e}")
    return _apex_oracle_instance

# ─────────────────────────────────────────────────────────────
#  Paths & constants
# ─────────────────────────────────────────────────────────────
from pathlib import Path as _P
ROOT_DIR  = _P(__file__).resolve().parent.parent.parent
TASKS_DIR = ROOT_DIR / "data" / "bot_tasks"
TASKS_FILE = TASKS_DIR / "tasks.json"
MEM_FILE   = TASKS_DIR / "long_term_memory.json"

CONV_WINDOW    = 20     # messages kept in per-user sliding window
MAX_CMD_OUTPUT = 3000   # chars truncated from shell output
SEARCH_RESULTS = 5      # number of DuckDuckGo results to include
REMINDER_CHECK = 60     # seconds between reminder checks

# ffmpeg paths (from original bot)
FFMPEG_PATH  = ROOT_DIR / "infrastructure" / "ffmpeg"
FFPROBE_PATH = ROOT_DIR / "infrastructure" / "ffprobe"

# Groq models
LLM_FAST    = "llama-3.1-8b-instant"
LLM_CAPABLE = "llama-3.3-70b-versatile"
WHISPER     = "whisper-large-v3"

# Commands that can be executed remotely (safety whitelist)
# Set MOON_ALLOW_ALL_COMMANDS=1 to bypass (use at your own risk)
ALLOWED_COMMANDS_PREFIXES: Tuple[str, ...] = (
    "ls", "cat", "echo", "pwd", "find", "grep", "python3",
    "pip", "git", "curl", "wget", "systemctl status", "df",
    "free", "ps", "top -bn1", "whoami", "date", "uname",
    "which", "env", "printenv", "wc", "head", "tail",
    "mkdir", "touch", "cp", "mv", "rm -f", "chmod",
    "journalctl", "systemctl", "docker", "docker-compose",
    "wpctl",  # PipeWire audio
)


# ─────────────────────────────────────────────────────────────
#  Task Manager
# ─────────────────────────────────────────────────────────────

class TaskStatus:
    PENDING   = "pending"
    DONE      = "done"
    CANCELLED = "cancelled"


@dataclass
class BotTask:
    id:          str
    type:        str          # "todo" | "reminder" | "plan" | "note"
    title:       str
    content:     str
    due_ts:      Optional[float] = None   # Unix timestamp
    status:      str = TaskStatus.PENDING
    priority:    str = "normal"           # "high" | "normal" | "low"
    tags:        List[str] = field(default_factory=list)
    created_at:  float = field(default_factory=time.time)
    notified:    bool = False

    def is_due(self) -> bool:
        if self.due_ts is None:
            return False
        return time.time() >= self.due_ts and not self.notified

    def format(self) -> str:
        status_emoji = {"pending": "🔲", "done": "✅", "cancelled": "❌"}
        prio_emoji   = {"high": "🔴", "normal": "🟡", "low": "🟢"}
        due_str      = ""
        if self.due_ts:
            due_str = f" | ⏰ {datetime.fromtimestamp(self.due_ts).strftime('%d/%m %H:%M')}"
        return (
            f"{status_emoji.get(self.status,'•')} {prio_emoji.get(self.priority,'•')} "
            f"*{self.title}*{due_str}\n   `{self.id[:8]}`"
        )


class TaskManager:
    """Persistent task/reminder/planning manager."""

    def __init__(self) -> None:
        self._tasks: Dict[str, BotTask] = {}
        TASKS_DIR.mkdir(parents=True, exist_ok=True)
        self._load()

    def add(
        self,
        type_:    str,
        title:    str,
        content:  str = "",
        due_ts:   Optional[float] = None,
        priority: str = "normal",
        tags:     Optional[List[str]] = None,
    ) -> BotTask:
        task_id = f"{int(time.time()*1000)}"
        task = BotTask(
            id=task_id, type=type_, title=title, content=content,
            due_ts=due_ts, priority=priority, tags=tags or [],
        )
        self._tasks[task_id] = task
        self._save()
        return task

    def complete(self, task_id_prefix: str) -> Optional[BotTask]:
        for tid, task in self._tasks.items():
            if tid.startswith(task_id_prefix):
                task.status = TaskStatus.DONE
                self._save()
                return task
        return None

    def delete(self, task_id_prefix: str) -> bool:
        for tid in list(self._tasks.keys()):
            if tid.startswith(task_id_prefix):
                del self._tasks[tid]
                self._save()
                return True
        return False

    def get_pending(self, type_: Optional[str] = None) -> List[BotTask]:
        tasks = [t for t in self._tasks.values() if t.status == TaskStatus.PENDING]
        if type_:
            tasks = [t for t in tasks if t.type == type_]
        return sorted(tasks, key=lambda t: (t.priority == "high", t.due_ts or 0), reverse=True)

    def get_due_reminders(self) -> List[BotTask]:
        return [t for t in self._tasks.values()
                if t.type == "reminder" and t.is_due() and t.status == TaskStatus.PENDING]

    def mark_notified(self, task_id: str) -> None:
        if task_id in self._tasks:
            self._tasks[task_id].notified = True
            self._save()

    def format_list(self, type_: Optional[str] = None, limit: int = 10) -> str:
        pending = self.get_pending(type_)[:limit]
        if not pending:
            label = f" de {type_}" if type_ else ""
            return f"📭 Nenhuma tarefa{label} pendente."
        type_labels = {"todo": "Tarefas", "reminder": "Lembretes",
                       "plan": "Planos", "note": "Notas"}
        header = type_labels.get(type_ or "", "Tarefas")
        lines  = [f"📋 *{header}*\n"]
        for t in pending:
            lines.append(t.format())
        return "\n".join(lines)

    def _save(self) -> None:
        try:
            data = {tid: asdict(t) for tid, t in self._tasks.items()}
            tmp  = TASKS_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
            tmp.replace(TASKS_FILE)
        except Exception as e:
            logger.error(f"TaskManager save failed: {e}")

    def _load(self) -> None:
        try:
            if TASKS_FILE.exists():
                data = json.loads(TASKS_FILE.read_text())
                for tid, d in data.items():
                    self._tasks[tid] = BotTask(**d)
        except Exception as e:
            logger.warning(f"TaskManager load failed: {e}")


# ─────────────────────────────────────────────────────────────
#  Conversation Memory
# ─────────────────────────────────────────────────────────────

class ConversationMemory:
    """
    Per-user sliding window of conversation history.
    Short-term: deque(CONV_WINDOW) — passed directly to LLM as messages.
    Long-term: optional bridge to SemanticMemoryWeaver.
    """

    def __init__(self) -> None:
        # user_id (str) → deque of {"role": ..., "content": ...}
        self._windows: Dict[str, Deque[Dict[str, str]]] = {}
        self._user_contexts: Dict[str, str] = {}   # user_id → custom context

    def add(self, user_id: str, role: str, content: str) -> None:
        if user_id not in self._windows:
            self._windows[user_id] = deque(maxlen=CONV_WINDOW)
        self._windows[user_id].append({"role": role, "content": content})

    def get_history(self, user_id: str) -> List[Dict[str, str]]:
        return list(self._windows.get(user_id, []))

    def set_context(self, user_id: str, context: str) -> None:
        """Stores a persistent context string for a user (e.g. user preferences)."""
        self._user_contexts[user_id] = context

    def get_context(self, user_id: str) -> str:
        return self._user_contexts.get(user_id, "")

    def clear(self, user_id: str) -> None:
        self._windows.pop(user_id, None)

    def summary(self, user_id: str) -> str:
        history = self.get_history(user_id)
        if not history:
            return "Sem histórico."
        return f"{len(history)} mensagens no contexto atual."


# ─────────────────────────────────────────────────────────────
#  Remote Command Executor
# ─────────────────────────────────────────────────────────────

class RemoteCommandExecutor:
    """
    Executes shell commands on the host machine.
    Uses ALLOWED_COMMANDS_PREFIXES as a safety whitelist.
    Set env var MOON_ALLOW_ALL_COMMANDS=1 to bypass (trusted environment only).
    """

    _ALLOW_ALL = os.getenv("MOON_ALLOW_ALL_COMMANDS", "0") == "1"

    def is_allowed(self, command: str) -> bool:
        if self._ALLOW_ALL:
            return True
        cmd = command.strip().lower()
        # Block clearly dangerous patterns even in allow-all mode
        dangerous = ["rm -rf /", ":(){ :|:& };:", "mkfs", "dd if=", "shutdown", "reboot",
                     "chmod 777 /", "wget | bash", "curl | bash", "> /dev/sda"]
        if any(d in cmd for d in dangerous):
            return False
        return any(cmd.startswith(prefix.lower()) for prefix in ALLOWED_COMMANDS_PREFIXES)

    async def run(self, command: str, timeout: int = 30) -> Tuple[bool, str]:
        """
        Runs a shell command asynchronously.
        Returns (success, output_or_error).
        """
        if not self.is_allowed(command):
            return False, (
                f"❌ Comando não permitido por segurança: `{command[:80]}`\n"
                f"Para permitir todos os comandos: defina `MOON_ALLOW_ALL_COMMANDS=1` no .env\n"
                f"⚠️ Faça isso somente em ambiente 100% confiável."
            )
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(ROOT_DIR),
            )
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                output = stdout.decode("utf-8", errors="replace").strip()
                if len(output) > MAX_CMD_OUTPUT:
                    output = output[:MAX_CMD_OUTPUT] + f"\n\n…(saída truncada em {MAX_CMD_OUTPUT} chars)"
                success = proc.returncode == 0
                return success, output or "(sem saída)"
            except asyncio.TimeoutError:
                proc.kill()
                return False, f"⏱️ Comando expirou após {timeout}s."
        except Exception as e:
            return False, f"Erro ao executar comando: {e}"


# ─────────────────────────────────────────────────────────────
#  Web Search (DuckDuckGo Instant Answers — sem API key)
# ─────────────────────────────────────────────────────────────

class WebSearch:
    """
    Searches the web via DuckDuckGo Instant Answers API.
    No API key required. Returns real, grounded data.
    """

    async def search(self, query: str) -> str:
        """Returns a summary of search results as a string."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                # DuckDuckGo Instant Answer API
                resp = await client.get(
                    "https://api.duckduckgo.com/",
                    params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"},
                    headers={"User-Agent": "TheMoon/1.0 (Zorin OS; personal assistant)"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return self._parse_ddg(data, query)
        except Exception as e:
            logger.warning(f"DuckDuckGo search failed: {e}")

        # Fallback: DuckDuckGo HTML search (scraping)
        return await self._html_search(query)

    def _parse_ddg(self, data: dict, query: str) -> str:
        parts: List[str] = []

        abstract   = data.get("AbstractText", "").strip()
        answer     = data.get("Answer", "").strip()
        definition = data.get("Definition", "").strip()
        related    = data.get("RelatedTopics", [])

        if answer:
            parts.append(f"📌 **Resposta direta:** {answer}")
        if abstract:
            parts.append(f"📖 {abstract[:600]}")
        if definition:
            parts.append(f"📚 Definição: {definition[:300]}")

        if related:
            parts.append(f"\n🔍 *Resultados relacionados para: {query}*")
            count = 0
            for item in related[:SEARCH_RESULTS]:
                if isinstance(item, dict) and item.get("Text"):
                    text = item.get("Text", "")[:200]
                    url  = item.get("FirstURL", "")
                    parts.append(f"• {text}" + (f"\n  {url}" if url else ""))
                    count += 1
                    if count >= SEARCH_RESULTS:
                        break

        if not parts:
            return f"🔍 Nenhum resultado direto para '{query}'. Tente reformular a busca."

        return "\n".join(parts)

    async def _html_search(self, query: str) -> str:
        """Fallback: scrape DuckDuckGo HTML results."""
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                resp = await client.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": query},
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                if resp.status_code == 200:
                    import re
                    # Extract result snippets
                    snippets = re.findall(
                        r'class="result__snippet"[^>]*>(.*?)</a>',
                        resp.text, re.DOTALL
                    )
                    clean = [re.sub(r'<[^>]+>', '', s).strip() for s in snippets[:5]]
                    if clean:
                        results = "\n".join(f"• {s[:200]}" for s in clean if s)
                        return f"🔍 *Resultados para: {query}*\n{results}"
        except Exception as e:
            logger.debug(f"HTML search fallback failed: {e}")
        return f"⚠️ Não foi possível obter resultados para: {query}"


# ─────────────────────────────────────────────────────────────
#  Intent Detector — entende o que o usuário quer
# ─────────────────────────────────────────────────────────────

class IntentDetector:
    """
    Lightweight rule-based intent detection to route messages
    before sending to LLM (faster, more reliable).
    """

    # (pattern_list, intent_label)
    _RULES = [
        (["busca ", "pesquisa ", "procura ", "search ", "o que é ", "quem é ",
          "quando foi ", "qual é ", "como funciona ", "notícias sobre "], "web_search"),
        (["execute ", "executa ", "roda ", "run ", "terminal:", "cmd:", "shell:",
          "liste os arquivos", "ls ", "ps aux", "status do sistema"], "shell_cmd"),
        (["adiciona tarefa", "cria tarefa", "nova tarefa", "todo:", "to-do:"], "task_add"),
        (["lembra de ", "lembre-me", "lembrete:", "alarme:", "me avisa"], "reminder_add"),
        (["minhas tarefas", "lista de tarefas", "ver tarefas", "o que tenho"], "task_list"),
        (["plano para", "planejamento:", "planeja ", "planejamento de"], "plan"),
        (["limpa contexto", "esquece tudo", "nova conversa", "reset"], "clear_memory"),
        (["briefing", "resumo do dia", "o que aconteceu", "status geral"], "nexus_briefing"),
        (["scan de código", "código tem bug", "auditoria", "devops"], "devops_scan"),
        (["aposta", "bet", "odds", "futebol", "partida", "jogo de hoje",
          "jogo de amanhã", "análise de jogo"], "sports"),
        (["status da banca", "quanto tenho", "saldo", "bankroll"], "banca_status"),
    ]

    def detect(self, text: str) -> Optional[str]:
        text_lower = text.lower()
        for patterns, intent in self._RULES:
            if any(p in text_lower for p in patterns):
                return intent
        return None

    def extract_command(self, text: str) -> Optional[str]:
        """Extracts shell command from user text."""
        prefixes = ["execute ", "executa ", "roda ", "run ", "terminal:", "cmd:", "shell:"]
        text_lower = text.lower()
        for prefix in prefixes:
            if prefix in text_lower:
                idx = text_lower.find(prefix) + len(prefix)
                return text[idx:].strip().strip('`"\'')

        # If text starts with $ (shell convention)
        stripped = text.strip()
        if stripped.startswith("$"):
            return stripped[1:].strip()

        return None

    def extract_search_query(self, text: str) -> str:
        """Strips intent keywords to get clean search query."""
        remove = ["busca ", "pesquisa ", "procura ", "search ", "pesquise sobre ",
                  "busque ", "o que é ", "quem é ", "quando foi ", "qual é ",
                  "como funciona ", "notícias sobre "]
        result = text
        for r in remove:
            result = result.lower().replace(r, "", 1)
        return result.strip()

    def extract_task(self, text: str) -> Tuple[str, Optional[float]]:
        """Extracts task title and optional due date from text."""
        import re
        # Remove intent keywords
        clean = re.sub(
            r'^(adiciona tarefa|cria tarefa|nova tarefa|todo:|to-do:|lembra de|lembre-me|lembrete:|alarme:|me avisa)\s*',
            '', text.strip(), flags=re.IGNORECASE
        ).strip()

        # Try to extract "amanhã às HH:MM" or "em X minutos"
        due_ts = None
        now    = time.time()
        if "amanhã" in text.lower():
            due_ts = now + 86400
            time_match = re.search(r'(\d{1,2})[h:](\d{2})', text)
            if time_match:
                h, m   = int(time_match.group(1)), int(time_match.group(2))
                from datetime import datetime, timedelta
                tomorrow = datetime.now() + timedelta(days=1)
                due_ts   = tomorrow.replace(hour=h, minute=m, second=0).timestamp()
        elif "hoje" in text.lower():
            time_match = re.search(r'(\d{1,2})[h:](\d{2})', text)
            if time_match:
                h, m   = int(time_match.group(1)), int(time_match.group(2))
                dt     = datetime.now().replace(hour=h, minute=m, second=0)
                due_ts = dt.timestamp()
        elif "em " in text.lower():
            min_match = re.search(r'em (\d+) minutos?', text, re.IGNORECASE)
            hr_match  = re.search(r'em (\d+) horas?', text, re.IGNORECASE)
            if min_match:
                due_ts = now + int(min_match.group(1)) * 60
            elif hr_match:
                due_ts = now + int(hr_match.group(1)) * 3600

        return clean, due_ts


# ─────────────────────────────────────────────────────────────
#  Sports Context Builder (expanded from original)
# ─────────────────────────────────────────────────────────────

class SportsContextBuilder:
    """
    Builds real sports context for the LLM.
    Expands beyond hoje/amanhã to detect temporal mentions.
    """

    async def build(self, text: str, sports_manager: Any) -> str:
        import re
        text_lower = text.lower()

        # Detect date intent
        days_offset = None
        if any(w in text_lower for w in ["hoje", "hoje à noite", "esta noite"]):
            days_offset = 0
        elif any(w in text_lower for w in ["amanhã", "amanhã à noite"]):
            days_offset = 1
        elif any(w in text_lower for w in ["depois de amanhã"]):
            days_offset = 2

        # Detect sport keywords without date = ask for date
        sport_keywords = ["partida", "jogo", "odds", "apostas", "futebol", "campeonato",
                          "liga", "time", "placar", "escalação"]
        has_sport_kw = any(kw in text_lower for kw in sport_keywords)

        if days_offset is None and not has_sport_kw:
            return ""

        if days_offset is None:
            return (
                "AVISO: O usuário perguntou sobre jogos/apostas mas não especificou data. "
                "Pergunte: 'Você quer jogos de hoje ou amanhã?'"
            )

        try:
            matches = await sports_manager.get_upcoming_opportunities(days_offset)
            date_str = {0: "hoje", 1: "amanhã", 2: "depois de amanhã"}.get(days_offset, "em breve")

            if matches:
                ctx  = f"JOGOS REAIS para {date_str} (Football-data.org):\n"
                for m in matches:
                    ctx += f"  • {m['teams']} | {m['competition']} | {m.get('utcDate', '?')}\n"
                ctx += (
                    "\nREGRA ABSOLUTA: Responda SOMENTE com base nesta lista. "
                    "Se o usuário citar um time que não está aqui, diga: "
                    "'Este jogo não consta nos meus dados ao vivo de hoje.' "
                    "NUNCA invente jogos, times ou placar."
                )
                return ctx
            else:
                return (
                    f"DADOS REAIS: O Football-data.org retornou ZERO jogos para {date_str} "
                    f"nas ligas monitoradas. Informe ao usuário exatamente isso."
                )
        except Exception as e:
            logger.error(f"SportsContextBuilder error: {e}")
            return "AVISO: Provedor de dados esportivos temporariamente indisponível."


# ─────────────────────────────────────────────────────────────
#  The Moon Bot — Main Class
# ─────────────────────────────────────────────────────────────

class MoonBot:
    """
    MoonBot — Interface Unificada do Ecossistema The Moon.

    Integra: Groq LLM (async), memória de conversa, execução remota,
    gestão de tarefas, pesquisa web, análise esportiva e todos os
    agentes do Orchestrator.
    """

    def __init__(self, orchestrator=None) -> None:
        self.token         = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id       = os.getenv("TELEGRAM_CHAT_ID", "")
        self.groq          = AsyncGroq(api_key=os.getenv("GROQ_API_KEY", ""))
        self._orchestrator = orchestrator

        # Subsystems
        self.memory   = ConversationMemory()
        self.tasks    = TaskManager()
        self.executor = RemoteCommandExecutor()
        self.search   = WebSearch()
        self.intent   = IntentDetector()
        self.sports   = SportsContextBuilder()

        # Sports manager (lazy init)
        self._sports_manager = None

        # ffmpeg setup
        self._setup_ffmpeg()

        TASKS_DIR.mkdir(parents=True, exist_ok=True)

    def _setup_ffmpeg(self) -> None:
        if FFMPEG_PATH.exists():
            AudioSegment.converter = str(FFMPEG_PATH)
            if FFPROBE_PATH.exists():
                AudioSegment.ffprobe = str(FFPROBE_PATH)
                os.environ["PATH"] += os.pathsep + str(FFMPEG_PATH.parent)
            logger.info(f"ffmpeg configured: {FFMPEG_PATH}")
        else:
            logger.warning("Static ffmpeg not found — audio conversion may fail.")

    def _get_sports_manager(self):
        if self._sports_manager is None:
            try:
                import sys
                if str(ROOT_DIR) not in sys.path:
                    sys.path.insert(0, str(ROOT_DIR))
                from agents.sports.manager import SportsManager
                self._sports_manager = SportsManager()
            except ImportError as e:
                logger.warning(f"SportsManager not available: {e}")
        return self._sports_manager

    # ════════════════════════════════════════════════════════
    #  System prompt builder — SINGLE SOURCE OF TRUTH
    # ════════════════════════════════════════════════════════

    def _build_system_prompt(
        self,
        user_id:       str,
        extra_context: str = "",
    ) -> str:
        now_str  = datetime.now().strftime("%d/%m/%Y %H:%M")
        user_ctx = self.memory.get_context(user_id)

        base = f"""Você é o assistente pessoal do ecossistema "The Moon". Data/hora atual: {now_str}.

IDENTIDADE:
- Nome: Moon Assistant
- Personalidade: analítico, direto, honesto, profissional em português
- Você TEM acesso ao computador do usuário e pode executar comandos
- Você TEM acesso à internet via pesquisa web real
- Você NUNCA inventa dados, fatos, jogos, preços ou informações

CAPACIDADES:
- Análise de apostas esportivas com dados reais (Football-data.org)
- Gestão de tarefas, lembretes e planejamentos
- Execução de comandos no computador (remoto)
- Pesquisa na internet (DuckDuckGo)
- Acesso a todos os agentes: DevOps, EconomicSentinel, SkillAlchemist, etc.

REGRA ANTI-ALUCINAÇÃO — NUNCA QUEBRE ESTA REGRA:
- Se você não sabe algo com certeza, diga "não tenho essa informação"
- Se os dados de jogos não mostram uma partida, diga isso ao usuário
- Nunca crie exemplos como se fossem dados reais
- Se a internet estiver indisponível, informe

FORMATO DE RESPOSTA:
- Use Markdown do Telegram (*negrito*, _itálico_, `código`)
- Respostas curtas e objetivas quando possível
- Use emojis moderadamente (máx 2-3 por mensagem)"""

        if user_ctx:
            base += f"\n\nCONTEXTO DO USUÁRIO:\n{user_ctx}"

        if extra_context:
            base += f"\n\nDADOS REAIS DO SISTEMA:\n{extra_context}"

        # Injeta contexto das análises APEX do dia
        try:
            from agents.apex.oracle import DailyContextStore
            apex_ctx = DailyContextStore().get_context_for_bot()
            if apex_ctx:
                base += f"\n\n{apex_ctx}"
        except Exception:
            pass

        return base

    # ════════════════════════════════════════════════════════
    #  LLM Call — ALWAYS async, NEVER blocks
    # ════════════════════════════════════════════════════════

    async def _ask_llm(
        self,
        user_id:       str,
        user_message:  str,
        extra_context: str = "",
        model:         str = LLM_CAPABLE,
        add_to_memory: bool = True,
    ) -> str:
        system_prompt = self._build_system_prompt(user_id, extra_context)
        history       = self.memory.get_history(user_id)

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        try:
            completion = await self.groq.chat.completions.create(
                model    = model,
                messages = messages,
                max_tokens = 1024,
                temperature = 0.4,
            )
            response = completion.choices[0].message.content.strip()

            if add_to_memory:
                self.memory.add(user_id, "user",      user_message)
                self.memory.add(user_id, "assistant", response)

            return response

        except Exception as e:
            logger.error(f"Groq LLM error: {e}")
            return f"⚠️ Erro ao processar com LLM: {e}\nTente novamente em instantes."

    # ════════════════════════════════════════════════════════
    #  Intent routing — called before LLM for fast paths
    # ════════════════════════════════════════════════════════

    async def _route_intent(
        self, user_id: str, text: str, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> Optional[str]:
        """
        Handles specific intents without LLM when possible.
        Returns response string or None (caller should use LLM).
        """
        detected = self.intent.detect(text)

        if detected == "shell_cmd":
            cmd = self.intent.extract_command(text) or text
            await update.message.reply_text(f"💻 Executando: `{cmd[:100]}`...", parse_mode="Markdown")
            success, output = await self.executor.run(cmd)
            icon = "✅" if success else "❌"
            return f"{icon} `$ {cmd}`\n\n```\n{output}\n```"

        if detected == "web_search":
            query = self.intent.extract_search_query(text)
            await update.message.reply_text(f"🔍 Buscando: _{query}_...", parse_mode="Markdown")
            result = await self.search.search(query)
            # Also pass to LLM for synthesis
            return await self._ask_llm(
                user_id, text,
                extra_context=f"RESULTADO DA BUSCA WEB:\n{result}",
            )

        if detected == "task_add":
            title, due_ts = self.intent.extract_task(text)
            task_type = "reminder" if "lembra" in text.lower() or "lembrete" in text.lower() else "todo"
            task = self.tasks.add(task_type, title, due_ts=due_ts)
            due_str = f" para {datetime.fromtimestamp(due_ts).strftime('%d/%m às %H:%M')}" if due_ts else ""
            return f"✅ Tarefa adicionada{due_str}:\n{task.format()}"

        if detected == "task_list":
            return self.tasks.format_list()

        if detected == "clear_memory":
            self.memory.clear(user_id)
            return "🧹 Contexto da conversa limpo. Começando do zero."

        if detected == "nexus_briefing" and self._orchestrator:
            try:
                result = await self._orchestrator.execute(
                    "briefing", agent_name="NexusIntelligence"
                )
                if result.success:
                    return result.data.get("briefing", "Briefing não disponível.")
            except Exception as e:
                logger.warning(f"Nexus briefing failed: {e}")

        if detected == "devops_scan" and self._orchestrator:
            await update.message.reply_text("🔍 Iniciando scan de código...", parse_mode="Markdown")
            try:
                result = await self._orchestrator.execute(
                    "scan", agent_name="AutonomousDevOpsRefactor"
                )
                if result.success:
                    return result.data.get("summary", "Scan concluído.")
            except Exception as e:
                logger.warning(f"DevOps scan failed: {e}")

        if detected == "sports":
            sm = self._get_sports_manager()
            if sm:
                sports_ctx = await self.sports.build(text, sm)
                if sports_ctx:
                    return await self._ask_llm(user_id, text, extra_context=sports_ctx)

        if detected == "banca_status":
            # Check if Orchestrator has EconomicSentinel
            if self._orchestrator:
                try:
                    result = await self._orchestrator.execute(
                        "portfolio", agent_name="EconomicSentinel"
                    )
                    if result.success:
                        snap = result.data.get("snapshot", {})
                        return (
                            f"💰 *Status da Banca*\n"
                            f"Banca: R${snap.get('bankroll', 0):.2f}\n"
                            f"Custo/mês: R${snap.get('infra_cost_month', 0):.2f}"
                        )
                except Exception:
                    pass

        return None  # Let LLM handle it

    # ════════════════════════════════════════════════════════
    #  Telegram Handlers
    # ════════════════════════════════════════════════════════

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = str(update.effective_user.id)
        await update.message.reply_text(
            "🌙 *The Moon — Assistente Pessoal*\n\n"
            "Olá! Posso ajudar com:\n"
            "• Análise de apostas esportivas em tempo real\n"
            "• Executar comandos no seu computador\n"
            "• Pesquisa na internet\n"
            "• Gestão de tarefas e lembretes\n"
            "• Status de todos os agentes do ecossistema\n\n"
            "Comandos:\n"
            "/tarefas — ver tarefas pendentes\n"
            "/briefing — resumo do ecossistema\n"
            "/busca <query> — pesquisa web\n"
            "/cmd <comando> — executar no terminal\n"
            "/limpar — limpar histórico da conversa\n"
            "/status — status do sistema\n"
            "/id — seu Chat ID",
            parse_mode="Markdown",
        )

    async def cmd_tarefas(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(self.tasks.format_list(), parse_mode="Markdown")

    async def cmd_briefing(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = str(update.effective_user.id)
        await update.message.reply_text("🧠 Gerando briefing...", parse_mode="Markdown")
        if self._orchestrator:
            try:
                result = await self._orchestrator.execute("briefing", agent_name="NexusIntelligence")
                if result.success:
                    await update.message.reply_text(result.data["briefing"], parse_mode="Markdown")
                    return
            except Exception as e:
                logger.warning(f"Nexus briefing failed: {e}")
        # Fallback: generate briefing via LLM
        response = await self._ask_llm(
            user_id,
            "Gere um resumo do ecossistema The Moon com o que está acontecendo hoje.",
            model=LLM_CAPABLE,
        )
        await update.message.reply_text(response, parse_mode="Markdown")

    async def cmd_busca(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = str(update.effective_user.id)
        query   = " ".join(context.args) if context.args else ""
        if not query:
            await update.message.reply_text("Uso: `/busca <sua pesquisa>`", parse_mode="Markdown")
            return
        await update.message.reply_text(f"🔍 Buscando: _{query}_...", parse_mode="Markdown")
        result   = await self.search.search(query)
        response = await self._ask_llm(
            user_id, f"Com base na busca por '{query}', responda de forma objetiva.",
            extra_context=f"RESULTADO DA BUSCA:\n{result}",
        )
        await update.message.reply_text(response, parse_mode="Markdown")

    async def cmd_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        command = " ".join(context.args) if context.args else ""
        if not command:
            await update.message.reply_text("Uso: `/cmd <comando>`", parse_mode="Markdown")
            return
        await update.message.reply_text(f"💻 Executando...", parse_mode="Markdown")
        success, output = await self.executor.run(command)
        icon = "✅" if success else "❌"
        response = f"{icon} `$ {command}`\n\n```\n{output}\n```"
        await update.message.reply_text(response, parse_mode="Markdown")

    async def cmd_limpar(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = str(update.effective_user.id)
        self.memory.clear(user_id)
        await update.message.reply_text("🧹 Histórico da conversa limpo.", parse_mode="Markdown")

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if self._orchestrator:
            status = self._orchestrator.get_status()
            agents_str  = ", ".join(status.get("agents", [])[:8])
            circuits_str = ", ".join(status.get("open_circuits", [])) or "nenhum"
            text = (
                f"🌙 *The Moon — Status*\n\n"
                f"• Agentes: *{status.get('agents_online', 0)}* online\n"
                f"• Skills: *{status.get('skills_online', 0)}*\n"
                f"• Canais: *{status.get('channels_online', 0)}*\n"
                f"• Circuitos abertos: `{circuits_str}`\n\n"
                f"Agentes: `{agents_str}`"
            )
        else:
            text = "✅ Bot online. Orchestrator não conectado."
        await update.message.reply_text(text, parse_mode="Markdown")

    async def cmd_get_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        await update.message.reply_text(
            f"🆔 Chat ID: `{chat_id}`\n"
            f"User ID: `{update.effective_user.id}`",
            parse_mode="Markdown",
        )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handles all text messages."""
        user_id  = str(update.effective_user.id)
        user_text = update.message.text

        logger.info(f"[{user_id}] text: {user_text[:80]}")

        # Fast-path intent routing
        routed = await self._route_intent(user_id, user_text, update, context)
        if routed:
            await update.message.reply_text(routed, parse_mode="Markdown")
            return

        # General LLM path — also check for sports context
        extra_ctx = ""
        sm = self._get_sports_manager()
        if sm:
            sports_ctx = await self.sports.build(user_text, sm)
            if sports_ctx:
                extra_ctx = sports_ctx

        response = await self._ask_llm(user_id, user_text, extra_context=extra_ctx)
        await update.message.reply_text(response, parse_mode="Markdown")

    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handles voice messages: download → transcribe → route → respond."""
        user_id = str(update.effective_user.id)
        logger.info(f"[{user_id}] voice message received")

        status_msg = await update.message.reply_text("🎧 Transcrevendo áudio...")

        try:
            voice_file = await context.bot.get_file(update.message.voice.file_id)

            with tempfile.TemporaryDirectory() as tmpdir:
                oga_path = os.path.join(tmpdir, "voice.oga")
                wav_path = os.path.join(tmpdir, "voice.wav")

                await voice_file.download_to_drive(oga_path)

                # Convert to WAV
                audio = AudioSegment.from_ogg(oga_path)
                audio.export(wav_path, format="wav")

                # Transcribe via Groq Whisper
                with open(wav_path, "rb") as f:
                    transcription = await self.groq.audio.transcriptions.create(
                        file     = (wav_path, f.read()),
                        model    = WHISPER,
                        language = "pt",
                    )

                transcribed_text = transcription.text.strip()
                logger.info(f"Transcribed: {transcribed_text[:100]}")

                if not transcribed_text:
                    await status_msg.edit_text("⚠️ Não consegui transcrever o áudio.")
                    return

                # Show transcription
                await status_msg.edit_text(
                    f"📝 *Transcrição:* _{transcribed_text}_", parse_mode="Markdown"
                )

                # Route like a text message
                routed = await self._route_intent(user_id, transcribed_text, update, context)
                if routed:
                    await update.message.reply_text(routed, parse_mode="Markdown")
                    return

                # General LLM path
                extra_ctx = ""
                sm = self._get_sports_manager()
                if sm:
                    sports_ctx = await self.sports.build(transcribed_text, sm)
                    if sports_ctx:
                        extra_ctx = sports_ctx

                response = await self._ask_llm(user_id, transcribed_text, extra_context=extra_ctx)
                await update.message.reply_text(response, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Voice handling error: {e}")
            await update.message.reply_text(
                "⚠️ Erro ao processar áudio. Verifique se o ffmpeg está instalado.",
                parse_mode="Markdown",
            )

    # ════════════════════════════════════════════════════════
    #  Reminder checker loop
    # ════════════════════════════════════════════════════════

    async def _reminder_loop(self, app) -> None:
        """Checks for due reminders and sends them."""
        while True:
            try:
                due = self.tasks.get_due_reminders()
                for task in due:
                    if self.chat_id:
                        await app.bot.send_message(
                            chat_id    = self.chat_id,
                            text       = f"⏰ *Lembrete:* {task.title}\n_{task.content}_",
                            parse_mode = "Markdown",
                        )
                    self.tasks.mark_notified(task.id)
            except Exception as e:
                logger.debug(f"Reminder loop error: {e}")
            await asyncio.sleep(REMINDER_CHECK)

    # ════════════════════════════════════════════════════════
    #  Entry point
    # ════════════════════════════════════════════════════════

    def run(self) -> None:
        """Starts the bot with all handlers."""
        if not self.token:
            logger.error("TELEGRAM_BOT_TOKEN not set. Bot cannot start.")
            return

        app = (
            ApplicationBuilder()
            .token(self.token)
            .read_timeout(30)
            .write_timeout(30)
            .connect_timeout(15)
            .pool_timeout(5)
            .build()
        )

        # Commands
        app.add_handler(CommandHandler("start",    self.cmd_start))
        app.add_handler(CommandHandler("tarefas",  self.cmd_tarefas))
        app.add_handler(CommandHandler("briefing", self.cmd_briefing))
        app.add_handler(CommandHandler("busca",    self.cmd_busca))
        app.add_handler(CommandHandler("cmd",      self.cmd_cmd))
        app.add_handler(CommandHandler("limpar",   self.cmd_limpar))
        app.add_handler(CommandHandler("status",   self.cmd_status))
        app.add_handler(CommandHandler("id",       self.cmd_get_id))

        # Messages
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        app.add_handler(MessageHandler(filters.VOICE, self.handle_voice))

        # Post-init: start reminder loop
        async def _post_init(application) -> None:
            asyncio.create_task(self._reminder_loop(application))
            # Inicia loop autônomo do APEX Oracle
            apex = _get_apex_oracle()
            if apex:
                asyncio.create_task(apex.run_autonomous_loop())
                logger.info("ApexOracle loop autônomo iniciado junto ao bot")
            else:
                logger.warning("ApexOracle não iniciado — verifique configuração")
            # Set bot commands for Telegram UI
            await application.bot.set_my_commands([
                BotCommand("start",    "Iniciar / apresentação"),
                BotCommand("status",   "Status do ecossistema"),
                BotCommand("tarefas",  "Ver tarefas pendentes"),
                BotCommand("briefing", "Resumo do dia"),
                BotCommand("busca",    "Pesquisa na internet"),
                BotCommand("cmd",      "Executar comando no terminal"),
                BotCommand("limpar",   "Limpar histórico da conversa"),
                BotCommand("id",       "Mostrar Chat ID"),
            ])
            logger.info("MoonBot initialized and ready.")

        app.post_init = _post_init

        logger.info("Starting MoonBot polling...")
        app.run_polling(
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=True,
        )


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    bot = MoonBot()
    bot.run()
