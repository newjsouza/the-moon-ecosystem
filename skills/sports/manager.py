import logging
import asyncio
import re
from datetime import datetime, timedelta
from typing import Dict, List, Any
from .api_client import FootballDataClient
from .analyzer import SportsAnalyzer
from .scraper import SofaScoreScraper
from ..skill_base import SkillBase

logger = logging.getLogger(__name__)

class SportsManager(SkillBase):
    """
    Orchestrates sports data collection, analysis, and alerting.
    """
    
    def __init__(self, banca_total: float = 1000.0):
        super().__init__(name="sports")
        self.api_client = FootballDataClient()
        self.analyzer = SportsAnalyzer(banca_total=banca_total)
        self.scraper = SofaScoreScraper()
        self.active_monitors = {}

    async def get_upcoming_opportunities(self, days_offset: int = 0) -> List[Dict]:
        """
        Fetches upcoming matches for a specific day offset (0=today, 1=tomorrow).
        """
        target_date = (datetime.now() + timedelta(days=days_offset)).strftime("%Y-%m-%d")
        
        try:
            logger.info(f"Fetching matches from API for {target_date}...")
            matches = self.api_client.get_matches(date_from=target_date, date_to=target_date)
            opportunities = []
            
            for match in matches:
                if match.get("status") in ["SCHEDULED", "TIMED", "LIVE", "IN_PLAY"]:
                    opp = {
                        "id": match["id"],
                        "teams": f"{match['homeTeam']['name']} vs {match['awayTeam']['name']}",
                        "homeTeam": match['homeTeam']['name'],
                        "awayTeam": match['awayTeam']['name'],
                        "utcDate": match["utcDate"],
                        "competition": match["competition"]["name"],
                        "status": match["status"],
                        "source": "Football-data.org"
                    }
                    opportunities.append(opp)
            
            if not opportunities and days_offset == 0:
                logger.info("API returned 0 matches. Attempting SofaScore scraper fallback...")
                try:
                    scrape_results = await self.scraper.get_realtime_data("https://www.sofascore.com/")
                    if scrape_results and not scrape_results.get("error"):
                        # If we got something from the scraper, maybe we can find a way to list games
                        # For now, we provide the scraper title as a hint if no matches found
                        logger.info(f"Scraper returned info: {scrape_results.get('title')}")
                except Exception as se:
                    logger.error(f"Scraper fallback failed: {se}")
                
            return opportunities
        except Exception as e:
            logger.error(f"Error fetching opportunities for {target_date}: {e}")
            return []

    async def analyze_match_live(self, match_id: int):
        """
        Deep analysis for a match close to starting.
        """
        try:
            # 1. Get match info from API
            match_data = self.api_client.get_matches(match_id=match_id)
            if not match_data:
                return {"error": "Match not found in API"}
            
            home_team = match_data['homeTeam']['name']
            away_team = match_data['awayTeam']['name']
            
            # 2. Get real-time stats from scraper
            logger.info(f"Searching for live data for {home_team} vs {away_team}...")
            match_url = await self.scraper.find_match_url(home_team, away_team)
            live_data = {}
            if match_url:
                live_data = await self.scraper.get_realtime_data(match_url)
            
            # 3. Use LLM/Groq for qualitative synthesis
            # (Note: Orchestrator would ideally handle this, but here we call LlmAgent directly for speed)
            from agents.llm import LlmAgent
            llm = LlmAgent()
            reasoning_prompt = f"""
            Analyze the following match for a betting opportunity:
            Teams: {home_team} vs {away_team}
            Live Data: {live_data}
            API Odds Data: {match_data.get('odds')}
            
            Provide a qualitative score from 1-10 for the 'Home Win' probability based on these factors.
            Return ONLY the number.
            """
            llm_result = await llm.execute(reasoning_prompt)
            qualitative_score = 5.0
            if llm_result.success:
                try:
                    qualitative_score = float(re.search(r'\d+', llm_result.data['response']).group())
                except:
                    pass

            # 4. Final Validation via Analyzer (APEX + Kelly)
            analysis = self.analyzer.validate_bet(
                match_data=match_data,
                live_data=live_data,
                qualitative_score=qualitative_score
            )
            
            return {
                "match": f"{home_team} vs {away_team}",
                "qualitative_score": qualitative_score,
                "analysis": analysis,
                "recommended_action": "BET" if analysis.get("kelly_stake", 0) > 0 else "SKIP"
            }
        except Exception as e:
            logger.error(f"Error in analyze_match_live: {e}")
            return {"error": str(e)}

    async def run_monitoring_loop(self):
        """
        Main loop to monitor matches and send alerts.
        """
        logger.info("Sports Monitoring Loop STARTED.")
        while True:
            try:
                # 1. Find upcoming matches for the next 4 hours
                target_date = datetime.now().strftime("%Y-%m-%d")
                matches = self.api_client.get_matches(date_from=target_date, date_to=target_date)
                
                for match in matches:
                    match_time = datetime.strptime(match['utcDate'], "%Y-%m-%dT%H:%M:%SZ")
                    time_to_start = match_time - datetime.utcnow()
                    
                    # If game is within 60 mins and we haven't analyzed it yet
                    if timedelta(0) < time_to_start < timedelta(minutes=60):
                        if match['id'] not in self.active_monitors:
                            logger.info(f"Triggering pre-game analysis for {match['homeTeam']['name']}...")
                            result = await self.analyze_match_live(match['id'])
                            self.active_monitors[match['id']] = result
                            # Alert logic (e.g. Telegram) would go here
                            logger.info(f"Analysis result for {match['id']}: {result['recommended_action']}")

                await asyncio.sleep(300) # Check every 5 minutes
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(60)
