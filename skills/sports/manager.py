import logging
import asyncio
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
        # 1. Get detailed data from API
        # 2. Get real-time stats from scraper
        # 3. Use LLM/Groq to synthesize and provide probability
        # 4. Use Analyzer for final bet validation
        pass

    async def run_monitoring_loop(self):
        """
        Main loop to monitor matches and send alerts.
        """
        while True:
            logger.info("Checking for new betting opportunities...")
            # Logic to check time, trigger analysis 1h before game, etc.
            await asyncio.sleep(3600) # Check every hour
