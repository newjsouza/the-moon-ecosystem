"""
agents/browser_pilot.py
BrowserPilot — Agente de Navegação Interativa com Pausa para Dados Sensíveis.

CAPACIDADES:
  1. Recebe instrução em linguagem natural via Telegram
     Ex: "acesse rapidapi.com, crie conta e assine a API-Football gratuita"

  2. LLM converte instrução → plano de steps sequenciais (JSON)
     Ex: [goto, click, fill_pause, click, screenshot, ...]

  3. Executa cada step via BrowserBridge (daemon Playwright real)

  4. Ao encontrar step "fill_sensitive" → PAUSA → envia screenshot + prompt
     para o Telegram → aguarda resposta do usuário → continua a navegação

  5. Envia screenshot de confirmação após cada etapa importante

  6. Bot Telegram recebe /browser <instrução> para iniciar sessão
     e responde mensagens de texto durante pausas ativas

COMANDOS SUPERTADOS (via BrowserBridge):
  goto, click, fill, press, scroll, hover, type,
  screenshot, text, links, snapshot, tabs, newtab

ASSINATURA IMUTÁVEL (Moon Codex):
  async def _execute(self, task: str, **kwargs) -> TaskResult
  TaskResult(success, data=None, error=None, execution_time=0.0)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import uuid

from groq import AsyncGroq

# Importar as classes de estado do navegador
from core.browser_state import BrowserSession, BrowserAction, PageSnapshot

logger = logging.getLogger("moon.browser_pilot")

ROOT_DIR  = Path(__file__).resolve().parent.parent
DATA_DIR  = ROOT_DIR / "data" / "browser_pilot"
DATA_DIR.mkdir(parents=True, exist_ok=True)

GROQ_API_KEY       = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL         = "llama-3.3-70b-versatile"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

# Timeout de espera por input sensível do usuário (10 minutos)
SENSITIVE_INPUT_TIMEOUT = 600

# Palavras-chave que indicam campo sensível no seletor/label
SENSITIVE_KEYWORDS = [
    "password", "senha", "secret", "token", "otp", "pin",
    "card", "cartão", "cvv", "cpf", "ssn", "credit",
    "private", "segredo",
]


# ─────────────────────────────────────────────────────────────
#  Step definitions — plano de navegação
# ─────────────────────────────────────────────────────────────

@dataclass
class BrowserStep:
    """Um passo do plano de navegação gerado pelo LLM."""
    action:      str                    # goto | click | fill | fill_sensitive | press |
                                        # scroll | screenshot | wait | assert_text |
                                        # select | check | hover | newtab | closetab
    selector:    Optional[str] = None   # CSS selector ou texto visível
    value:       Optional[str] = None   # URL (goto) | texto (fill) | key (press)
    description: str = ""               # descrição humana do step
    sensitive:   bool = False           # True = pausar e pedir ao usuário
    label:       str = ""               # label do campo sensível (ex: "Senha")
    optional:    bool = False           # True = ignorar erro e continuar

    @classmethod
    def from_dict(cls, d: dict) -> "BrowserStep":
        return cls(
            action      = d.get("action", ""),
            selector    = d.get("selector"),
            value       = d.get("value"),
            description = d.get("description", ""),
            sensitive   = d.get("sensitive", False) or
                          any(k in (d.get("label", "") + d.get("selector", "")).lower()
                              for k in SENSITIVE_KEYWORDS),
            label       = d.get("label", d.get("selector", "campo")),
            optional    = d.get("optional", False),
        )


@dataclass
class PilotSession:
    """Estado de uma sessão de navegação em andamento."""
    session_id:     str
    task:           str
    steps:          List[BrowserStep]
    current_step:   int = 0
    status:         str = "running"     # running | waiting_input | done | error
    pending_input:  Optional[asyncio.Future] = field(default=None, repr=False)
    history:        List[dict] = field(default_factory=list)
    started_at:     float = field(default_factory=time.time)
    last_screenshot: Optional[bytes] = None


# ─────────────────────────────────────────────────────────────
#  Telegram notifier (direto, sem depender do bot.py)
# ─────────────────────────────────────────────────────────────

class PilotNotifier:
    """Envia mensagens e screenshots ao Telegram durante a sessão."""

    def __init__(self) -> None:
        self.token   = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.base    = f"https://api.telegram.org/bot{self.token}"

    async def send_text(self, text: str) -> bool:
        if not self.token or not self.chat_id:
            return False
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self.base}/sendMessage",
                    json={
                        "chat_id":    self.chat_id,
                        "text":       text[:4000],
                        "parse_mode": "Markdown",
                    }
                )
                return resp.status_code == 200
        except Exception as e:
            logger.error(f"PilotNotifier send_text erro: {e}")
            return False

    async def send_photo(self, image_bytes: bytes, caption: str = "") -> bool:
        if not self.token or not self.chat_id:
            return False
        try:
            import httpx
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{self.base}/sendPhoto",
                    data={
                        "chat_id": self.chat_id,
                        "caption": caption[:1000],
                        "parse_mode": "Markdown",
                    },
                    files={"photo": ("screenshot.png", image_bytes, "image/png")},
                )
                return resp.status_code == 200
        except Exception as e:
            logger.error(f"PilotNotifier send_photo erro: {e}")
            return False

    async def request_sensitive_input(
        self, label: str, step_desc: str, screenshot: Optional[bytes]
    ) -> None:
        """Envia screenshot + instrução para o usuário inserir dado sensível."""
        msg = (
            f"🔐 *BrowserPilot — Entrada Necessária*\n\n"
            f"📋 Etapa: _{step_desc}_\n\n"
            f"✏️ Por favor, envie o valor para: *{label}*\n\n"
            f"_⚠️ Não armazenarei este dado. Ele será usado uma vez e descartado._\n"
            f"_Digite /cancelar_browser para cancelar a sessão._"
        )
        if screenshot:
            await self.send_photo(screenshot, caption=msg)
        else:
            await self.send_text(msg)

    async def notify_step(self, step: BrowserStep, step_num: int, total: int) -> None:
        await self.send_text(
            f"🌐 *BrowserPilot* [{step_num}/{total}]\n"
            f"▶️ _{step.description or step.action}_"
        )

    async def notify_done(self, task: str, screenshot: Optional[bytes]) -> None:
        msg = f"✅ *BrowserPilot — Concluído!*\n\n_{task}_"
        if screenshot:
            await self.send_photo(screenshot, caption=msg)
        else:
            await self.send_text(msg)

    async def notify_error(self, error: str, screenshot: Optional[bytes]) -> None:
        msg = f"❌ *BrowserPilot — Erro*\n\n`{error[:300]}`"
        if screenshot:
            await self.send_photo(screenshot, caption=msg)
        else:
            await self.send_text(msg)


# ─────────────────────────────────────────────────────────────
#  Plan Generator — LLM converte instrução → steps JSON
# ─────────────────────────────────────────────────────────────

class PlanGenerator:
    """Usa Groq LLM para converter instrução em plano de steps."""

    def __init__(self) -> None:
        self.client = AsyncGroq(api_key=GROQ_API_KEY)

    async def generate(self, task: str) -> List[BrowserStep]:
        system = """Você é um especialista em automação de navegadores.
