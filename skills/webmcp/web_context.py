"""
WebContextEnricher — detecta se uma task precisa de dados externos
e retorna contexto enriquecido via WebMCPAgent.

Desacoplado do Orchestrator: pode ser importado de qualquer lugar.
"""
import re
from typing import Optional

# ── Sinais que indicam necessidade de dados externos ─────────

_WEB_SIGNALS = [
    # Busca genérica
    r"\bbuscar?\b", r"\bpesquisar?\b", r"\bprocurar?\b",
    r"\bencontrar?\b", r"\bquem é\b", r"\bqual é\b",
    r"\bcomo está\b", r"\bonde fica\b",
    # Dados em tempo real
    r"\bhoje\b", r"\bagora\b", r"\bao vivo\b", r"\blive\b",
    r"\batualizado\b", r"\breal.?time\b", r"\búltim[ao]\b",
    r"\bnotícia\b", r"\bnoticia\b",
    # Finanças
    r"\bpreço\b", r"\bcotação\b", r"\bcota[cç]ao\b",
    r"\bdólar\b", r"\beuro\b", r"\bbitcoin\b", r"\bcripto\b",
]

# ── Sinais esportivos (rota direta para sports layer) ────────

_SPORTS_SIGNALS = [
    r"\bescala[cç]ao\b", r"\bescalação\b", r"\btitulares\b",
    r"\bpartida\b", r"\bjogo\b", r"\bplacar\b", r"\bresultado\b",
    r"\bfutebol\b", r"\bbrasileirão\b", r"\bchampions\b",
    r"\blibertadores\b", r"\bcopado\b", r"\bpremier\b",
    r"\b(flamengo|palmeiras|corinthians|são paulo|santos|grêmio"
    r"|atletico|cruzeiro|botafogo|vasco|fluminense|internacional"
    r"|manchester|barcelona|real madrid|psg|juventus|milan|inter"
    r"|arsenal|chelsea|liverpool|city|united)\b",
    r"\bvs\b", r" x ",
]

_WEB_RE = re.compile("|".join(_WEB_SIGNALS), re.IGNORECASE)
_SPORTS_RE = re.compile("|".join(_SPORTS_SIGNALS), re.IGNORECASE)


def needs_web_data(task: str) -> bool:
    """True se a task indica necessidade de dados externos em tempo real."""
    return bool(_WEB_RE.search(task) or _SPORTS_RE.search(task))


def needs_sports_data(task: str) -> bool:
    """True se é especificamente uma query esportiva."""
    return bool(_SPORTS_RE.search(task))


def build_web_task(task: str) -> str:
    """Converte task livre em task string para WebMCPAgent."""
    if needs_sports_data(task):
        # Verifica se é pedido de escalação específico
        if re.search(r"escala[cç][aã]o|titulares|time confirmado", task, re.I):
            return f"sports:lineup:{task}"
        return f"sports:{task}"
    return f"search_and_fetch:{task}"


async def fetch_web_context(task: str) -> Optional[dict]:
    """
    Chama WebMCPAgent e retorna dados enriquecidos.
    Retorna None se falhar (não bloqueia fluxo principal).
    """
    try:
        from agents.webmcp_agent import WebMCPAgent
        agent = WebMCPAgent()
        web_task = build_web_task(task)
        result = await agent._execute(web_task)
        if result.success:
            return {
                "web_task": web_task,
                "data": result.data,
                "execution_time": result.execution_time,
            }
    except Exception:
        pass
    return None
