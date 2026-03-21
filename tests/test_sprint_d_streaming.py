"""Sprint D — Test suite for LLM Streaming."""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from core.agent_base import TaskResult


# ─────────────────────────────────────────────
# LLMRouter stream() tests
# ─────────────────────────────────────────────
class TestLLMRouterStream:

    def setup_method(self):
        from agents.llm import LLMRouter
        self.llm = LLMRouter()

    def test_stream_method_exists(self):
        assert hasattr(self.llm, 'stream'), "stream() deve existir no LLMRouter"

    def test_complete_method_still_exists(self):
        assert hasattr(self.llm, 'complete'), "complete() não deve ter sido removido"

    def test_stream_is_async_generator(self):
        import inspect
        assert inspect.isasyncgenfunction(self.llm.stream), \
            "stream() deve ser async generator function"

    def test_private_stream_methods_exist(self):
        assert hasattr(self.llm, '_stream_groq')
        assert hasattr(self.llm, '_stream_gemini')
        assert hasattr(self.llm, '_stream_openrouter')

    @pytest.mark.asyncio
    async def test_stream_groq_yields_chunks(self):
        """Groq stream retorna chunks de texto."""
        mock_chunk = MagicMock()
        mock_chunk.choices = [MagicMock()]
        mock_chunk.choices[0].delta = MagicMock()
        mock_chunk.choices[0].delta.content = "chunk de texto"

        async def mock_aiter(*args, **kwargs):
            yield mock_chunk

        mock_stream = MagicMock()
        mock_stream.__aiter__ = mock_aiter

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_stream)

        with patch('groq.AsyncGroq', return_value=mock_client):
            chunks = []
            async for chunk in self.llm._stream_groq("test prompt"):
                chunks.append(chunk)
            assert len(chunks) > 0
            assert "chunk de texto" in chunks

    @pytest.mark.asyncio
    async def test_stream_fallback_on_groq_error(self):
        """Quando Groq falha, stream faz fallback para Gemini."""
        async def fail_groq(*args, **kwargs):
            raise Exception("Groq indisponível")
            yield  # tornar async generator

        async def mock_gemini(*args, **kwargs):
            yield "resposta do gemini"

        with patch.object(self.llm, '_stream_groq', fail_groq), \
             patch.object(self.llm, '_stream_gemini', mock_gemini):
            chunks = []
            async for chunk in self.llm.stream("test"):
                chunks.append(chunk)
            assert "resposta do gemini" in chunks

    @pytest.mark.asyncio
    async def test_stream_full_fallback_chain(self):
        """Quando todos os providers falham, retorna mensagem de erro."""
        async def fail(*args, **kwargs):
            raise Exception("provider down")
            yield

        with patch.object(self.llm, '_stream_groq', fail), \
             patch.object(self.llm, '_stream_gemini', fail), \
             patch.object(self.llm, '_stream_openrouter', fail):
            chunks = []
            async for chunk in self.llm.stream("test"):
                chunks.append(chunk)
            full = "".join(chunks)
            assert "ERRO" in full.upper()

    @pytest.mark.asyncio
    async def test_stream_with_task_type(self):
        """stream() aceita task_type como parâmetro."""
        async def mock_groq(prompt, task_type="general", **kwargs):
            yield f"task_type={task_type}"

        with patch.object(self.llm, '_stream_groq', mock_groq):
            chunks = []
            async for chunk in self.llm.stream("prompt", task_type="telegram"):
                chunks.append(chunk)
            assert any("telegram" in c for c in chunks)

    @pytest.mark.asyncio
    async def test_stream_openrouter_yields_chunks(self):
        """OpenRouter stream retorna chunks via API OpenAI-compatible."""
        mock_chunk = MagicMock()
        mock_chunk.choices = [MagicMock()]
        mock_chunk.choices[0].delta = MagicMock()
        mock_chunk.choices[0].delta.content = "openrouter chunk"

        async def mock_aiter(*args, **kwargs):
            yield mock_chunk

        mock_stream = MagicMock()
        mock_stream.__aiter__ = mock_aiter

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_stream)

        with patch('openai.AsyncOpenAI', return_value=mock_client):
            chunks = []
            async for chunk in self.llm._stream_openrouter("test"):
                chunks.append(chunk)
            assert "openrouter chunk" in chunks

    @pytest.mark.asyncio
    async def test_stream_empty_delta_skipped(self):
        """Chunks com content None são ignorados."""
        mock_chunk_none = MagicMock()
        mock_chunk_none.choices = [MagicMock()]
        mock_chunk_none.choices[0].delta = MagicMock()
        mock_chunk_none.choices[0].delta.content = None

        mock_chunk_real = MagicMock()
        mock_chunk_real.choices = [MagicMock()]
        mock_chunk_real.choices[0].delta = MagicMock()
        mock_chunk_real.choices[0].delta.content = "conteúdo real"

        async def mock_aiter(*args, **kwargs):
            yield mock_chunk_none
            yield mock_chunk_real

        mock_stream = MagicMock()
        mock_stream.__aiter__ = mock_aiter

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_stream)

        with patch('groq.AsyncGroq', return_value=mock_client):
            chunks = []
            async for chunk in self.llm._stream_groq("test"):
                chunks.append(chunk)
            assert None not in chunks
            assert "conteúdo real" in chunks


