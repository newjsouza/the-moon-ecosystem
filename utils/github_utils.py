"""
utils/github_utils.py
GitHub API and Git operations utility.
"""
import os
import subprocess
import requests
from utils.logger import setup_logger

logger = setup_logger("GithubUtils")

class GithubManager:
    def __init__(self, token=None):
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.base_url = "https://api.github.com"
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
        }
        if self.token:
            self.headers["Authorization"] = f"token {self.token}"

    def search_trending_repos(self, query="topic:ai-agents", sort="stars"):
        """Search for repositories matching a query."""
        url = f"{self.base_url}/search/repositories"
        params = {"q": query, "sort": sort, "order": "desc"}
        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json().get("items", [])
        except Exception as e:
            logger.error(f"Failed to search GitHub: {e}")
            return []

    def get_latest_commits(self, owner, repo, count=5):
        """Fetch latest commits from a repository."""
        url = f"{self.base_url}/repos/{owner}/{repo}/commits"
        params = {"per_page": count}
        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch commits for {owner}/{repo}: {e}")
            return []

    def run_git_command(self, cmd, cwd=None):
        """Run a raw git command in the specified directory."""
        try:
            result = subprocess.run(
                ["git"] + cmd,
                cwd=cwd or os.getcwd(),
                capture_output=True,
                text=True,
                check=True
            )
            return {"success": True, "output": result.stdout}
        except subprocess.CalledProcessError as e:
            logger.error(f"Git command failed: {e.stderr}")
            return {"success": False, "error": e.stderr}

if __name__ == "__main__":
    # Quick test
    gm = GithubManager()
    repos = gm.search_trending_repos()
    print(f"Found {len(repos)} repos. Top one: {repos[0]['full_name'] if repos else 'None'}")
