import asyncio
import re
import urllib.parse
from playwright.async_api import async_playwright
from typing import Dict, List, Optional

class SofaScoreScraper:
    """
    Scraper for SofaScore to get real-time match data and lineups.
    """
    BASE_URL = "https://www.sofascore.com"

    async def get_realtime_data(self, match_url: str) -> Dict:
        """
        Scrapes real-time statistics and lineups from a SofaScore match page.
        """
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            # Set a realistic user agent
            await page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
            })

            try:
                await page.goto(match_url, wait_until="networkidle")
                
                # 1. Capture basic info
                title = await page.title()
                
                # 2. Extract Data from SofaScore's JSON structure if possible
                # Often available in window.__INITIAL_STATE__ or via XHR interception
                # For simplicity here, we use DOM selectors based on common SofaScore structure
                
                # Possession (Example selector - may vary)
                possession_home = "50%"
                possession_away = "50%"
                try:
                    # Look for elements with text "Possession"
                    pos_row = page.get_by_text("Possession").first
                    if await pos_row.is_visible():
                        # This usually sits in a parent container with values on both sides
                        values = await page.locator(".sc-dcJsrf").all_inner_texts() # generic Sofascore component class
                        if len(values) >= 2:
                            possession_home = values[0]
                            possession_away = values[1]
                except:
                    pass

                # Lineups
                lineups = {"home": [], "away": []}
                try:
                    # Switch to lineups tab if needed
                    await page.get_by_text("Lineups").click()
                    await asyncio.sleep(1)
                    
                    # Extract players
                    players = await page.locator(".sc-fqkvVR").all_inner_texts() # generic player item class
                    # Parse into home/away (usually split by a header or container)
                    lineups["raw"] = players[:22] # Top 22 usually starters
                except:
                    pass

                # Live Odds
                live_odds = {}
                try:
                    odds_elements = await page.locator("[data-testimonial-id='odds']").all_inner_texts()
                    if odds_elements:
                        live_odds["main"] = odds_elements
                except:
                    pass

                return {
                    "title": title,
                    "url": match_url,
                    "possession": {"home": possession_home, "away": possession_away},
                    "lineups": lineups,
                    "live_odds": live_odds,
                    "timestamp": asyncio.get_event_loop().time()
                }
            except Exception as e:
                return {"error": str(e)}
            finally:
                await browser.close()

    async def find_match_url(self, team_home: str, team_away: str) -> Optional[str]:
        """
        Searches for a match URL on SofaScore by team names.
        """
        search_query = f"{team_home} {team_away}"
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                # Use Google or SofaScore search
                url = f"https://www.google.com/search?q=site:sofascore.com+{search_query.replace(' ', '+')}"
                await page.goto(url)
                # Take the first sofascore link
                link = await page.get_by_role("link", name=re.compile("sofascore.com/.*", re.IGNORECASE)).first.get_attribute("href")
                if link and "sofascore.com" in link:
                    # Basic sanitization
                    if "google.com" in link: # sometimes google search results have wrappers
                        import urllib.parse
                        parsed = urllib.parse.urlparse(link)
                        qs = urllib.parse.parse_qs(parsed.query)
                        if 'q' in qs:
                            link = qs['q'][0]
                    return link
                return None
            except Exception:
                return None
            finally:
                await browser.close()
