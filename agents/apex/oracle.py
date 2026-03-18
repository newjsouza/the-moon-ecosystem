"""
agents/apex/oracle.py
ApexOracle — Motor de análise autônoma de apostas de futebol.

RESPONSABILIDADES:
  1. Às 07:30 todo dia → buscar jogos do dia via football-data.org
                        → gerar análises completas + 2-3 indicações de mercados
                        → enviar via Telegram

  2. 45 min antes de cada jogo → buscar escalações atualizadas
                                → refinar análise com desfalques/retornos/suspensões
                                → enviar update individual via Telegram

  3. Bot Telegram → guardar contexto das análises do dia
                  → responder dúvidas sobre qualquer indicação enviada

ANTI-ALUCINAÇÃO:
  - Todos os dados vêm da football-data.org API (dados reais)
  - Se API falhar → log de erro + aviso ao usuário → não envia análise falsa
  - Escalações buscadas via API ou fonte secundária real
  - Zero placeholders, zero exemplos inventados

SIGNATURES RESPEITADAS (imutáveis):
  AgentBase._execute(): async def _execute(self, task: str, **kwargs) -> TaskResult
  TaskResult:           TaskResult(success, data=None, error=None, execution_time=0.0)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("moon.apex.oracle")

ROOT_DIR   = Path(__file__).resolve().parent.parent.parent
DATA_DIR   = ROOT_DIR / "data" / "apex"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Arquivo de contexto do dia — o Bot lê isso para responder dúvidas
DAILY_CONTEXT_FILE = DATA_DIR / "daily_context.json"

FOOTBALL_API_BASE  = "https://api.football-data.org/v4"
FOOTBALL_API_KEY   = os.getenv("FOOTBALL_DATA_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
GROQ_API_KEY       = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL         = "llama-3.3-70b-versatile"

# Ligas monitoradas (códigos football-data.org)
MONITORED_COMPETITIONS = {
    "PL":  "Premier League 🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "PD":  "La Liga 🇪🇸",
    "BL1": "Bundesliga 🇩🇪",
    "SA":  "Serie A 🇮🇹",
    "FL1": "Ligue 1 🇫🇷",
    "CL":  "Champions League 🏆",
    "EL":  "Europa League 🟠",
    "BSB": "Brasileirão Série A 🇧🇷",
    "PPL": "Primeira Liga 🇵🇹",
    "DED": "Eredivisie 🇳🇱",
}

# Mercados de apostas disponíveis para análise
BETTING_MARKETS = [
    "Resultado Final (1X2)",
    "Dupla Chance",
    "Empate Anula Aposta (AH)",
    "Ambos Marcam (BTTS)",
    "Over/Under 2.5 Gols",
    "Over/Under 1.5 Gols",
    "Over/Under 9.5 Escanteios",
    "Handicap Asiático",
    "Gol no 1º Tempo",
]


# ─────────────────────────────────────────────────────────────
#  Football Data Client
# ─────────────────────────────────────────────────────────────

class FootballDataClient:
    """Cliente assíncrono para football-data.org API v4."""

    def __init__(self) -> None:
        self.api_key = FOOTBALL_API_KEY
        self.base    = FOOTBALL_API_BASE
        self._cache: Dict[str, Any] = {}

    def _headers(self) -> dict:
        return {"X-Auth-Token": self.api_key}

    async def get(self, path: str, params: dict = None) -> Optional[dict]:
        cache_key = f"{path}_{json.dumps(params or {})}"
        if cache_key in self._cache:
            cached_at, data = self._cache[cache_key]
            # Cache de 10 minutos para dados não-críticos
            if time.time() - cached_at < 600:
                return data

        url = f"{self.base}{path}"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, headers=self._headers(), params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    self._cache[cache_key] = (time.time(), data)
                    return data
                elif resp.status_code == 429:
                    logger.warning(f"FootballData API rate limit atingido. Path: {path}")
                    return None
                else:
                    logger.error(f"FootballData API erro {resp.status_code} para {path}: {resp.text[:200]}")
                    return None
        except httpx.TimeoutException:
            logger.error(f"FootballData API timeout para {path}")
            return None
        except Exception as e:
            logger.error(f"FootballData API erro inesperado: {e}")
            return None

    async def get_matches_today(self) -> List[dict]:
        """Busca partidas do dia atual em todas as ligas monitoradas."""
        today = datetime.now().strftime("%Y-%m-%d")
        data  = await self.get("/matches", params={"dateFrom": today, "dateTo": today, "status": "SCHEDULED,TIMED"})
        if not data:
            return []
        matches = data.get("matches", [])
        # Filtra apenas ligas monitoradas
        filtered = [
            m for m in matches
            if m.get("competition", {}).get("code") in MONITORED_COMPETITIONS
        ]
        logger.info(f"FootballData: {len(filtered)} jogos encontrados para hoje ({today})")
        return filtered

    async def get_last_5_matches(self, team_id: int) -> List[dict]:
        """Busca os últimos 5 jogos de um time."""
        data = await self.get(f"/teams/{team_id}/matches", params={"status": "FINISHED", "limit": 5})
        if not data:
            return []
        matches = data.get("matches", [])
        return sorted(matches, key=lambda m: m.get("utcDate", ""), reverse=True)[:5]

    async def get_match_detail(self, match_id: int) -> Optional[dict]:
        """Busca detalhes completos de uma partida (inclui lineups se disponíveis)."""
        return await self.get(f"/matches/{match_id}")

    async def get_team_info(self, team_id: int) -> Optional[dict]:
        """Busca informações do time."""
        return await self.get(f"/teams/{team_id}")

    async def get_standings(self, competition_code: str) -> Optional[dict]:
        """Busca tabela de classificação de uma liga."""
        return await self.get(f"/competitions/{competition_code}/standings")


# ─────────────────────────────────────────────────────────────
#  Telegram Sender
# ─────────────────────────────────────────────────────────────

class TelegramSender:
    """Envia mensagens via Telegram Bot API diretamente (sem python-telegram-bot)."""

    def __init__(self) -> None:
        self.token   = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.base    = f"https://api.telegram.org/bot{self.token}"

    async def send(self, text: str, parse_mode: str = "Markdown") -> bool:
        """Envia mensagem. Divide automaticamente se > 4096 chars."""
        if not self.token or not self.chat_id:
            logger.error("TelegramSender: TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID não configurados")
            return False

        # Telegram max = 4096 chars por mensagem
        chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
        success = True

        async with httpx.AsyncClient(timeout=15) as client:
            for chunk in chunks:
                try:
                    resp = await client.post(
                        f"{self.base}/sendMessage",
                        json={
                            "chat_id":    self.chat_id,
                            "text":       chunk,
                            "parse_mode": parse_mode,
                        }
                    )
                    if resp.status_code != 200:
                        logger.error(f"Telegram send erro {resp.status_code}: {resp.text[:200]}")
                        success = False
                    await asyncio.sleep(0.5)  # evitar rate limit
                except Exception as e:
                    logger.error(f"Telegram send exceção: {e}")
                    success = False

        return success


# ─────────────────────────────────────────────────────────────
#  Groq LLM Caller
# ─────────────────────────────────────────────────────────────

class ApexLLM:
    """Chama Groq para geração das análises."""

    def __init__(self) -> None:
        from groq import AsyncGroq
        self.client = AsyncGroq(api_key=GROQ_API_KEY)

    async def generate(self, prompt: str, system: str = "") -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            completion = await self.client.chat.completions.create(
                model       = GROQ_MODEL,
                messages    = messages,
                max_tokens  = 2048,
                temperature = 0.3,
            )
            return completion.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"ApexLLM erro: {e}")
            return ""


# ─────────────────────────────────────────────────────────────
#  Context Store — Bot lê isso para responder dúvidas
# ─────────────────────────────────────────────────────────────

class DailyContextStore:
    """
    Armazena o contexto completo das análises do dia.
    O MoonBot lê este arquivo para responder dúvidas sobre indicações.
    """

    def __init__(self) -> None:
        self._context: Dict[str, Any] = {
            "date": "",
            "analyses": [],       # lista de análises completas
            "sent_at": "",
            "matches_summary": []  # resumo para o bot responder
        }
        self._load()

    def save_daily_analyses(self, date: str, analyses: List[dict]) -> None:
        self._context = {
            "date": date,
            "analyses": analyses,
            "sent_at": datetime.now().isoformat(),
            "matches_summary": [
                {
                    "match_id":     a["match_id"],
                    "teams":        a["teams"],
                    "competition":  a["competition"],
                    "kickoff":      a["kickoff_local"],
                    "markets":      a["betting_markets"],
                    "pre45_sent":   False,
                }
                for a in analyses
            ]
        }
        self._save()

    def mark_pre45_sent(self, match_id: int) -> None:
        for m in self._context.get("matches_summary", []):
            if m["match_id"] == match_id:
                m["pre45_sent"] = True
        self._save()

    def get_context_for_bot(self) -> str:
        """Retorna contexto formatado para o system prompt do MoonBot."""
        if not self._context.get("analyses"):
            return ""
        date  = self._context.get("date", "hoje")
        lines = [f"ANÁLISES APEX DO DIA ({date}):"]
        for a in self._context["analyses"]:
            lines.append(
                f"\n-  {a['teams']} ({a['competition']}) às {a['kickoff_local']}\n"
                f"  Mercados indicados: {', '.join(m['market'] for m in a['betting_markets'])}\n"
                f"  Análise: {a['general_analysis'][:200]}..."
            )
        lines.append(
            "\nREGRA: Use APENAS estas informações para responder dúvidas sobre apostas de hoje. "
            "Nunca invente odds ou resultados."
        )
        return "\n".join(lines)

    def get_pending_pre45(self) -> List[dict]:
        """Retorna partidas que ainda não receberam análise pré-45min."""
        now = datetime.now(timezone.utc)
        pending = []
        for a in self._context.get("analyses", []):
            summary = next(
                (m for m in self._context.get("matches_summary", [])
                 if m["match_id"] == a["match_id"]), None
            )
            if summary and summary.get("pre45_sent"):
                continue
            try:
                kickoff = datetime.fromisoformat(a["kickoff_utc"].replace("Z", "+00:00"))
                diff_minutes = (kickoff - now).total_seconds() / 60
                if 40 <= diff_minutes <= 50:
                    pending.append(a)
            except Exception:
                pass
        return pending

    def _save(self) -> None:
        try:
            tmp = DAILY_CONTEXT_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._context, ensure_ascii=False, indent=2))
            tmp.replace(DAILY_CONTEXT_FILE)
        except Exception as e:
            logger.error(f"DailyContextStore save erro: {e}")

    def _load(self) -> None:
        try:
            if DAILY_CONTEXT_FILE.exists():
                self._context = json.loads(DAILY_CONTEXT_FILE.read_text())
        except Exception as e:
            logger.warning(f"DailyContextStore load erro: {e}")


# ─────────────────────────────────────────────────────────────
#  Message Formatter — Formata análises em Markdown para Telegram
# ─────────────────────────────────────────────────────────────

class MatchMessageFormatter:
    """Formata análises de jogos em Markdown rico para Telegram."""

    @staticmethod
    def format_last5(matches: List[dict], team_name: str) -> str:
        if not matches:
            return f"  _{team_name}: dados não disponíveis_"
        lines = [f"  *{team_name}* — últimos 5 jogos:"]
        for m in matches[:5]:
            home  = m.get("homeTeam", {}).get("shortName", "?")
            away  = m.get("awayTeam", {}).get("shortName", "?")
            score = m.get("score", {}).get("fullTime", {})
            home_goals = score.get("home", "?")
            away_goals = score.get("away", "?")
            date_str   = m.get("utcDate", "")[:10]
            comp       = m.get("competition", {}).get("name", "")

            # Determina resultado do time em questão
            team_is_home = home.lower() in team_name.lower() or team_name.lower() in home.lower()
            if home_goals == "?" or away_goals == "?":
                result_icon = "❓"
            elif team_is_home:
                if home_goals > away_goals: result_icon = "✅"
                elif home_goals < away_goals: result_icon = "❌"
                else: result_icon = "🟡"
            else:
                if away_goals > home_goals: result_icon = "✅"
                elif away_goals < home_goals: result_icon = "❌"
                else: result_icon = "🟡"

            lines.append(f"  {result_icon} {date_str} | {home} {home_goals}×{away_goals} {away} _{comp}_")
        return "\n".join(lines)

    @staticmethod
    def format_morning_analysis(analysis: dict) -> str:
        """Formata análise completa da manhã."""
        home = analysis["home_team"]
        away = analysis["away_team"]
        comp = analysis["competition"]
        date = analysis["kickoff_local"]
        last5_home  = analysis.get("last5_home_formatted", "")
        last5_away  = analysis.get("last5_away_formatted", "")
        general     = analysis.get("general_analysis", "")
        markets     = analysis.get("betting_markets", [])

        lines = [
            f"",
            f"⚽ *{home} × {away}*",
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"🏆 {comp}",
            f"📅 {date}",
            f"",
            f"📊 *FORMA RECENTE*",
            last5_home,
            "",
            last5_away,
            "",
            f"🔍 *ANÁLISE DO CONFRONTO*",
            general,
            "",
            f"🎯 *MERCADOS INDICADOS*",
        ]

        for i, m in enumerate(markets, 1):
            market_name  = m.get("market", "")
            tip          = m.get("tip", "")
            reasoning    = m.get("reasoning", "")
            confidence   = m.get("confidence", "")
            conf_icon    = {"Alta": "🟢", "Média": "🟡", "Baixa": "🔴"}.get(confidence, "⚪")
            lines.append(f"")
            lines.append(f"  *{i}. {market_name}*")
            lines.append(f"  💡 Aposta: *{tip}*")
            lines.append(f"  📝 {reasoning}")
            lines.append(f"  {conf_icon} Confiança: {confidence}")

        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        return "\n".join(lines)

    @staticmethod
    def format_pre45_analysis(analysis: dict, lineups: dict) -> str:
        """Formata análise de 45 min antes com escalações."""
        home = analysis["home_team"]
        away = analysis["away_team"]
        comp = analysis["competition"]
        date = analysis["kickoff_local"]
        markets = analysis.get("betting_markets", [])
        refined = analysis.get("refined_analysis", "") or analysis.get("general_analysis", "")

        home_lineup = lineups.get("home_lineup", [])
        away_lineup = lineups.get("away_lineup", [])
        home_absent = lineups.get("home_absent", [])
        away_absent = lineups.get("away_absent", [])
        home_suspended = lineups.get("home_suspended", [])
        away_suspended = lineups.get("away_suspended", [])
        home_returns   = lineups.get("home_returns", [])
        away_returns   = lineups.get("away_returns", [])

        def fmt_players(lst: List[str]) -> str:
            return ", ".join(lst) if lst else "—"

        lines = [
            f"",
            f"⏰ *45 MIN PARA O JOGO!*",
            f"",
            f"⚽ *{home} × {away}*",
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"🏆 {comp}  |  📅 {date}",
            f"",
            f"👕 *ESCALAÇÕES CONFIRMADAS*",
            f"",
            f"  *{home}:*",
            f"  {fmt_players(home_lineup)}",
        ]

        if home_absent:
            lines.append(f"  🚑 Desfalques: {fmt_players(home_absent)}")
        if home_suspended:
            lines.append(f"  🟨 Suspensos: {fmt_players(home_suspended)}")
        if home_returns:
            lines.append(f"  ✅ Retornos: {fmt_players(home_returns)}")

        lines += [
            f"",
            f"  *{away}:*",
            f"  {fmt_players(away_lineup)}",
        ]

        if away_absent:
            lines.append(f"  🚑 Desfalques: {fmt_players(away_absent)}")
        if away_suspended:
            lines.append(f"  🟨 Suspensos: {fmt_players(away_suspended)}")
        if away_returns:
            lines.append(f"  ✅ Retornos: {fmt_players(away_returns)}")

        lines += [
            f"",
            f"🔄 *ANÁLISE REFINADA (com escalações)*",
            refined,
            f"",
            f"🎯 *CONFIRMAÇÃO DE MERCADOS*",
        ]

        for i, m in enumerate(markets, 1):
            market_name = m.get("market", "")
            tip         = m.get("tip", "")
            conf_icon   = {"Alta": "🟢", "Média": "🟡", "Baixa": "🔴"}.get(m.get("confidence", ""), "⚪")
            lines.append(f"  {conf_icon} *{i}. {market_name}* → {tip}")

        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
#  Analysis Engine — Gera análises via LLM com dados reais
# ─────────────────────────────────────────────────────────────

class AnalysisEngine:
    """Gera análises de apostas usando dados reais + LLM."""

    def __init__(self) -> None:
        self.llm = ApexLLM()

    async def generate_morning_analysis(
        self,
        match: dict,
        last5_home: List[dict],
        last5_away: List[dict],
        standings: Optional[dict],
    ) -> Optional[dict]:
        """Gera análise completa da manhã para um jogo."""
        home_id   = match.get("homeTeam", {}).get("id")
        away_id   = match.get("awayTeam", {}).get("id")
        home_name = match.get("homeTeam", {}).get("name", "?")
        away_name = match.get("awayTeam", {}).get("name", "?")
        comp_name = match.get("competition", {}).get("name", "?")
        comp_code = match.get("competition", {}).get("code", "?")
        utc_date  = match.get("utcDate", "")
        match_id  = match.get("id")

        # Converte horário UTC para horário de Brasília (UTC-3)
        try:
            utc_dt    = datetime.fromisoformat(utc_date.replace("Z", "+00:00"))
            brt_dt    = utc_dt.astimezone(timezone(timedelta(hours=-3)))
            kickoff_local = brt_dt.strftime("%d/%m/%Y às %H:%M (Brasília)")
        except Exception:
            kickoff_local = utc_date

        # Formata últimos 5 jogos
        formatter       = MatchMessageFormatter()
        last5_home_fmt  = formatter.format_last5(last5_home, home_name)
        last5_away_fmt  = formatter.format_last5(last5_away, away_name)

        # Monta contexto de standings se disponível
        standings_ctx = ""
        if standings:
            for table in standings.get("standings", []):
                if table.get("type") == "TOTAL":
                    for row in table.get("table", []):
                        team_name_row = row.get("team", {}).get("name", "")
                        if home_name in team_name_row or team_name_row in home_name:
                            standings_ctx += (
                                f"{home_name}: {row['position']}º lugar, "
                                f"{row['points']} pts, {row['won']}V {row['draw']}E {row['lost']}D\n"
                            )
                        if away_name in team_name_row or team_name_row in away_name:
                            standings_ctx += (
                                f"{away_name}: {row['position']}º lugar, "
                                f"{row['points']} pts, {row['won']}V {row['draw']}E {row['lost']}D\n"
                            )

        # Formata histórico dos últimos 5 para o prompt
        def fmt_matches_for_prompt(matches: List[dict], team: str) -> str:
            lines = []
            for m in matches[:5]:
                home_t  = m.get("homeTeam", {}).get("name", "?")
                away_t  = m.get("awayTeam", {}).get("name", "?")
                score   = m.get("score", {}).get("fullTime", {})
                hg      = score.get("home", "?")
                ag      = score.get("away", "?")
                date_m  = m.get("utcDate", "")[:10]
                lines.append(f"  {date_m}: {home_t} {hg}x{ag} {away_t}")
            return "\n".join(lines) if lines else "  (sem dados)"

        system_prompt = """Você é um analista profissional de apostas esportivas de futebol.
