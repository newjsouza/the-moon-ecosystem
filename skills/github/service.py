"""
service.py - GitHub Service integration
Interfaces with the GitHub MCP server tools.
"""

import logging
from typing import List, Optional, Dict, Any
from .models import GitHubRepo, GitHubIssue, IssueState

logger = logging.getLogger(__name__)

class GitHubService:
    """
    Service to interact with GitHub using the MCP tools.
    Note: This service relies on the MCP server being active in the environment.
    """
    
    def __init__(self, owner: str):
        self.owner = owner

    async def list_repositories(self) -> List[GitHubRepo]:
        """Lists user repositories using MCP search tool"""
        # We'll use the search_repositories tool via the orchestrator/agent
        # In this context, we'll assume the manager handles the actual MCP tool call
        # but the service layer structures the data.
        pass

    def parse_repo(self, data: Dict[str, Any]) -> GitHubRepo:
        """Parses repository data from GitHub API/MCP format"""
        return GitHubRepo(
            id=str(data.get("id", "")),
            name=data.get("name", ""),
            full_name=data.get("full_name", ""),
            owner=data.get("owner", {}).get("login", self.owner) if isinstance(data.get("owner"), dict) else self.owner,
            html_url=data.get("html_url", ""),
            description=data.get("description"),
            private=data.get("private", False),
            stargazers_count=data.get("stargazers_count", 0),
            open_issues_count=data.get("open_issues_count", 0),
            language=data.get("language")
        )

    def parse_issue(self, data: Dict[str, Any]) -> GitHubIssue:
        """Parses issue data from GitHub API/MCP format"""
        return GitHubIssue(
            id=str(data.get("id", "")),
            number=data.get("number", 0),
            title=data.get("title", ""),
            body=data.get("body"),
            state=IssueState(data.get("state", "open")),
            author=data.get("user", {}).get("login", "") if isinstance(data.get("user"), dict) else "",
            labels=[l["name"] for l in data.get("labels", []) if "name" in l],
            html_url=data.get("html_url", "")
        )
