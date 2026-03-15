import os
import requests
import json

class LogoFetcher:
    """
    Fetcher Agent: Searches and downloads official sports club logos.
    Currently configured for European Football using clearbit or direct CDN links.
    """
    def __init__(self, output_dir="assets/logos"):
        self.output_dir = output_dir
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
    def fetch_logo(self, team_name):
        print(f"[*] Fetching logo for: {team_name}")
        # Simplified mapping for demonstration
        team_map = {
            "Manchester City": "manchester-city-fc",
            "West Ham": "west-ham-united-fc",
            "Arsenal": "arsenal-fc",
            "Everton": "everton-fc"
        }
        
        slug = team_map.get(team_name, team_name.lower().replace(" ", "-"))
        # Using a reliable open source for logos or Clearbit API
        url = f"https://logo.clearbit.com/{slug}.com" 
        # Fallback to football-data.org style if we had IDs
        
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                filepath = os.path.join(self.output_dir, f"{slug}.png")
                with open(filepath, "wb") as f:
                    f.write(response.content)
                print(f"[+] Successfully saved logo to {filepath}")
                return filepath
            else:
                print(f"[!] Failed to fetch logo for {team_name} (Status: {response.status_code})")
                return None
        except Exception as e:
            print(f"[!] Error fetching logo: {e}")
            return None

if __name__ == "__main__":
    fetcher = LogoFetcher()
    teams = ["Manchester City", "West Ham", "Arsenal", "Everton"]
    for team in teams:
        fetcher.fetch_logo(team)
