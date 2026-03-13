import os
import requests
from typing import Dict, List, Optional
from dotenv import load_dotenv

load_dotenv()

class FootballDataClient:
    """
    Client for Football-data.org API
    """
    BASE_URL = "https://api.football-data.org/v4"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("FOOTBALL_DATA_API_KEY")
        if not self.api_key:
            raise ValueError("FOOTBALL_DATA_API_KEY not found in environment")
        
        self.headers = {
            "X-Auth-Token": self.api_key
        }

    def get_competitions(self) -> List[Dict]:
        """Get list of available competitions"""
        url = f"{self.BASE_URL}/competitions"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json().get("competitions", [])

    def get_matches(self, competition_id: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None) -> List[Dict]:
        """Get matches for competition and/or date range"""
        url = f"{self.BASE_URL}/matches"
        params = {}
        if competition_id:
            url = f"{self.BASE_URL}/competitions/{competition_id}/matches"
        if date_from:
            params["dateFrom"] = date_from
        if date_to:
            params["dateTo"] = date_to
            
        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        return response.json().get("matches", [])

    def get_match(self, match_id: int) -> Dict:
        """Get specific match details"""
        url = f"{self.BASE_URL}/matches/{match_id}"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def get_odds(self, match_id: int) -> Dict:
        """Get odds for a specific match (Note: Free tier might have limited odds)"""
        url = f"{self.BASE_URL}/matches/{match_id}"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json().get("odds", {})
