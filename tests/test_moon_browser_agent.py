"""
tests/test_moon_browser_agent.py
Testes para MoonBrowserAgent e BrowserBridge

Executar:
    python3 -m pytest tests/test_moon_browser_agent.py -v
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Adiciona o diretório raiz ao path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))


# ─────────────────────────────────────────────────────────────
#  Testes: BrowserBridge
# ─────────────────────────────────────────────────────────────

class TestBrowserBridgeReadsStateFile:
    """Testa que BrowserBridge lê o arquivo de estado corretamente."""
    
    def test_bridge_reads_state_file(self, tmp_path):
        """Mock do arquivo .gstack/browse.json, verificar que BrowserBridge lê port e token."""
        from core.browser_bridge import BrowserBridge

        # Cria arquivo de estado mock
        state_file = tmp_path / ".gstack" / "browse.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)

        state_data = {
            "pid": 12345,
            "port": 8080,
            "token": "test-token-123",
        }
        state_file.write_text(json.dumps(state_data))
        
        # Mock para o processo estar vivo
        with patch("core.browser_bridge.os.kill") as mock_kill:
            mock_kill.return_value = None  # Processo vivo
            
            bridge = BrowserBridge(project_root=str(tmp_path))
            state = bridge._read_state_file()
            
            assert state is not None
            assert state["port"] == 8080
            assert state["token"] == "test-token-123"
            assert state["pid"] == 12345


class TestBridgeAutoStartsDaemon:
    """Testa que BrowserBridge inicia o daemon automaticamente."""
    
    @pytest.mark.asyncio
    async def test_bridge_auto_starts_daemon(self, tmp_path):
        """Simular arquivo inexistente, mock de subprocess.Popen."""
        from core.browser_bridge import BrowserBridge

        # Cria script daemon mock
        daemon_script = tmp_path / "skills" / "moon_browse" / "start_daemon.sh"
        daemon_script.parent.mkdir(parents=True, exist_ok=True)
        daemon_script.write_text("#!/bin/bash\necho 'daemon'\n")
        daemon_script.chmod(0o755)
        
        bridge = BrowserBridge(project_root=str(tmp_path))
        
        # Mock do subprocess.Popen
        with patch("core.browser_bridge.subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 99999
            mock_popen.return_value = mock_process
            
            # Mock do _read_state_file para retornar None inicialmente, depois estado
            call_count = [0]
            
            def mock_read():
                call_count[0] += 1
                if call_count[0] > 3:
                    return {
                        "pid": 99999,
                        "port": 9000,
                        "token": "auto-token",
                    }
                return None
            
            with patch.object(bridge, "_read_state_file", side_effect=mock_read):
                with patch("core.browser_bridge.os.kill") as mock_kill:
                    mock_kill.return_value = None
                    
                    result = await bridge.ensure_running()
                    
                    # Verifica que Popen foi chamado
                    assert mock_popen.called
                    # Verifica que o daemon foi iniciado
                    assert call_count[0] > 1


class TestBridgeGoto:
    """Testa o método goto do BrowserBridge."""

    @pytest.mark.asyncio
    async def test_bridge_goto(self):
        """Mock de httpx.AsyncClient.post retornando resposta correta."""
        from core.browser_bridge import BrowserBridge

        bridge = BrowserBridge()
        bridge._port = 8080
        bridge._token = "test-token"
        bridge._pid = 12345
        bridge._base_url = "http://127.0.0.1:8080"

        # Mock do client HTTP
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Navigated to https://example.com"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        bridge._client = mock_client

        # Mock ensure_running para retornar True diretamente
        with patch.object(bridge, 'ensure_running', AsyncMock(return_value=True)):
            result = await bridge._request("goto", ["https://example.com"])

        # Verifica chamada correta
        mock_client.post.assert_called_once_with(
            "/command",
            json={"command": "goto", "args": ["https://example.com"]}
        )

        assert result == "Navigated to https://example.com"
        assert "BROWSER_ERROR" not in result


# ─────────────────────────────────────────────────────────────
#  Testes: MoonBrowserAgent
# ─────────────────────────────────────────────────────────────

class TestAgentExecutesGotoTask:
    """Testa que MoonBrowserAgent executa tarefas goto."""
    
    @pytest.mark.asyncio
    async def test_agent_executes_goto_task(self):
        """Instanciar MoonBrowserAgent com bridge mockada."""
        from agents.moon_browser_agent import MoonBrowserAgent
        
        agent = MoonBrowserAgent()
        
        # Mock do bridge
        mock_bridge = AsyncMock()
        mock_bridge.goto = AsyncMock(return_value="Navigated to https://example.com")
        agent.bridge = mock_bridge
        
        result = await agent._execute("goto https://example.com")
        
        # Verifica TaskResult
        assert result.success is True
        assert result.data is not None
        assert result.data["output"] == "Navigated to https://example.com"
        assert result.data["command"] == "goto https://example.com"
        
        # Verifica que bridge.goto foi chamado
        mock_bridge.goto.assert_called_once_with("https://example.com")


class TestAgentHandlesBrowserError:
    """Testa que MoonBrowserAgent lida com erros do browser."""
    
    @pytest.mark.asyncio
    async def test_agent_handles_browser_error(self):
        """Mock retornando 'BROWSER_ERROR: timeout'."""
        from agents.moon_browser_agent import MoonBrowserAgent
        
        agent = MoonBrowserAgent()
        
        # Mock do bridge com erro
        mock_bridge = AsyncMock()
        mock_bridge.goto = AsyncMock(return_value="BROWSER_ERROR: timeout")
        agent.bridge = mock_bridge
        
        result = await agent._execute("goto https://example.com")
        
        # Verifica que não lançou exceção
        assert result.success is True  # Sucesso na execução, mesmo com erro do browser
        assert result.data is not None
        assert "BROWSER_ERROR" in result.data["output"]


class TestAgentSnapshotCommand:
    """Testa comando snapshot."""
    
    @pytest.mark.asyncio
    async def test_agent_snapshot_interactive(self):
        """Testa snapshot com modo interactive."""
        from agents.moon_browser_agent import MoonBrowserAgent
        
        agent = MoonBrowserAgent()
        
        mock_bridge = AsyncMock()
        mock_bridge.snapshot = AsyncMock(return_value="@e1 [button] 'Click me'")
        agent.bridge = mock_bridge
        
        result = await agent._execute("snapshot interactive")
        
        assert result.success is True
        mock_bridge.snapshot.assert_called_once_with(interactive=True)


class TestAgentScreenshotCommand:
    """Testa comando screenshot."""
    
    @pytest.mark.asyncio
    async def test_agent_screenshot(self):
        """Testa screenshot com path."""
        from agents.moon_browser_agent import MoonBrowserAgent
        
        agent = MoonBrowserAgent()
        
        mock_bridge = AsyncMock()
        mock_bridge.screenshot = AsyncMock(return_value="Screenshot saved: /tmp/test.png")
        agent.bridge = mock_bridge
        
        result = await agent._execute("screenshot /tmp/test.png")
        
        assert result.success is True
        mock_bridge.screenshot.assert_called_once_with("/tmp/test.png")


class TestAgentClickCommand:
    """Testa comando click."""
    
    @pytest.mark.asyncio
    async def test_agent_click(self):
        """Testa click com ref."""
        from agents.moon_browser_agent import MoonBrowserAgent
        
        agent = MoonBrowserAgent()
        
        mock_bridge = AsyncMock()
        mock_bridge.click = AsyncMock(return_value="Clicked @e3")
        agent.bridge = mock_bridge
        
        result = await agent._execute("click @e3")
        
        assert result.success is True
        mock_bridge.click.assert_called_once_with("@e3")


class TestAgentFillCommand:
    """Testa comando fill."""
    
    @pytest.mark.asyncio
    async def test_agent_fill(self):
        """Testa fill com ref e valor."""
        from agents.moon_browser_agent import MoonBrowserAgent
        
        agent = MoonBrowserAgent()
        
        mock_bridge = AsyncMock()
        mock_bridge.fill = AsyncMock(return_value="Filled @e2")
        agent.bridge = mock_bridge
        
        result = await agent._execute("fill @e2 valor do campo")
        
        assert result.success is True
        mock_bridge.fill.assert_called_once_with("@e2", "valor do campo")


class TestAgentHealthCheck:
    """Testa health check do agente."""
    
    @pytest.mark.asyncio
    async def test_agent_health_check(self):
        """Testa método health_check."""
        from agents.moon_browser_agent import MoonBrowserAgent
        
        agent = MoonBrowserAgent()
        
        mock_bridge = AsyncMock()
        mock_bridge.goto = AsyncMock(return_value="Navigated to about:blank")
        agent.bridge = mock_bridge
        
        healthy = await agent.health_check()
        
        assert healthy is True
        mock_bridge.goto.assert_called_once_with("about:blank")


class TestAgentQaPassMode:
    """Testa modo especial qa_pass."""
    
    @pytest.mark.asyncio
    async def test_agent_qa_pass(self):
        """Testa qa_pass que navega, screenshot e snapshot."""
        from agents.moon_browser_agent import MoonBrowserAgent
        
        agent = MoonBrowserAgent()
        
        mock_bridge = AsyncMock()
        mock_bridge.goto = AsyncMock(return_value="Navigated to https://example.com")
        mock_bridge.screenshot = AsyncMock(return_value="Screenshot saved")
        mock_bridge.snapshot = AsyncMock(return_value="@e1 [link]")
        agent.bridge = mock_bridge
        
        with patch("asyncio.sleep", AsyncMock()):  # Skip sleep
            result = await agent._execute("qa_pass https://example.com")
        
        assert result.success is True
        assert mock_bridge.goto.called
        assert mock_bridge.screenshot.called
        assert mock_bridge.snapshot.called


# ─────────────────────────────────────────────────────────────
#  Testes de integração leve (opcional, pode falhar sem daemon)
# ─────────────────────────────────────────────────────────────

@pytest.mark.skip(reason="Requer daemon rodando")
class TestIntegrationWithDaemon:
    """Testes de integração com daemon real."""
    
    @pytest.mark.asyncio
    async def test_full_goto_flow(self):
        """Testa fluxo completo com daemon real."""
        from core.browser_bridge import BrowserBridge
        
        bridge = BrowserBridge()
        
        # Deve iniciar daemon automaticamente
        result = await bridge.goto("https://httpbin.org/get")
        
        assert "BROWSER_ERROR" not in result
        assert "Navigated" in result


# ─────────────────────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
