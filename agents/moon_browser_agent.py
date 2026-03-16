"""
agents/moon_browser_agent.py
Moon Browser Agent — Wrapper Python do daemon gstack Playwright

Architecture:
  - Encapsula core/browser_bridge.py
  - Expõe comandos como métodos assíncronos nativos
  - Integrado à MessageBus com tópicos browser.*
  - Health check via goto("about:blank")

Commands suportados:
  - goto <url>
  - snapshot [interactive]
  - screenshot <path>
  - click <ref>
  - fill <ref> <value>
  - press <ref> <key>
  - text
  - html
  - console
  - links
  - qa_pass <url> (modo especial para QA)
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional

from core.agent_base import AgentBase, AgentPriority, TaskResult
from core.message_bus import MessageBus
from core.browser_bridge import BrowserBridge

logger = logging.getLogger("moon.agents.browser")


class MoonBrowserAgent(AgentBase):
    """
    Agente de navegação web via daemon Playwright.
    
    Uso via task string:
        await agent.execute("goto https://example.com")
        await agent.execute("snapshot interactive")
        await agent.execute("screenshot /tmp/screen.png")
        await agent.execute("click @e3")
        await agent.execute("fill @e2 valor")
    """
    
    def __init__(self):
        super().__init__()
        self.name = "MoonBrowserAgent"
        self.priority = AgentPriority.MEDIUM
        self.description = "Browser automation via Playwright daemon (gstack)"
        self.bridge: Optional[BrowserBridge] = None
        self._message_bus: Optional[MessageBus] = None
        self._subscriptions_active = False
    
    async def initialize(self) -> None:
        """Inicializa o agente e subscreve na MessageBus."""
        await super().initialize()
        
        self.bridge = BrowserBridge()
        self._message_bus = MessageBus()
        
        # Subscreve para comandos via message bus
        self._message_bus.subscribe("browser.command", self._handle_browser_command)
        self._subscriptions_active = True
        
        logger.info("MoonBrowserAgent initialized")
    
    async def shutdown(self) -> None:
        """Para o agente e limpa recursos."""
        self._subscriptions_active = False
        
        if self.bridge:
            try:
                await self.bridge.close()
            except Exception as e:
                logger.warning(f"Error closing bridge: {e}")
        
        await super().shutdown()
        logger.info("MoonBrowserAgent shut down")
    
    async def _handle_browser_command(self, message) -> None:
        """Handler para comandos recebidos via MessageBus."""
        if not self._subscriptions_active:
            return
        
        task = message.payload.get("task", "") if message.payload else ""
        sender = message.sender
        
        logger.debug(f"Received browser command from {sender}: {task[:50]}...")
        
        result = await self.execute(task)
        
        # Publica resultado
        await self._message_bus.publish(
            sender=self.name,
            topic="browser.result",
            payload={
                "success": result.success,
                "data": result.data,
                "error": result.error,
                "original_task": task,
            },
            target=sender,
        )
    
    async def _execute(self, task: str, **kwargs) -> TaskResult:
        """
        Executa um comando de browser.
        
        Args:
            task: String no formato "COMANDO arg1 arg2"
        
        Returns:
            TaskResult com output do comando.
        """
        if not self.bridge:
            return TaskResult(success=False, error="BrowserBridge not initialized")
        
        start_time = asyncio.get_event_loop().time()
        
        try:
            # Parseia o comando
            parts = task.strip().split(None, 1)
            if not parts:
                return TaskResult(success=False, error="Empty task")
            
            command = parts[0].lower()
            args_str = parts[1] if len(parts) > 1 else ""
            
            # Mapeia para métodos do bridge
            result_str = await self._dispatch_command(command, args_str)
            
            execution_time = asyncio.get_event_loop().time() - start_time
            
            return TaskResult(
                success=True,
                data={
                    "output": result_str,
                    "command": task,
                    "execution_time": execution_time,
                },
            )
            
        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            execution_time = asyncio.get_event_loop().time() - start_time
            return TaskResult(
                success=False,
                error=str(e),
                execution_time=execution_time,
            )
    
    async def _dispatch_command(self, command: str, args_str: str) -> str:
        """
        Despacha o comando para o método correto do bridge.
        
        Args:
            command: Nome do comando
            args_str: Argumentos como string
        
        Returns:
            Resultado do comando.
        """
        # Parseia argumentos
        args = args_str.split() if args_str else []
        
        if command == "goto":
            if not args:
                raise ValueError("Usage: goto <url>")
            return await self.bridge.goto(args[0])
        
        elif command == "snapshot":
            interactive = "interactive" in args_str.lower() or "-i" in args
            return await self.bridge.snapshot(interactive=interactive)
        
        elif command == "screenshot":
            if not args:
                raise ValueError("Usage: screenshot <path>")
            return await self.bridge.screenshot(args[0])
        
        elif command == "click":
            if not args:
                raise ValueError("Usage: click <ref>")
            return await self.bridge.click(args[0])
        
        elif command == "fill":
            if len(args) < 2:
                raise ValueError("Usage: fill <ref> <value>")
            ref = args[0]
            value = " ".join(args[1:])
            return await self.bridge.fill(ref, value)
        
        elif command == "press":
            if len(args) < 2:
                raise ValueError("Usage: press <ref> <key>")
            return await self.bridge.press(args[0], args[1])
        
        elif command == "text":
            return await self.bridge.text()
        
        elif command == "html":
            return await self.bridge.html()
        
        elif command == "console":
            return await self.bridge.console()
        
        elif command == "links":
            return await self.bridge.links()
        
        elif command == "qa_pass":
            # Modo especial para QA: navega, tira screenshot e retorna snapshot
            if not args:
                raise ValueError("Usage: qa_pass <url>")
            url = args[0]
            
            goto_result = await self.bridge.goto(url)
            if "BROWSER_ERROR" in goto_result:
                return goto_result
            
            await asyncio.sleep(1)  # Aguarda página carregar
            
            screenshot_path = f"/tmp/moon_qa_{int(asyncio.get_event_loop().time())}.png"
            screenshot_result = await self.bridge.screenshot(screenshot_path)
            
            snapshot_result = await self.bridge.snapshot(interactive=True)
            
            return f"QA Pass:\n- Navigated: {goto_result}\n- Screenshot: {screenshot_result}\n- Snapshot:\n{snapshot_result}"
        
        elif command == "stop":
            return await self.bridge.stop()
        
        elif command == "health":
            healthy = await self.bridge.health_check()
            return f"Health check: {'healthy' if healthy else 'unhealthy'}"
        
        else:
            raise ValueError(f"Unknown command: {command}. Use: goto, snapshot, screenshot, click, fill, press, text, html, console, links, qa_pass, stop, health")
    
    # ─────────────────────────────────────────────────────────────
    #  Métodos diretos (para uso programático)
    # ─────────────────────────────────────────────────────────────
    
    async def goto(self, url: str) -> str:
        """Navega para uma URL."""
        if not self.bridge:
            raise RuntimeError("Bridge not initialized")
        return await self.bridge.goto(url)
    
    async def snapshot(self, interactive: bool = True) -> str:
        """Captura árvore de acessibilidade."""
        if not self.bridge:
            raise RuntimeError("Bridge not initialized")
        return await self.bridge.snapshot(interactive=interactive)
    
    async def screenshot(self, path: str) -> str:
        """Tira screenshot."""
        if not self.bridge:
            raise RuntimeError("Bridge not initialized")
        return await self.bridge.screenshot(path)
    
    async def click(self, ref: str) -> str:
        """Clica em elemento."""
        if not self.bridge:
            raise RuntimeError("Bridge not initialized")
        return await self.bridge.click(ref)
    
    async def fill(self, ref: str, value: str) -> str:
        """Preenche input."""
        if not self.bridge:
            raise RuntimeError("Bridge not initialized")
        return await self.bridge.fill(ref, value)
    
    async def get_text(self) -> str:
        """Obtém texto da página."""
        if not self.bridge:
            raise RuntimeError("Bridge not initialized")
        return await self.bridge.text()
    
    async def get_html(self) -> str:
        """Obtém HTML da página."""
        if not self.bridge:
            raise RuntimeError("Bridge not initialized")
        return await self.bridge.html()
    
    async def get_links(self) -> List[Dict[str, str]]:
        """Obtém links da página."""
        if not self.bridge:
            raise RuntimeError("Bridge not initialized")
        links_str = await self.bridge.links()
        
        # Parseia links do formato "texto → href"
        links = []
        for line in links_str.split("\n"):
            if "→" in line:
                parts = line.split("→", 1)
                links.append({
                    "text": parts[0].strip(),
                    "href": parts[1].strip(),
                })
        return links
    
    async def health_check(self) -> bool:
        """
        Health check para o WatchdogAgent.

        Returns:
            True se o browser está saudável.
        """
        if not self.bridge:
            return False

        try:
            # Tenta navegar para about:blank
            result = await self.bridge.goto("about:blank")
            return "BROWSER_ERROR" not in result
        except Exception:
            return False

    async def import_cookies(self, browser: str = "chrome", domain: Optional[str] = None) -> int:
        """
        Importa cookies do browser do sistema (Linux).

        Args:
            browser: Nome do browser (chrome, chromium, brave, edge)
            domain: Filtrar por domínio (opcional)

        Returns:
            Número de cookies importados
        """
        try:
            from core.linux_cookie_importer import LinuxCookieImporter

            importer = LinuxCookieImporter()
            cookies = importer.get_cookies(browser, domain)

            if not cookies:
                logger.warning(f"No cookies found for {browser}")
                return 0

            # Injeta cookies via bridge (comando cookie-import)
            # Nota: O daemon gstack suporta cookie-import via JSON
            logger.info(f"Importing {len(cookies)} cookies from {browser}")

            # Salva cookies em arquivo temp para import
            import json
            import tempfile

            temp_file = tempfile.mktemp(suffix=".json")
            with open(temp_file, "w") as f:
                json.dump(cookies, f)

            # Usa o comando cookie-import do daemon
            if self.bridge:
                result = await self.bridge._request("cookie-import", [temp_file])
                logger.info(f"Cookie import result: {result}")

            # Limpa arquivo temp
            try:
                os.unlink(temp_file)
            except:
                pass

            return len(cookies)

        except Exception as e:
            logger.error(f"Cookie import failed: {e}")
            return 0
    
    async def ping(self) -> bool:
        """Lightweight liveness probe."""
        return self.bridge is not None


# ─────────────────────────────────────────────────────────────
#  Factory function
# ─────────────────────────────────────────────────────────────

def create_browser_agent() -> MoonBrowserAgent:
    """Factory function para criar o agente."""
    return MoonBrowserAgent()
