"""
agents/moon_plan_agent.py
Moon Plan Agent — Modos cognitivos CEO e ENG para design de produto e arquitetura

Architecture:
  - Usa LLMRouter com Groq llama-3.3-70b para raciocínio profundo
  - Dois modos: CEO (estratégia de produto) e ENG (arquitetura técnica)
  - Salva resultados em data/plans/{timestamp}_{mode}.md
  - Publica em "plan.result" na MessageBus
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from core.agent_base import AgentBase, AgentPriority, TaskResult
from core.message_bus import MessageBus
from agents.llm import LLMRouter

logger = logging.getLogger("moon.agents.plan")


# ─────────────────────────────────────────────────────────────
#  Prompts
# ─────────────────────────────────────────────────────────────

CEO_REVIEW_PROMPT = """Você é um avaliador estratégico de produto com mentalidade de founder.
Seu trabalho NÃO é implementar o que foi pedido.
Seu trabalho é questionar se o que foi pedido é a coisa certa.

CONTEXTO DO PROJETO: The Moon Ecosystem — middleware cognitivo pessoal,
sistema de agentes autônomos rodando em Linux, custo zero absoluto,
foco em automação de vida digital (blog, apostas esportivas, trading,
distribuição de conteúdo).

PEDIDO RECEBIDO:
{task}

Responda com:
1. **O Problema Real**: O que o usuário está REALMENTE tentando resolver?
   (Pode ser diferente do que foi pedido)
2. **O Produto de 10 Estrelas**: Se esse problema fosse resolvido de forma
   ideal no contexto do The Moon, como seria? Liste 5-8 características
   concretas e específicas, não genéricas.
3. **O Que NÃO Fazer**: Quais implementações óbvias mas erradas devem
   ser evitadas e por quê?
4. **Validação de Direção**: Uma pergunta crítica que o usuário deve
   responder antes de começar a implementar.
5. **Pré-requisitos Ocultos**: O que precisa existir no ecossistema
   antes que isso funcione corretamente?

Seja direto. Sem prolixidade. Máximo 600 palavras."""


ENG_REVIEW_PROMPT = """Você é um tech lead sênior com foco em sistemas assíncronos,
arquitetura de agentes e sistemas Python de produção.

CONTEXTO: The Moon Ecosystem — Python 3.10+, asyncio, AgentBase,
MessageBus (pub/sub), LLMRouter (Groq/Gemini/OpenRouter fallback),
Playwright (browser), PostgreSQL/JSON local para persistência,
Zorin OS Linux, custo zero absoluto.

TAREFA A ARQUITETAR:
{task}

Gere:
1. **Diagrama de Componentes** (ASCII art obrigatório):
   Mostre os módulos envolvidos, setas de dependência, fluxo de dados.

2. **Diagrama de Sequência** (ASCII art obrigatório):
   Mostre a ordem de chamadas entre agentes/componentes para o caso
   de uso principal.

3. **Decisões de Design** (tabela):
   | Decisão | Opção Escolhida | Alternativa Rejeitada | Razão |

4. **Modos de Falha** (lista):
   Para cada componente crítico: o que acontece se falhar?
   Como o sistema degrada gracefully?

5. **Matriz de Testes**:
   | Cenário | Input | Output Esperado | Tipo de Teste |

6. **Ordem de Implementação**:
   Lista numerada de tarefas atômicas, cada uma implementável em <2h.

