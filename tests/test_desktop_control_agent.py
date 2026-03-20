"""
tests/test_desktop_control_agent.py
Testes para DesktopControlAgent — 100% mockados (sem GUI real).
"""
import asyncio
import os
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from agents.desktop_control_agent import DesktopControlAgent, _SCREENSHOTS_DIR


@pytest.fixture
def mock_bus():
    bus = MagicMock()
    bus.subscribe = MagicMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def mock_llm():
    return AsyncMock()


@pytest.fixture
def mock_pyautogui():
    pg = MagicMock()
    pg.FAILSAFE = True
    pg.PAUSE = 0.3
    pg.position.return_value = MagicMock(x=100, y=200)
    pg.size.return_value = MagicMock(width=1920, height=1080)
    pg.locateOnScreen.return_value = MagicMock(left=10, top=20, width=100, height=50)
    return pg


@pytest.fixture
def agent_no_display(mock_bus, mock_llm):
    """Agente sem display disponível — modo limitado."""
    with patch.dict(os.environ, {}, clear=True):
        if "DISPLAY" in os.environ:
            del os.environ["DISPLAY"]
        a = DesktopControlAgent(bus=mock_bus, llm=mock_llm)
        a._display_available = False
        return a


@pytest.fixture
def agent(mock_bus, mock_llm, mock_pyautogui):
    """Agente com display mockado."""
    a = DesktopControlAgent(bus=mock_bus, llm=mock_llm)
    a._display_available = True
    a._pyautogui = mock_pyautogui
    a._mss = MagicMock()
    a._pytesseract = MagicMock()
    a._pytesseract.image_to_string.return_value = "texto extraído pelo OCR"
    mock_img = MagicMock()
    mock_img.width = 1920
    mock_img.height = 1080
    mock_img.size = (1920, 1080)
    mock_img.rgb = b"\x00" * (1920 * 1080 * 3)
    a._mss.mss.return_value.__enter__.return_value.grab.return_value = mock_img
    a._mss.mss.return_value.__enter__.return_value.monitors = [
        None, {"top": 0, "left": 0, "width": 1920, "height": 1080}
    ]
    return a


# ── Instanciação ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_instantiation_no_display(agent_no_display):
    assert agent_no_display.name == "DesktopControlAgent"
    assert agent_no_display._display_available is False
    assert agent_no_display._pyautogui is None


@pytest.mark.asyncio
async def test_instantiation_with_display(agent):
    assert agent._display_available is True
    assert agent._pyautogui is not None


# ── Status ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_status_no_display(agent_no_display):
    result = await agent_no_display._execute("status")
    assert result.success is True
    assert result.data["display_available"] is False
    assert result.data["pyautogui_loaded"] is False


@pytest.mark.asyncio
async def test_execute_status_with_display(agent):
    result = await agent._execute("status")
    assert result.success is True
    assert result.data["display_available"] is True
    assert result.data["pyautogui_loaded"] is True


# ── Sem display: deve retornar RuntimeError ───────────────────────

@pytest.mark.asyncio
async def test_click_no_display_fails(agent_no_display):
    result = await agent_no_display._execute("click", x=100, y=200)
    assert result.success is False
    assert "DISPLAY" in result.error or "display" in result.error.lower()


@pytest.mark.asyncio
async def test_type_no_display_fails(agent_no_display):
    result = await agent_no_display._execute("type_text", text="hello")
    assert result.success is False


# ── Mouse ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_click_calls_pyautogui(agent):
    with patch.object(agent, "_throttle", new_callable=AsyncMock):
        result = await agent._execute("click", x=300, y=400)
    assert result.success is True
    agent._pyautogui.click.assert_called_once_with(300, 400, button="left")


@pytest.mark.asyncio
async def test_click_right_button(agent):
    with patch.object(agent, "_throttle", new_callable=AsyncMock):
        result = await agent._execute("click", x=100, y=100, button="right")
    assert result.success is True
    agent._pyautogui.click.assert_called_with(100, 100, button="right")


@pytest.mark.asyncio
async def test_double_click(agent):
    with patch.object(agent, "_throttle", new_callable=AsyncMock):
        result = await agent._execute("double_click", x=50, y=60)
    assert result.success is True
    agent._pyautogui.doubleClick.assert_called_once_with(50, 60)


@pytest.mark.asyncio
async def test_scroll(agent):
    result = await agent._execute("scroll", x=100, y=100, clicks=5)
    assert result.success is True
    agent._pyautogui.scroll.assert_called_once_with(5, x=100, y=100)


@pytest.mark.asyncio
async def test_get_mouse_position(agent):
    result = await agent._execute("get_mouse_position")
    assert result.success is True
    assert result.data["x"] == 100
    assert result.data["y"] == 200


@pytest.mark.asyncio
async def test_click_missing_params(agent):
    result = await agent._execute("click", x=10)
    assert result.success is False
    assert "y" in result.error