Sua função é gerar análises REAIS e PRECISAS baseadas exclusivamente nos dados fornecidos.
NUNCA invente informações. Se não souber algo com certeza, indique isso claramente.
Responda SEMPRE em português do Brasil.
Seja direto, objetivo e profissional."""

        user_prompt = f"""Gere uma análise completa para o seguinte jogo:

JOGO: {home_name} × {away_name}
COMPETIÇÃO: {comp_name}
DATA/HORA: {kickoff_local}

ÚLTIMOS 5 JOGOS — {home_name}:
{fmt_matches_for_prompt(last5_home, home_name)}

ÚLTIMOS 5 JOGOS — {away_name}:
{fmt_matches_for_prompt(last5_away, away_name)}

CLASSIFICAÇÃO ATUAL:
{standings_ctx if standings_ctx else "Dados não disponíveis"}

Por favor, gere:
1. Uma análise geral do confronto (3-4 parágrafos) considerando:
   - Força geral das equipes e momento atual na temporada
   - Estilo de jogo de cada time
   - Se é um clássico regional ou histórico
   - Se a competição tem "peso de Copa" ou é Liga/Campeonato
   - Mudanças recentes de técnico se relevante
   
2. Exatamente 3 mercados de apostas recomendados, cada um com:
   - Nome do mercado
   - Aposta específica (ex: "Over 2.5 Gols", "Vitória do {home_name}", "Ambos Marcam - Sim")
   - Justificativa em 2-3 linhas
   - Nível de confiança: Alta / Média / Baixa