Seja preciso. Use nomes reais de arquivos e classes do The Moon.
Máximo 800 palavras, mas não corte os diagramas."""


# ─────────────────────────────────────────────────────────────
#  Moon Plan Agent
# ─────────────────────────────────────────────────────────────

class MoonPlanAgent(AgentBase):
    """
    Agente de planejamento estratégico e técnico.
    
    Modos:
      - ceo: Análise estratégica de produto
      - eng: Arquitetura técnica e design
    
    Uso:
        await agent.execute("ceo Quero adicionar análise de risco")
        await agent.execute("eng Implementar cache distribuído")
        await agent.execute("mode:ceo <descrição>")
        await agent.execute("mode:eng <descrição>")
    """
    
    def __init__(self):
        super().__init__()
        self.name = "MoonPlanAgent"
        self.priority = AgentPriority.HIGH
        self.description = "Strategic planning agent (CEO/ENG modes)"
        self._router: Optional[LLMRouter] = None
        self._message_bus: Optional[MessageBus] = None
        self._plans_dir: Path = Path(__file__).resolve().parent.parent / "data" / "plans"
    
    async def initialize(self) -> None:
        """Inicializa o agente."""
        await super().initialize()
        self._router = LLMRouter()
        self._message_bus = MessageBus()
        
        # Garante diretório de planos
        self._plans_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("MoonPlanAgent initialized")
    
    async def _execute(self, task: str, **kwargs) -> TaskResult:
        """
        Executa análise de planejamento.
        
        Args:
            task: String no formato "ceo <descrição>" ou "eng <descrição>"
        
        Returns:
            TaskResult com análise completa.
        """
        try:
            # Parseia o modo
            mode, description = self._parse_task(task)
            
            if not description:
                return TaskResult(
                    success=False,
                    error=f"Usage: {mode} <description>. Example: ceo Quero adicionar análise de risco"
                )
            
            # Seleciona o prompt
            if mode == "ceo":
                prompt = CEO_REVIEW_PROMPT.format(task=description)
            elif mode == "eng":
                prompt = ENG_REVIEW_PROMPT.format(task=description)
            else:
                return TaskResult(success=False, error=f"Unknown mode: {mode}")
            
            # Chama LLM
            logger.info(f"Executing {mode} mode analysis for: {description[:50]}...")
            
            analysis = await self._router.complete(
                prompt=prompt,
                task_type="complex",
                model="llama-3.3-70b-versatile"
            )
            
            # Salva o resultado
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            plan_file = self._plans_dir / f"{timestamp}_{mode}.md"
            
            plan_content = f"""# {mode.upper()} Analysis — {timestamp}

## Task
{description}

## Analysis
{analysis}
"""
            
            plan_file.write_text(plan_content, encoding="utf-8")
            logger.info(f"Plan saved to {plan_file}")
            
            # Publica na MessageBus
            await self._message_bus.publish(
                sender=self.name,
                topic="plan.result",
                payload={
                    "mode": mode,
                    "task": description,
                    "analysis": analysis,
                    "file": str(plan_file),
                    "timestamp": datetime.now().isoformat(),
                }
            )
            
            return TaskResult(
                success=True,
                data={
                    "mode": mode,
                    "task": description,
                    "analysis": analysis,
                    "file": str(plan_file),
                }
            )
            
        except Exception as e:
            logger.error(f"Plan execution failed: {e}")
            return TaskResult(success=False, error=str(e))
    
    def _parse_task(self, task: str) -> tuple[str, str]:
        """
        Parseia a task para extrair modo e descrição.
        
        Returns:
            (mode, description)
        """
        task = task.strip()
        
        # Formato: "mode:ceo <descrição>" ou "mode:eng <descrição>"
        if task.startswith("mode:"):
            parts = task.split(None, 1)
            mode = parts[0].replace("mode:", "")
            description = parts[1] if len(parts) > 1 else ""
            return mode, description
        
        # Formato: "ceo <descrição>" ou "eng <descrição>"
        first_word = task.split()[0].lower() if task.split() else ""
        
        if first_word in ("ceo", "eng"):
            parts = task.split(None, 1)
            return parts[0], parts[1] if len(parts) > 1 else ""
        
        # Default: assume ceo mode
        return "ceo", task


# ─────────────────────────────────────────────────────────────
#  Factory function
# ─────────────────────────────────────────────────────────────

def create_plan_agent() -> MoonPlanAgent:
    """Factory function para criar o agente."""
    return MoonPlanAgent()
