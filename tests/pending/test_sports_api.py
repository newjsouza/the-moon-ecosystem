import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))

from agents.sports.api_client import FootballDataClient

load_dotenv()

def test_api():
    print("Testing Football-data.org API...")
    try:
        client = FootballDataClient()
        # Test getting competitions
        comps = client.get_competitions()
        print(f"Successfully fetched {len(comps)} competitions:")
        for c in comps:
            print(f"- {c['name']} (ID: {c['id']}, Area: {c['area']['name']})")
        
        # Test getting matches for today
        from datetime import datetime, timedelta
        today = datetime.now().strftime("%Y-%m-%d")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        
        matches_today = client.get_matches(date_from=today, date_to=today)
        print(f"\nSuccessfully fetched {len(matches_today)} matches for today ({today}).")
        for m in matches_today[:5]:
             print(f"- {m['homeTeam']['name']} vs {m['awayTeam']['name']} ({m['status']})")

        matches_tomorrow = client.get_matches(date_from=tomorrow, date_to=tomorrow)
        print(f"\nSuccessfully fetched {len(matches_tomorrow)} matches for tomorrow ({tomorrow}).")
        for m in matches_tomorrow[:5]:
             print(f"- {m['homeTeam']['name']} vs {m['awayTeam']['name']} ({m['status']})")
             
    except Exception as e:
        print(f"API Test Failed: {e}")

if __name__ == "__main__":
    test_api()