Responda em formato JSON VÁLIDO com a seguinte estrutura:
{{
  "general_analysis": "texto da análise geral aqui",
  "betting_markets": [
    {{
      "market": "Nome do mercado",
      "tip": "Aposta específica",
      "reasoning": "Justificativa aqui",
      "confidence": "Alta/Média/Baixa"
    }}
  ]
}}

IMPORTANTE: Retorne APENAS o JSON, sem texto extra antes ou depois."""

        llm_response = await self.llm.generate(user_prompt, system_prompt)

        if not llm_response:
            logger.error(f"LLM retornou resposta vazia para {home_name} × {away_name}")
            return None

        # Parse do JSON
        try:
            # Remove possíveis ```json ... ``` wraps
            clean = llm_response.strip()
            if clean.startswith("```"):
                parts = clean.split("```")
                clean = parts[1] if len(parts) > 1 else clean
                if clean.startswith("json"):
                    clean = clean[4:]
                clean = clean.strip()
            parsed = json.loads(clean)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse erro para {home_name} × {away_name}: {e}\nResposta: {llm_response[:300]}")
            return None

        return {
            "match_id":            match_id,
            "home_team":           home_name,
            "away_team":           away_name,
            "teams":               f"{home_name} × {away_name}",
            "competition":         comp_name,
            "competition_code":    comp_code,
            "kickoff_utc":         utc_date,
            "kickoff_local":       kickoff_local,
            "last5_home_formatted": last5_home_fmt,
            "last5_away_formatted": last5_away_fmt,
            "general_analysis":    parsed.get("general_analysis", ""),
            "betting_markets":     parsed.get("betting_markets", []),
        }

    async def generate_pre45_analysis(
        self,
        analysis: dict,
        match_detail: Optional[dict],
        webmcp_lineups: Optional[dict] = None,
    ) -> dict:
        """Refina análise com escalações confirmadas 45 min antes."""
        home_name = analysis["home_team"]
        away_name = analysis["away_team"]

        # Extrai lineups do match detail
        lineups = self._extract_lineups(match_detail, home_name, away_name)

        # P9: completa com lineups do WebMCP quando a fonte principal vier vazia
        if webmcp_lineups:
            merged = dict(lineups)
            for key, value in webmcp_lineups.items():
                current = merged.get(key)
                if key not in merged or not current:
                    merged[key] = value
            lineups = merged

        lineup_ctx = ""
        if lineups.get("home_lineup"):
            lineup_ctx += f"\n{home_name} TITULARES: {', '.join(lineups['home_lineup'][:11])}"
        if lineups.get("away_lineup"):
            lineup_ctx += f"\n{away_name} TITULARES: {', '.join(lineups['away_lineup'][:11])}"

        absent_ctx = ""
        if lineups.get("home_absent"):
            absent_ctx += f"\n{home_name} SEM: {', '.join(lineups['home_absent'])}"
        if lineups.get("home_suspended"):
            absent_ctx += f"\n{home_name} SUSPENSOS: {', '.join(lineups['home_suspended'])}"
        if lineups.get("home_returns"):
            absent_ctx += f"\n{home_name} RETORNOS: {', '.join(lineups['home_returns'])}"
        if lineups.get("away_absent"):
            absent_ctx += f"\n{away_name} SEM: {', '.join(lineups['away_absent'])}"
        if lineups.get("away_suspended"):
            absent_ctx += f"\n{away_name} SUSPENSOS: {', '.join(lineups['away_suspended'])}"
        if lineups.get("away_returns"):
            absent_ctx += f"\n{away_name} RETORNOS: {', '.join(lineups['away_returns'])}"

        # Sem nenhuma informação de escalação, mantém o aviso original
        if not lineup_ctx and not absent_ctx:
            analysis["refined_analysis"] = (
                analysis["general_analysis"] +
                "\n\n_⚠️ Escalações ainda não confirmadas pela fonte de dados._"
            )
            return {"analysis": analysis, "lineups": lineups}

        system_prompt = """Você é um analista profissional de apostas esportivas.