# ─────────────────────────────────────────────
# Telegram streaming helper tests
# ─────────────────────────────────────────────
class TestTelegramStreamingHelper:

    def test_streaming_helper_exists_in_bot(self):
        with open('agents/telegram/bot.py', 'r') as f:
            content = f.read()
        assert '_send_streaming_response' in content, \
            "_send_streaming_response deve existir em agents/telegram/bot.py"

    def test_bot_syntax_valid(self):
        import ast
        with open('agents/telegram/bot.py', 'r') as f:
            content = f.read()
        try:
            ast.parse(content)
            assert True
        except SyntaxError as e:
            pytest.fail(f"agents/telegram/bot.py tem erro de sintaxe: {e}")


# ─────────────────────────────────────────────
# MoonCLIAgent streaming tests
# ─────────────────────────────────────────────
class TestMoonCLIAgentStreaming:

    def setup_method(self):
        from agents.moon_cli_agent import MoonCLIAgent
        self.agent = MoonCLIAgent()

    def test_stream_response_method_exists(self):
        assert hasattr(self.agent, 'stream_response'), \
            "stream_response() deve existir no MoonCLIAgent"

    def test_execute_method_intact(self):
        import inspect
        sig = inspect.signature(self.agent._execute)
        assert 'task' in str(sig), "_execute() deve ter parâmetro task"
        assert 'kwargs' in str(sig), "_execute() deve ter **kwargs"

    @pytest.mark.asyncio
    async def test_stream_response_returns_task_result(self):
        async def mock_stream(prompt, **kwargs):
            yield "resposta "
            yield "em streaming"

        with patch.object(self.agent, 'llm', create=True) as mock_llm:
            mock_llm.stream = mock_stream
            with patch('builtins.print'):
                result = await self.agent.stream_response("test prompt")
        assert isinstance(result, TaskResult)

    @pytest.mark.asyncio
    async def test_stream_response_error_handling(self):
        async def fail_stream(prompt, **kwargs):
            raise Exception("streaming error")
            yield

        with patch('agents.llm.LLMRouter') as MockLLM:
            instance = MockLLM.return_value
            instance.stream = fail_stream
            with patch('builtins.print'):
                result = await self.agent.stream_response("test")
        assert isinstance(result, TaskResult)

    def test_cli_agent_syntax_valid(self):
        import ast
        with open('agents/moon_cli_agent.py', 'r') as f:
            content = f.read()
        try:
            ast.parse(content)
            assert True
        except SyntaxError as e:
            pytest.fail(f"agents/moon_cli_agent.py tem erro de sintaxe: {e}")


# ─────────────────────────────────────────────
# Integração geral
# ─────────────────────────────────────────────
class TestSprintDIntegration:

    def test_llm_router_complete_signature_unchanged(self):
        """complete() não deve ter sido modificado."""
        import inspect
        from agents.llm import LLMRouter
        llm = LLMRouter()
        sig = inspect.signature(llm.complete)
        params = list(sig.parameters.keys())
        assert 'prompt' in params, "complete() deve ter parâmetro 'prompt'"

    def test_stream_and_complete_coexist(self):
        from agents.llm import LLMRouter
        llm = LLMRouter()
        assert hasattr(llm, 'complete') and hasattr(llm, 'stream')

    def test_task_result_import_in_cli_agent(self):
        with open('agents/moon_cli_agent.py', 'r') as f:
            content = f.read()
        assert 'TaskResult' in content, \
            "agents/moon_cli_agent.py deve importar ou usar TaskResult"