# ── Teclado ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_type_text(agent):
    with patch.object(agent, "_throttle", new_callable=AsyncMock):
        result = await agent._execute("type_text", text="hello moon")
    assert result.success is True
    assert result.data["chars"] == 10
    agent._pyautogui.typewrite.assert_called_once_with("hello moon", interval=0.05)


@pytest.mark.asyncio
async def test_press_key(agent):
    with patch.object(agent, "_throttle", new_callable=AsyncMock):
        result = await agent._execute("press_key", key="enter")
    assert result.success is True
    agent._pyautogui.press.assert_called_once_with("enter")


@pytest.mark.asyncio
async def test_hotkey(agent):
    with patch.object(agent, "_throttle", new_callable=AsyncMock):
        result = await agent._execute("hotkey", keys=["ctrl", "c"])
    assert result.success is True
    agent._pyautogui.hotkey.assert_called_once_with("ctrl", "c")


# ── Tela / OCR ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_screen_size(agent):
    result = await agent._execute("get_screen_size")
    assert result.success is True
    assert result.data["width"] == 1920
    assert result.data["height"] == 1080


@pytest.mark.asyncio
async def test_find_on_screen_found(agent):
    result = await agent._execute(
        "find_on_screen", image_path="fake.png", confidence=0.8
    )
    assert result.success is True
    assert result.data["center_x"] == 60
    assert result.data["center_y"] == 45


@pytest.mark.asyncio
async def test_find_on_screen_not_found(agent):
    agent._pyautogui.locateOnScreen.return_value = None
    result = await agent._execute("find_on_screen", image_path="nope.png")
    assert result.success is False
    assert result.data == {"found": False}


# ── Janelas (xdotool mockado) ─────────────────────────────────────

@pytest.mark.asyncio
async def test_find_window_returns_list(agent):
    with patch.object(agent, "_run_xdotool", new_callable=AsyncMock) as mock_xdt:
        mock_xdt.side_effect = ["12345\n67890", "Firefox", "Terminal"]
        result = await agent._execute("find_window", name="Firefox")
    assert result.success is True
    assert result.data["count"] == 2


@pytest.mark.asyncio
async def test_find_window_not_found(agent):
    with patch.object(agent, "_run_xdotool", side_effect=RuntimeError("no windows")):
        result = await agent._execute("find_window", name="NotExist")
    assert result.success is True
    assert result.data["count"] == 0


@pytest.mark.asyncio
async def test_focus_window(agent):
    with patch.object(agent, "_run_xdotool", new_callable=AsyncMock) as mock_xdt:
        mock_xdt.return_value = ""
        result = await agent._execute("focus_window", window_id="12345")
    assert result.success is True
    assert mock_xdt.call_count == 2


@pytest.mark.asyncio
async def test_get_active_window(agent):
    with patch.object(agent, "_run_xdotool", new_callable=AsyncMock) as mock_xdt:
        mock_xdt.side_effect = ["99999", "VS Code"]
        result = await agent._execute("get_active_window")
    assert result.success is True
    assert result.data["id"] == "99999"
    assert result.data["name"] == "VS Code"


# ── Macro ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_macro_empty_steps(agent):
    result = await agent._execute("run_macro", steps=[])
    assert result.success is False
    assert "steps" in result.error


@pytest.mark.asyncio
async def test_run_macro_executes_sequence(agent):
    with patch.object(agent, "_throttle", new_callable=AsyncMock):
        result = await agent._execute(
            "run_macro",
            steps=[
                {"action": "press_key", "params": {"key": "ctrl"}},
                {"action": "press_key", "params": {"key": "a"}},
            ],
        )
    assert result.success is True
    assert result.data["total"] == 2
    assert result.data["ok"] == 2


@pytest.mark.asyncio
async def test_run_macro_partial_failure(agent):
    async def mock_execute(task, **kwargs):
        from core.agent_base import TaskResult
        if task == "press_key" and kwargs.get("key") == "bad_key":
            return TaskResult(success=False, error="bad key")
        return TaskResult(success=True, data={})

    with patch.object(agent, "_execute", side_effect=mock_execute):
        result = await agent.run_macro([
            {"action": "press_key", "params": {"key": "enter"}},
            {"action": "press_key", "params": {"key": "bad_key"}},
        ])
    assert result[0]["success"] is True
    assert result[1]["success"] is False


# ── MessageBus ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_on_desktop_action_publishes_result(agent, mock_bus):
    with patch.object(agent, "_execute", new_callable=AsyncMock) as mock_exec:
        from core.agent_base import TaskResult
        mock_exec.return_value = TaskResult(success=True, data={"key": "val"})
        await agent._on_desktop_action(
            "ArchitectAgent",
            {"action": "press_key", "params": {"key": "enter"},
             "request_id": "req-001"},
        )
    mock_bus.publish.assert_called_once()
    call_args = mock_bus.publish.call_args
    assert call_args[0][1] == "desktop.result"
    assert call_args[1].get("target") == "ArchitectAgent"


# ── Task desconhecida ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_unknown_task(agent):
    result = await agent._execute("unknown_action")
    assert result.success is False
    assert "desconhecida" in result.error