Refine a análise de aposta considerando as escalações confirmadas.
Avalie o impacto tático dos titulares escalados e dos possíveis desfalques.
Seja objetivo e direto. Responda em português do Brasil."""

        escalacoes_ctx = lineup_ctx
        if absent_ctx:
            escalacoes_ctx += f"\n\nDESFALQUES/RETORNOS:{absent_ctx}"

        source_label = lineups.get("source", "fonte desconhecida")
        user_prompt = f"""Análise original do jogo {home_name} × {away_name}:
{analysis['general_analysis'][:500]}

ESCALAÇÕES CONFIRMADAS (fonte: {source_label}):{escalacoes_ctx}

Com base nestas informações, escreva um parágrafo refinando a análise.
Considere o impacto dos titulares escalados, da formação do meio-campo
e se as escalações confirmam ou alteram as indicações anteriores.
Máximo 5 linhas. Responda apenas o texto, sem JSON."""

        refined = await self.llm.generate(user_prompt, system_prompt)
        analysis["refined_analysis"] = refined or analysis["general_analysis"]

        return {"analysis": analysis, "lineups": lineups}

    def _extract_lineups(self, match_detail: Optional[dict], home_name: str, away_name: str) -> dict:
        """Extrai escalações do match detail da API."""
        lineups = {
            "home_lineup": [],
            "away_lineup": [],
            "home_absent": [],
            "away_absent": [],
            "home_suspended": [],
            "away_suspended": [],
            "home_returns": [],
            "away_returns": [],
        }

        if not match_detail:
            return lineups

        # football-data.org v4 não fornece escalações via API gratuita
        # mas fornece informações de cabeçalho; escalações detalhadas
        # virão de web scraping ou API paga quando disponível
        # Por ora, retornamos estrutura vazia e indicamos no texto
        return lineups


async def _fetch_webmcp_lineups(
    home: str,
    away: str,
    competition: str = "",
) -> dict:
    """
    Busca escalações via WebMCP Sports Layer sem bloquear o fluxo principal.
    Retorna um dict compatível com format_pre45_analysis().
    """
    lineups = {
        "home_lineup": [],
        "away_lineup": [],
        "home_absent": [],
        "away_absent": [],
        "home_suspended": [],
        "away_suspended": [],
        "home_returns": [],
        "away_returns": [],
    }

    try:
        from skills.webmcp.sports.lineup_detector import LineupDetector

        detector = LineupDetector()
        result = await detector.detect_lineups(home, away, competition=competition)

        if result.matches:
            match = result.matches[0]
            if match.home_lineup:
                lineups["home_lineup"] = [p.name for p in match.home_lineup.starters[:11]]
                if match.home_lineup.formation:
                    lineups["home_formation"] = match.home_lineup.formation
            if match.away_lineup:
                lineups["away_lineup"] = [p.name for p in match.away_lineup.starters[:11]]
                if match.away_lineup.formation:
                    lineups["away_formation"] = match.away_lineup.formation
            if lineups["home_lineup"] or lineups["away_lineup"]:
                lineups["source"] = result.raw_data.get("lineup_source", result.provider)
                return lineups

        lineup_news = [n for n in result.news if n.mentions_lineup]
        if lineup_news:
            lineups["news_articles"] = [
                {"title": n.title, "url": n.url, "source": n.source}
                for n in lineup_news[:3]
            ]
            lineups["source"] = result.raw_data.get("lineup_source", result.provider)
            return lineups
    except Exception as e:
        logger.warning(f"_fetch_webmcp_lineups falhou ({home} × {away}): {e}")

    return {}


# ─────────────────────────────────────────────────────────────
#  ApexOracle — Orquestrador principal
# ─────────────────────────────────────────────────────────────

class ApexOracle:
    """
    Motor principal do sistema APEX.
    Orquestra: coleta de dados → análise → formatação → envio via Telegram.
    
    Ciclo diário:
      07:30 → run_morning_cycle()   (análises do dia)
      cada hora → check_pre45()    (análises 45 min antes de cada jogo)
    """

    def __init__(self) -> None:
        self.football = FootballDataClient()
        self.telegram = TelegramSender()
        self.engine   = AnalysisEngine()
        self.context  = DailyContextStore()
        self.formatter = MatchMessageFormatter()

    async def run_morning_cycle(self) -> None:
        """
        Ciclo da manhã: busca jogos do dia, gera análises completas,
        envia tudo via Telegram.
        """
        logger.info("ApexOracle: iniciando ciclo matinal")
        today = datetime.now().strftime("%Y-%m-%d")

        # Aviso de início
        await self.telegram.send(
            "🌅 *APEX BETTING ORACLE — Análises do Dia*\n"
            f"📅 {datetime.now().strftime('%d/%m/%Y')}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "_Buscando jogos e gerando análises... aguarde._"
        )

        # 1. Busca jogos de hoje
        matches = await self.football.get_matches_today()

        if not matches:
            await self.telegram.send(
                "⚠️ *APEX*: Nenhum jogo encontrado nas ligas monitoradas para hoje.\n"
                "_Verifique a configuração das ligas ou a FOOTBALL_DATA_API_KEY._"
            )
            logger.warning("ApexOracle: zero jogos encontrados para hoje")
            return

        logger.info(f"ApexOracle: {len(matches)} jogos encontrados, gerando análises...")

        analyses = []
        errors   = []

        for match in matches:
            home_id   = match.get("homeTeam", {}).get("id")
            away_id   = match.get("awayTeam", {}).get("id")
            comp_code = match.get("competition", {}).get("code", "")
            home_name = match.get("homeTeam", {}).get("name", "?")
            away_name = match.get("awayTeam", {}).get("name", "?")

            try:
                # Busca dados em paralelo
                last5_home, last5_away, standings = await asyncio.gather(
                    self.football.get_last_5_matches(home_id),
                    self.football.get_last_5_matches(away_id),
                    self.football.get_standings(comp_code),
                    return_exceptions=True
                )

                # Trata exceções do gather
                if isinstance(last5_home, Exception): last5_home = []
                if isinstance(last5_away, Exception): last5_away = []
                if isinstance(standings, Exception):  standings  = None

                analysis = await self.engine.generate_morning_analysis(
                    match, last5_home, last5_away, standings
                )

                if analysis:
                    analyses.append(analysis)
                else:
                    errors.append(f"{home_name} × {away_name}")

                # Rate limit: 1 req/s na API gratuita
                await asyncio.sleep(1.2)

            except Exception as e:
                logger.error(f"ApexOracle erro processando {home_name} × {away_name}: {e}")
                errors.append(f"{home_name} × {away_name}")

        # Salva contexto do dia (Bot usará para responder dúvidas)
        self.context.save_daily_analyses(today, analyses)

        # Envia cabeçalho
        total_games = len(analyses)
        await self.telegram.send(
            f"✅ *{total_games} ANÁLISE{'S' if total_games != 1 else ''} PRONTA{'S' if total_games != 1 else ''}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )

        # Envia cada análise
        for analysis in analyses:
            msg = self.formatter.format_morning_analysis(analysis)
            await self.telegram.send(msg)
            await asyncio.sleep(0.5)

        # Reporta erros se houver
        if errors:
            await self.telegram.send(
                f"⚠️ *Não foi possível analisar:* {', '.join(errors)}\n"
                "_Dados insuficientes da API para estes jogos._"
            )

        # Rodapé
        await self.telegram.send(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🤖 _Enviarei análise refinada com escalações 45 min antes de cada jogo._\n"
            "💬 _Me pergunte sobre qualquer indicação!_"
        )

        logger.info(f"ApexOracle: ciclo matinal concluído. {total_games} análises enviadas.")

    async def check_pre45(self) -> None:
        """
        Verifica se algum jogo começa em ~45 min.
        Se sim, busca escalações e envia análise refinada.
        """
        pending = self.context.get_pending_pre45()
        if not pending:
            return

        for analysis in pending:
            match_id  = analysis["match_id"]
            home_name = analysis["home_team"]
            away_name = analysis["away_team"]

            logger.info(f"ApexOracle: enviando análise pré-45 para {home_name} × {away_name}")

            try:
                match_detail = await self.football.get_match_detail(match_id)
                webmcp_lineups = await _fetch_webmcp_lineups(
                    home_name, away_name, analysis.get("competition", "")
                )
                result = await self.engine.generate_pre45_analysis(
                    analysis,
                    match_detail,
                    webmcp_lineups=webmcp_lineups,
                )

                msg = self.formatter.format_pre45_analysis(
                    result["analysis"], result["lineups"]
                )
                sent = await self.telegram.send(msg)
                if sent:
                    self.context.mark_pre45_sent(match_id)
            except Exception as e:
                logger.error(f"ApexOracle check_pre45 erro {home_name} × {away_name}: {e}")

    async def run_autonomous_loop(self) -> None:
        """
        Loop autônomo principal. Roda indefinidamente.
        - Verifica se é hora do ciclo matinal (07:30)
        - A cada 5 minutos verifica jogos que começam em ~45 min
        """
        logger.info("ApexOracle: loop autônomo iniciado")
        from agents.apex.lineup_poller import APEXLineupPoller
        asyncio.create_task(APEXLineupPoller(self.context, self.telegram).start())
        morning_sent_today = ""  # data do último envio matinal

        while True:
            try:
                now = datetime.now()
                today_str = now.strftime("%Y-%m-%d")

                # Ciclo matinal: 07:30
                if now.hour == 7 and now.minute == 30 and morning_sent_today != today_str:
                    morning_sent_today = today_str
                    asyncio.create_task(self.run_morning_cycle())

                # Check pré-45 min: a cada 5 minutos
                await self.check_pre45()

                # Dorme 60 segundos entre verificações
                await asyncio.sleep(60)

            except asyncio.CancelledError:
                logger.info("ApexOracle: loop autônomo cancelado")
                break
            except Exception as e:
                logger.error(f"ApexOracle loop erro: {e}")
                await asyncio.sleep(60)
