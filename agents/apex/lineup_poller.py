"""
APEXLineupPoller — polling autônomo de escalações para o APEX Betting.

Roda como task asyncio paralela ao loop principal.
Janela de polling: t-70min até t-5min.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Set

logger = logging.getLogger(__name__)


class APEXLineupPoller:
    """Serviço de polling de escalações com notificação progressiva."""

    POLL_INTERVAL_SECONDS = 300
    WINDOW_START_MINUTES = 70
    WINDOW_END_MINUTES = 5
    NOTIFY_PARTIAL = True

    def __init__(self, context: Any, telegram_sender: Any) -> None:
        self._context = context
        self._telegram = telegram_sender
        self._notified_full: Set[int] = set()
        self._notified_partial: Set[int] = set()
        self._running = False

    async def start(self) -> None:
        """Loop principal; ideal para uso com asyncio.create_task()."""
        self._running = True
        logger.info("APEXLineupPoller: iniciado")
        while self._running:
            try:
                await self._poll_cycle()
            except asyncio.CancelledError:
                logger.info("APEXLineupPoller: cancelado")
                raise
            except Exception as e:
                logger.error(f"APEXLineupPoller: erro no ciclo: {e}")
            if self._running:
                await asyncio.sleep(self.POLL_INTERVAL_SECONDS)

    def stop(self) -> None:
        self._running = False

    async def _poll_cycle(self) -> None:
        matches = self._get_window_matches()
        if not matches:
            return

        logger.info(f"APEXLineupPoller: {len(matches)} jogo(s) na janela de polling")
        for analysis in matches:
            match_id = analysis["match_id"]
            if match_id in self._notified_full:
                continue

            status = await self._check_lineups(
                analysis["home_team"],
                analysis["away_team"],
                analysis.get("competition", ""),
                analysis.get("match_id"),
            )
            await self._handle_status(
                match_id,
                analysis["home_team"],
                analysis["away_team"],
                analysis.get("competition", ""),
                status,
            )

    def _get_window_matches(self) -> List[dict]:
        """Retorna partidas entre t-70min e t-5min."""
        now = datetime.now(timezone.utc)
        matches: List[dict] = []
        for analysis in self._context._context.get("analyses", []):
            try:
                kickoff = datetime.fromisoformat(
                    analysis["kickoff_utc"].replace("Z", "+00:00")
                )
                diff = (kickoff - now).total_seconds() / 60
                if self.WINDOW_END_MINUTES <= diff <= self.WINDOW_START_MINUTES:
                    matches.append(analysis)
            except Exception:
                continue
        return matches

    async def _check_lineups(
        self,
        home: str,
        away: str,
        competition: str = "",
        match_id: Any = None,
    ) -> dict:
        """Consulta o WebMCP e normaliza o status para o poller."""
        safe_status: Dict[str, Any] = {
            "home_team": home,
            "away_team": away,
            "home_confirmed": False,
            "away_confirmed": False,
            "both_confirmed": False,
            "news_found": 0,
            "lineup_news": 0,
            "source": "error",
            "home_starters": [],
            "away_starters": [],
            "home_formation": "",
            "away_formation": "",
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            from skills.webmcp.sports.lineup_detector import LineupDetector

            detector = LineupDetector()
            result = await detector.detect_lineups(
                home,
                away,
                match_id=str(match_id) if match_id is not None else None,
                competition=competition,
            )
        except Exception as e:
            logger.warning(f"APEXLineupPoller: LineupDetector falhou ({home} × {away}): {e}")
            return safe_status

        status = dict(safe_status)
        status["source"] = result.raw_data.get("lineup_source", result.provider or "none")
        status["news_found"] = len(result.news)
        status["lineup_news"] = sum(1 for n in result.news if n.mentions_lineup)

        if result.matches:
            match = result.matches[0]
            if match.home_lineup:
                status["home_confirmed"] = bool(match.home_lineup.confirmed)
                status["home_starters"] = [p.name for p in match.home_lineup.starters[:11]]
                status["home_formation"] = match.home_lineup.formation
            if match.away_lineup:
                status["away_confirmed"] = bool(match.away_lineup.confirmed)
                status["away_starters"] = [p.name for p in match.away_lineup.starters[:11]]
                status["away_formation"] = match.away_lineup.formation

        status["both_confirmed"] = status["home_confirmed"] and status["away_confirmed"]
        status["checked_at"] = datetime.now(timezone.utc).isoformat()
        return status

    async def _handle_status(
        self,
        match_id: int,
        home: str,
        away: str,
        competition: str,
        status: dict,
    ) -> None:
        """Envia notificações completas ou parciais conforme o status."""
        if match_id in self._notified_full:
            return

        both = status.get("both_confirmed", False)
        home_ok = status.get("home_confirmed", False)
        away_ok = status.get("away_confirmed", False)
        news_count = status.get("lineup_news", 0)
        source = status.get("source", "?")

        if both and match_id not in self._notified_full:
            msg = self._format_full_confirmation(home, away, competition, status, source)
            sent = await self._telegram.send(msg)
            if sent:
                self._notified_full.add(match_id)
                self._context._context.setdefault("lineups_confirmed", {})[match_id] = status
                if hasattr(self._context, "_save"):
                    self._context._save()
                logger.info(
                    f"APEXLineupPoller: ambas escalações confirmadas {home} × {away} via {source}"
                )
            return

        if self.NOTIFY_PARTIAL and (home_ok or away_ok or news_count > 0):
            if match_id not in self._notified_partial:
                msg = self._format_partial_notification(home, away, competition, status)
                sent = await self._telegram.send(msg)
                if sent:
                    self._notified_partial.add(match_id)
                    logger.info(f"APEXLineupPoller: escalação parcial {home} × {away}")

    def _format_full_confirmation(
        self,
        home: str,
        away: str,
        competition: str,
        status: dict,
        source: str,
    ) -> str:
        now_label = datetime.now().strftime("%H:%M")
        lines = [
            f"✅ *ESCALAÇÕES CONFIRMADAS* — {now_label}",
            f"⚽ *{home} × {away}*",
            f"🏆 {competition}",
            f"📡 Fonte: {source}",
            "",
        ]

        home_starters = status.get("home_starters", [])
        away_starters = status.get("away_starters", [])
        home_form = status.get("home_formation", "")
        away_form = status.get("away_formation", "")

        if home_starters:
            form = f" ({home_form})" if home_form else ""
            lines.append(f"🔵 *{home}*{form}:")
            lines.extend(f"  {player}" for player in home_starters[:11])
            lines.append("")

        if away_starters:
            form = f" ({away_form})" if away_form else ""
            lines.append(f"🔴 *{away}*{form}:")
            lines.extend(f"  {player}" for player in away_starters[:11])
            lines.append("")

        lines.append("🔔 Análise pré-jogo refinada em breve.")
        return "\n".join(lines)

    def _format_partial_notification(
        self,
        home: str,
        away: str,
        competition: str,
        status: dict,
    ) -> str:
        home_ok = status.get("home_confirmed", False)
        away_ok = status.get("away_confirmed", False)
        news_count = status.get("lineup_news", 0)
        now_label = datetime.now().strftime("%H:%M")

        confirmed_team = home if home_ok else away if away_ok else None
        pending_team = away if home_ok else home if away_ok else None

        lines = [
            f"🔶 *ESCALAÇÃO PARCIAL* — {now_label}",
            f"⚽ *{home} × {away}* | {competition}",
            "",
        ]

        if confirmed_team and pending_team:
            lines.append(f"✅ {confirmed_team}: confirmado")
            lines.append(f"⏳ {pending_team}: aguardando")
        elif news_count > 0:
            lines.append(f"📰 {news_count} artigo(s) de escalação encontrado(s)")
            lines.append("⏳ Escalações oficiais ainda não confirmadas")

        lines.append("🔄 Próxima verificação em 5 minutos.")
        return "\n".join(lines)
