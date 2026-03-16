"""
core/browser_bridge.py
Browser Bridge — Client HTTP assíncrono Python → daemon gstack (TypeScript/Bun)

Architecture:
  - Lê .gstack/browse.json para obter port e token do daemon
  - Inicia o daemon automaticamente via subprocess se necessário
  - Faz requisições HTTP POST para http://localhost:{port}/command
  - Todas as exceções são capturadas e retornam "BROWSER_ERROR: {msg}"
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger("moon.core.browser_bridge")


class BrowserBridge:
    """
    Client HTTP assíncrono para o daemon Playwright do gstack.
    
    Uso:
        bridge = BrowserBridge()
        await bridge.goto("https://example.com")
        snap = await bridge.snapshot()
        await bridge.screenshot("/tmp/screen.png")
    """
    
    def __init__(self, project_root: Optional[str] = None):
        """
        Inicializa a BrowserBridge.
        
        Args:
            project_root: Raiz do projeto The Moon. Se None, usa o diretório
                         pai do arquivo browser_bridge.py.
        """
        if project_root:
            self._project_root = Path(project_root)
        else:
            # Diretório raiz do projeto (2 níveis acima deste arquivo)
            self._project_root = Path(__file__).resolve().parent.parent
        
        self._gstack_dir = self._project_root / ".gstack"
        self._state_file = self._gstack_dir / "browse.json"
        self._daemon_script = self._project_root / "skills" / "moon_browse" / "start_daemon.sh"
        
        self._port: Optional[int] = None
        self._token: Optional[str] = None
        self._pid: Optional[int] = None
        self._client: Optional[httpx.AsyncClient] = None
        self._daemon_process: Optional[subprocess.Popen] = None
        self._base_url: str = ""
        
        logger.info(f"BrowserBridge initialized. Project root: {self._project_root}")
    
    async def ensure_running(self) -> bool:
        """
        Garante que o daemon está rodando.
        
        Returns:
            True se o daemon está rodando (ou foi iniciado), False se falhou.
        """
        # Verifica se já temos conexão válida
        if self._client and self._port and self._token:
            if self._pid and self._is_process_alive(self._pid):
                return True
            # PID morreu, limpar estado
            self._cleanup()
        
        # Tenta ler o estado do arquivo
        state = self._read_state_file()
        
        if state:
            self._port = state.get("port")
            self._token = state.get("token")
            self._pid = state.get("pid")
            
            # Verifica se o PID está vivo
            if self._pid and self._is_process_alive(self._pid):
                self._setup_client()
                logger.info(f"Connected to existing daemon on port {self._port}")
                return True
            else:
                logger.warning(f"Daemon PID {self._pid} not alive, will restart")
                self._cleanup()
        
        # Inicia o daemon
        return await self._start_daemon()
    
    def _is_process_alive(self, pid: int) -> bool:
        """Verifica se um processo está vivo."""
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False
    
    def _read_state_file(self) -> Optional[Dict[str, Any]]:
        """Lê o arquivo de estado .gstack/browse.json."""
        try:
            if not self._state_file.exists():
                return None
            
            with open(self._state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
            
            logger.debug(f"Read state file: port={state.get('port')}, pid={state.get('pid')}")
            return state
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to read state file: {e}")
            return None
    
    def _cleanup(self) -> None:
        """Limpa o estado da conexão."""
        self._port = None
        self._token = None
        self._pid = None
        self._base_url = ""
        if self._client:
            asyncio.create_task(self._client.aclose())
            self._client = None
    
    def _setup_client(self) -> None:
        """Configura o client HTTP com o token de autenticação."""
        if not self._port or not self._token:
            raise RuntimeError("Port and token not set")
        
        self._base_url = f"http://127.0.0.1:{self._port}"
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=30.0,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            }
        )
        logger.debug(f"HTTP client setup for {self._base_url}")
    
    async def _start_daemon(self) -> bool:
        """
        Inicia o daemon do browser.
        
        Returns:
            True se iniciou com sucesso, False caso contrário.
        """
        logger.info("Starting browser daemon...")
        
        if not self._daemon_script.exists():
            logger.error(f"Daemon script not found: {self._daemon_script}")
            return False
        
        try:
            # Inicia o daemon em background
            env = os.environ.copy()
            env["BROWSE_STATE_FILE"] = str(self._state_file)
            
            self._daemon_process = subprocess.Popen(
                ["bash", str(self._daemon_script)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=str(self._daemon_script.parent),
                env=env,
                start_new_session=True,  # Desacopla do processo pai
            )
            
            logger.info(f"Daemon started with PID {self._daemon_process.pid}")
            
            # Aguarda o arquivo de estado aparecer (até 10 segundos)
            for attempt in range(20):  # 20 * 0.5s = 10s
                await asyncio.sleep(0.5)
                state = self._read_state_file()
                
                if state:
                    self._port = state.get("port")
                    self._token = state.get("token")
                    self._pid = state.get("pid")
                    self._setup_client()
                    logger.info(f"Daemon ready on port {self._port}")
                    return True
            
            logger.error("Daemon did not start within timeout")
            return False
            
        except Exception as e:
            logger.error(f"Failed to start daemon: {e}")
            return False
    
    async def _request(self, command: str, args: Optional[list] = None) -> str:
        """
        Faz uma requisição POST para o daemon.
        
        Args:
            command: Nome do comando (goto, snapshot, etc.)
            args: Lista de argumentos do comando
        
        Returns:
            Resposta do daemon ou string de erro.
        """
        if not await self.ensure_running():
            return "BROWSER_ERROR: Daemon not running"
        
        if not self._client:
            return "BROWSER_ERROR: Client not initialized"
        
        try:
            body = {"command": command, "args": args or []}
            
            response = await self._client.post("/command", json=body)
            
            if response.status_code == 401:
                self._cleanup()
                return "BROWSER_ERROR: Unauthorized (token expired)"
            
            if response.status_code == 500:
                error_data = response.json()
                return f"BROWSER_ERROR: {error_data.get('error', 'Unknown error')}"
            
            # Resposta em texto plano
            return response.text
            
        except httpx.TimeoutException:
            logger.warning(f"Timeout executing command: {command}")
            return f"BROWSER_ERROR: Timeout executing {command}"
        except httpx.ConnectError as e:
            logger.warning(f"Connection error: {e}")
            self._cleanup()
            return f"BROWSER_ERROR: Connection failed ({e})"
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return f"BROWSER_ERROR: {str(e)}"
    
    # ─────────────────────────────────────────────────────────────
    #  Comandos públicos
    # ─────────────────────────────────────────────────────────────
    
    async def goto(self, url: str) -> str:
        """
        Navega para uma URL.
        
        Args:
            url: URL para navegar
        
        Returns:
            Mensagem de confirmação ou erro.
        """
        return await self._request("goto", [url])
    
    async def snapshot(self, interactive: bool = True) -> str:
        """
        Captura a árvore de acessibilidade da página com refs.
        
        Args:
            interactive: Se True, usa flag -i para elementos interativos apenas.
        
        Returns:
            Árvore de acessibilidade com refs (@e1, @e2, etc.) ou erro.
        """
        args = ["-i"] if interactive else []
        return await self._request("snapshot", args)
    
    async def screenshot(self, path: str) -> str:
        """
        Tira um screenshot da página.
        
        Args:
            path: Caminho para salvar o screenshot.
        
        Returns:
            Mensagem de confirmação ou erro.
        """
        return await self._request("screenshot", [path])
    
    async def click(self, ref: str) -> str:
        """
        Clica em um elemento (por ref @e1 ou seletor CSS).
        
        Args:
            ref: Referência do elemento (@e1, @e2, etc.) ou seletor CSS.
        
        Returns:
            Mensagem de confirmação ou erro.
        """
        return await self._request("click", [ref])
    
    async def fill(self, ref: str, value: str) -> str:
        """
        Preenche um campo de input.
        
        Args:
            ref: Referência do elemento ou seletor CSS.
            value: Valor para preencher.
        
        Returns:
            Mensagem de confirmação ou erro.
        """
        return await self._request("fill", [ref, value])
    
    async def press(self, ref: str, key: str) -> str:
        """
        Pressiona uma tecla.
        
        Args:
            ref: Referência do elemento ou seletor CSS.
            key: Tecla para pressionar (Enter, Tab, Escape, etc.)
        
        Returns:
            Mensagem de confirmação ou erro.
        """
        return await self._request("press", [key])
    
    async def text(self) -> str:
        """
        Obtém o texto limpo da página.
        
        Returns:
            Texto da página ou erro.
        """
        return await self._request("text", [])
    
    async def html(self) -> str:
        """
        Obtém o HTML da página.
        
        Returns:
            HTML da página ou erro.
        """
        return await self._request("html", [])
    
    async def console(self, limit: int = 20) -> str:
        """
        Obtém mensagens do console do browser.
        
        Args:
            limit: Número máximo de mensagens para retornar.
        
        Returns:
            Mensagens do console ou erro.
        """
        return await self._request("console", [])
    
    async def links(self) -> str:
        """
        Obtém todos os links da página.
        
        Returns:
            Lista de links (texto → href) ou erro.
        """
        return await self._request("links", [])
    
    async def stop(self) -> str:
        """
        Para o daemon do browser.
        
        Returns:
            Mensagem de confirmação ou erro.
        """
        result = await self._request("stop", [])
        if self._client:
            await self._client.aclose()
            self._client = None
        return result
    
    async def health_check(self) -> bool:
        """
        Verifica se o daemon está saudável.
        
        Returns:
            True se saudável, False caso contrário.
        """
        if not await self.ensure_running():
            return False
        
        if not self._client:
            return False
        
        try:
            response = await self._client.get("/health")
            data = response.json()
            return data.get("status") == "healthy"
        except Exception:
            return False
    
    async def close(self) -> None:
        """
        Fecha a conexão com o daemon.
        """
        if self._client:
            await self._client.aclose()
            self._client = None
        logger.info("BrowserBridge connection closed")


# ─────────────────────────────────────────────────────────────
#  Context manager
# ─────────────────────────────────────────────────────────────

class BrowserBridgeContext:
    """Context manager para BrowserBridge."""
    
    def __init__(self, project_root: Optional[str] = None):
        self.bridge = BrowserBridge(project_root)
    
    async def __aenter__(self) -> BrowserBridge:
        await self.bridge.ensure_running()
        return self.bridge
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.bridge.close()


# ─────────────────────────────────────────────────────────────
#  Utility functions
# ─────────────────────────────────────────────────────────────

async def quick_goto(url: str, project_root: Optional[str] = None) -> str:
    """
    Função utilitária para navegar rapidamente para uma URL.
    
    Uso:
        result = await quick_goto("https://example.com")
    """
    async with BrowserBridgeContext(project_root) as bridge:
        return await bridge.goto(url)
