"""
WebDataRouter — ponto central de detecção de intenção e despacho.

Prefixos suportados:
  sports:<query>                   → auto-detecta sub-modo
  sports:lineup:<home> vs <away>   → LineupDetector (multi-fonte)
  sports:match:<query>             → SofaScoreScraper.search_matches
  sports:live                      → FlashscoreScraper.get_live_matches
  sports:today                     → SofaScoreScraper.get_today_matches
  sports:news:<topic>              → SportsNewsScraper
  <texto livre esportivo>          → auto-detect → sports

Para tasks não-esportivas, retorna {"__delegate__": task} para o
WebMCPAgent tratar com os modos genéricos (search/fetch/deep).
"""
import re
import dataclasses
from typing import Any

_SPORTS_TERMS = [
    "escalação", "escalacao", "jogo", "partida", "futebol",
    "campeonato", "brasileirão", "brasileirao", "champions",
    "libertadores", "copa do brasil", "premier league", "la liga",
    "bundesliga", "serie a", "vs ", " x ", "sofascore", "flashscore",
    "gol", "placar", "resultado", "ao vivo", "live score",
    "titulares", "convocados", "técnico", "treinador",
]


def _is_sports(text: str) -> bool:
    t = text.lower()
    return any(term in t for term in _SPORTS_TERMS)


def _serialize(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if isinstance(obj, list):
        return [_serialize(i) for i in obj]
    return obj


async def route(task: str, **kwargs) -> dict:
    """Entrada única do router. Retorna dict com dados ou __delegate__."""
    task = task.strip()

    if task.startswith("sports:"):
        return await _sports(task[7:], **kwargs)

    if _is_sports(task):
        return await _sports(task, **kwargs)

    return {"__delegate__": task}


async def _sports(sub: str, **kwargs) -> dict:
    from .sports.sofascore import SofaScoreScraper
    from .sports.flashscore import FlashscoreScraper
    from .sports.news import SportsNewsScraper
    from .sports.lineup_detector import LineupDetector

    sub = sub.strip()

    # lineup:<home> vs <away>
    if sub.startswith("lineup:"):
        raw = sub[7:].strip()
        parts = re.split(r"\s+vs\s+", raw, flags=re.IGNORECASE, maxsplit=1)
        home = parts[0].strip()
        away = parts[1].strip() if len(parts) > 1 else ""
        r = await LineupDetector().detect_lineups(
            home, away,
            match_id=kwargs.get("match_id"),
            competition=kwargs.get("competition", ""),
        )
        return _serialize(r)

    if sub in ("live", "ao vivo", "agora"):
        return _serialize(await FlashscoreScraper().get_live_matches())

    if sub in ("today", "hoje"):
        return _serialize(await SofaScoreScraper().get_today_matches())

    if sub.startswith("news:"):
        return _serialize(
            await SportsNewsScraper().get_latest_sports_news(topic=sub[5:].strip())
        )

    if sub.startswith("match:"):
        return _serialize(
            await SofaScoreScraper().search_matches(sub[6:].strip())
        )

    # query genérica → SofaScore, fallback para news
    r = await SofaScoreScraper().search_matches(sub)
    if not r.matches:
        r = await SportsNewsScraper().search_team_news(sub)
    return _serialize(r)