Converta a instrução do usuário em um plano de steps JSON para o Playwright.

REGRAS:
- Retorne APENAS JSON válido, array de steps
- Campos disponíveis por step: action, selector, value, description, label, sensitive, optional
- Para campos de senha/dados sensíveis: use action="fill_sensitive" e sensitive=true
- Seletores: prefira texto visível ('text=Login') antes de CSS complexo
- Sempre inclua screenshots após ações importantes
- Seja conservador: inclua waits após cliques em botões que carregam páginas

ACTIONS DISPONÍVEIS:
  goto         → value=URL
  click        → selector=CSS_ou_texto
  fill         → selector=campo, value=texto_a_preencher
  fill_sensitive → selector=campo, label=nome_legível, sensitive=true (SEM value)
  press        → selector=campo, value=tecla (Enter, Tab, Escape)
  scroll       → value="down" | "up" | "bottom"
  screenshot   → sem parâmetros extras
  wait         → value=segundos (string)
  assert_text  → value=texto_esperado_na_página
  select       → selector=dropdown, value=opção
  check        → selector=checkbox
  hover        → selector=elemento
  newtab       → value=URL
  closetab     → sem parâmetros

EXEMPLO de output para "Faça login no GitHub":
[
  {"action": "goto", "value": "https://github.com/login", "description": "Abre página de login do GitHub"},
  {"action": "screenshot", "description": "Captura página de login"},
  {"action": "fill", "selector": "#login_field", "value": "meu_usuario", "description": "Preenche usuário"},
  {"action": "fill_sensitive", "selector": "#password", "label": "Senha do GitHub", "sensitive": true, "description": "Aguarda senha do usuário"},
  {"action": "click", "selector": "input[type=submit]", "description": "Clica em Entrar"},
  {"action": "wait", "value": "2", "description": "Aguarda carregamento"},
  {"action": "screenshot", "description": "Confirma login realizado"}
]"""

        user = f"Instrução: {task}\n\nGere o plano de steps JSON:"

        try:
            completion = await self.client.chat.completions.create(
                model       = GROQ_MODEL,
                messages    = [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user},
                ],
                max_tokens  = 2048,
                temperature = 0.2,
            )
            raw = completion.choices[0].message.content.strip()

            # Remove possível ```json wrapper
            if "```" in raw:
                parts = raw.split("```")
                for part in parts:
                    if part.startswith("json"):
                        raw = part[4:].strip()
                        break
                    elif part.strip().startswith("["):
                        raw = part.strip()
                        break

            steps_data = json.loads(raw)
            steps = [BrowserStep.from_dict(s) for s in steps_data]
            logger.info(f"PlanGenerator: {len(steps)} steps gerados para '{task[:60]}'")
            return steps

        except json.JSONDecodeError as e:
            logger.error(f"PlanGenerator JSON parse erro: {e}")
            return []
        except Exception as e:
            logger.error(f"PlanGenerator erro: {e}")
            return []


# ─────────────────────────────────────────────────────────────
#  BrowserPilot — Orquestrador principal
# ─────────────────────────────────────────────────────────────

class BrowserPilot:
    """
    Agente de navegação interativa com pausa para dados sensíveis.

    Integração com Telegram Bot:
      - bot.py chama pilot.start_session(task, chat_id) para iniciar
      - bot.py chama pilot.provide_sensitive_input(session_id, value)
        quando usuário responde durante uma pausa
      - bot.py chama pilot.cancel_session(session_id) via /cancelar_browser
    """

    def __init__(self) -> None:
        self.planner  = PlanGenerator()
        self.notifier = PilotNotifier()
        self._sessions: Dict[str, PilotSession] = {}
        self._bridge  = None   # lazy init — evita import circular
        # Adicionando o objeto de sessão do navegador
        self._browser_session: BrowserSession | None = None

    def _get_bridge(self):
        """Lazy import do BrowserBridge para evitar import circular."""
        if self._bridge is None:
            try:
                import sys
                if str(ROOT_DIR) not in sys.path:
                    sys.path.insert(0, str(ROOT_DIR))
                from core.browser_bridge import BrowserBridge
                self._bridge = BrowserBridge()
                logger.info("BrowserBridge carregado com sucesso")
            except ImportError as e:
                logger.error(f"BrowserBridge import erro: {e}")
        return self._bridge

    # ════════════════════════════════════════════════════════
    #  Public API — chamada pelo bot.py
    # ════════════════════════════════════════════════════════

    async def start_session(self, task: str) -> str:
        """
        Inicia nova sessão de navegação.
        Retorna session_id para acompanhamento.
        """
        session_id = f"pilot_{int(time.time())}"
        logger.info(f"BrowserPilot: iniciando sessão {session_id} — '{task[:80]}'")

        await self.notifier.send_text(
            f"🚀 *BrowserPilot iniciado*\n\n"
            f"📋 Tarefa: _{task}_\n\n"
            f"_Gerando plano de navegação..._"
        )

        # Gera plano via LLM
        steps = await self.planner.generate(task)

        if not steps:
            await self.notifier.send_text(
                "❌ *BrowserPilot*: Não consegui gerar um plano para esta tarefa.\n"
                "Tente reformular a instrução com mais detalhes."
            )
            return session_id

        session = PilotSession(
            session_id = session_id,
            task       = task,
            steps      = steps,
        )
        self._sessions[session_id] = session

        # Informa plano ao usuário
        plan_lines = [f"📋 *Plano de navegação ({len(steps)} steps):*\n"]
        for i, s in enumerate(steps, 1):
            icon = "🔐" if s.sensitive else "▶️"
            plan_lines.append(f"{icon} {i}. {s.description or s.action}")
        await self.notifier.send_text("\n".join(plan_lines))

        # Executa em background
        asyncio.create_task(self._execute_session(session_id))
        return session_id

    async def provide_sensitive_input(self, session_id: str, value: str) -> bool:
        """
        Recebe dado sensível do usuário e desbloqueia a sessão.
        Chamado pelo bot.py quando usuário responde durante pausa.
        value NÃO é armazenado — usado apenas para preencher o campo e descartado.
        """
        session = self._sessions.get(session_id)
        if not session or session.status != "waiting_input":
            return False
        if session.pending_input and not session.pending_input.done():
            session.pending_input.set_result(value)
            return True
        return False

    async def cancel_session(self, session_id: str) -> bool:
        """Cancela sessão em andamento."""
        session = self._sessions.get(session_id)
        if not session:
            return False
        session.status = "error"
        if session.pending_input and not session.pending_input.done():
            session.pending_input.cancel()
        await self.notifier.send_text("⏹️ *BrowserPilot*: Sessão cancelada.")
        return True

    def get_active_session(self) -> Optional[PilotSession]:
        """Retorna a sessão ativa mais recente (status=waiting_input ou running)."""
        active = [
            s for s in self._sessions.values()
            if s.status in ("running", "waiting_input")
        ]
        return active[0] if active else None

    # ════════════════════════════════════════════════════════
    #  Execution engine
    # ════════════════════════════════════════════════════════

    async def _execute_session(self, session_id: str) -> None:
        """Loop principal de execução dos steps."""
        session = self._sessions[session_id]
        bridge  = self._get_bridge()

        if not bridge:
            await self.notifier.send_text("❌ BrowserBridge não disponível. Verifique o daemon.")
            session.status = "error"
            return

        # Garante daemon rodando
        try:
            await bridge.ensure_running()
        except Exception as e:
            await self.notifier.send_text(f"❌ Não foi possível iniciar o browser daemon: `{e}`")
            session.status = "error"
            return

        total = len(session.steps)

        for i, step in enumerate(session.steps):
            if session.status == "error":
                break

            session.current_step = i
            logger.info(f"[{session_id}] Step {i+1}/{total}: {step.action} — {step.description}")

            try:
                await self._execute_step(session, step, i + 1, total, bridge)
            except asyncio.CancelledError:
                session.status = "error"
                break
            except Exception as e:
                logger.error(f"[{session_id}] Step {i+1} erro: {e}")
                if not step.optional:
                    screenshot = await self._take_screenshot(bridge)
                    await self.notifier.notify_error(
                        f"Step {i+1} ({step.action}): {e}", screenshot
                    )
                    session.status = "error"
                    break
                # Step opcional: loga e continua
                logger.warning(f"[{session_id}] Step opcional {i+1} falhou, continuando")

        if session.status != "error":
            session.status = "done"
            screenshot = await self._take_screenshot(bridge)
            await self.notifier.notify_done(session.task, screenshot)
            logger.info(f"[{session_id}] Sessão concluída com sucesso")

    async def _execute_step(
        self,
        session: PilotSession,
        step:    BrowserStep,
        step_num: int,
        total:   int,
        bridge,
    ) -> None:
        """Executa um step individual."""

        # Para steps importantes, notifica o usuário
        important_actions = {"goto", "click", "fill_sensitive", "screenshot"}
        if step.action in important_actions or step_num % 5 == 0:
            await self.notifier.notify_step(step, step_num, total)

        action = step.action

        # ── GOTO ──────────────────────────────────────────
        if action == "goto":
            await bridge.goto(step.value)
            await asyncio.sleep(1.5)  # espera carregamento

        # ── CLICK ─────────────────────────────────────────
        elif action == "click":
            await bridge.click(step.selector)
            await asyncio.sleep(0.8)

        # ── FILL (normal) ──────────────────────────────────
        elif action == "fill":
            await bridge.fill(step.selector, step.value or "")

        # ── FILL SENSITIVE — pausa para o usuário ──────────
        elif action == "fill_sensitive" or step.sensitive:
            screenshot = await self._take_screenshot(bridge)
            session.last_screenshot = screenshot
            session.status = "waiting_input"

            # Cria Future para aguardar input
            loop   = asyncio.get_event_loop()
            future = loop.create_future()
            session.pending_input = future

            await self.notifier.request_sensitive_input(
                step.label, step.description, screenshot
            )

            # Aguarda input do usuário (timeout = 10 min)
            try:
                sensitive_value = await asyncio.wait_for(
                    asyncio.shield(future),
                    timeout = SENSITIVE_INPUT_TIMEOUT,
                )
            except asyncio.TimeoutError:
                await self.notifier.send_text(
                    f"⏱️ *BrowserPilot*: Timeout aguardando `{step.label}`.\n"
                    f"Sessão cancelada por inatividade."
                )
                session.status = "error"
                return

            session.status = "running"
            session.pending_input = None

            # Preenche o campo — valor usado AQUI e descartado
            await bridge.fill(step.selector, sensitive_value)
            del sensitive_value  # descarta imediatamente

            await self.notifier.send_text(
                f"✅ _Campo `{step.label}` preenchido. Continuando..._"
            )

        # ── PRESS ─────────────────────────────────────────
        elif action == "press":
            await bridge.press(step.selector or "body", step.value or "Enter")

        # ── SCREENSHOT ────────────────────────────────────
        elif action == "screenshot":
            screenshot = await self._take_screenshot(bridge)
            if screenshot:
                caption = f"📸 _{step.description or 'Screenshot'}_"
                await self.notifier.send_photo(screenshot, caption)

        # ── WAIT ──────────────────────────────────────────
        elif action == "wait":
            secs = float(step.value or "1")
            await asyncio.sleep(min(secs, 30))  # máximo 30s de wait

        # ── ASSERT TEXT ───────────────────────────────────
        elif action == "assert_text":
            page_text = await bridge.text()
            if step.value and step.value.lower() not in page_text.lower():
                raise AssertionError(
                    f"Texto esperado não encontrado: '{step.value}'"
                )

        # ── TEXT ──────────────────────────────────────────
        elif action == "text":
            await bridge.text()

        # ── HOVER ─────────────────────────────────────────
        elif action == "hover":
            await bridge.command("hover", selector=step.selector)

        # ── SCROLL ────────────────────────────────────────
        elif action == "scroll":
            direction = step.value or "down"
            await bridge.command("scroll", value=direction)

        # ── SELECT ────────────────────────────────────────
        elif action == "select":
            await bridge.command("select", selector=step.selector, value=step.value)

        # ── CHECK ─────────────────────────────────────────
        elif action == "check":
            await bridge.command("check", selector=step.selector)

        # ── NEWTAB ────────────────────────────────────────
        elif action == "newtab":
            await bridge.command("newtab", value=step.value)
            await asyncio.sleep(1.5)

        # ── CLOSETAB ──────────────────────────────────────
        elif action == "closetab":
            await bridge.command("closetab")

        else:
            logger.warning(f"BrowserPilot: action desconhecida '{action}', ignorando")

        # Log do step no histórico da sessão
        session.history.append({
            "step":   step_num,
            "action": action,
            "desc":   step.description,
            "ts":     datetime.now().isoformat(),
            "ok":     True,
        })

    async def _take_screenshot(self, bridge) -> Optional[bytes]:
        """Captura screenshot silenciosamente, retorna bytes ou None."""
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                temp_path = f.name
            
            result = await bridge.screenshot(temp_path)
            
            # Lê o arquivo e retorna bytes
            with open(temp_path, "rb") as f:
                image_bytes = f.read()
            
            # Limpa arquivo temporário
            try:
                os.unlink(temp_path)
            except:
                pass
            
            return image_bytes
        except Exception as e:
            logger.debug(f"Screenshot falhou: {e}")
            return None

    def _start_session(self, session_id: str = None) -> BrowserSession:
        """Inicia uma nova sessão de navegação estruturada."""
        sid = session_id or str(uuid.uuid4())[:8]
        self._browser_session = BrowserSession(session_id=sid, actions=[], snapshots=[])
        return self._browser_session

    def _record_action(self, action_type: str, target_ref: str = None, value: str = None) -> None:
        """Registra uma ação na sessão de navegação."""
        if self._browser_session:
            self._browser_session.add_action(BrowserAction(
                action_type=action_type, target_ref=target_ref,
                value=value, timestamp=time.time()
            ))

    def _record_snapshot(self, url: str, title: str, raw_text: str = "", elements: list = None) -> None:
        """Registra um snapshot da página na sessão de navegação."""
        if self._browser_session:
            self._browser_session.add_snapshot(PageSnapshot(
                url=url, title=title, timestamp=time.time(),
                elements=elements or [], raw_text=raw_text
            ))

    def get_replay_log(self) -> list:
        """Obtém o log de replay auditável das ações realizadas."""
        if self._browser_session:
            return self._browser_session.replay_log()
        return []

    def get_session_dict(self) -> dict:
        """Obtém a representação dicionário da sessão atual."""
        if self._browser_session:
            return self._browser_session.to_dict()
        return {}
        