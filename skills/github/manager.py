"""
manager.py - GitHub Skill Manager for The Moon
Orchestrates GitHub operations.
"""

import logging
from typing import Dict, Any, List
from skills.skill_base import SkillBase
from .service import GitHubService

logger = logging.getLogger("moon.skills.github")

class GitHubManager(SkillBase):
    """
    Skill to manage GitHub repositories and issues.
    This skill acts as a proxy to the GitHub MCP server.
    """
    
    def __init__(self, default_owner: str = "newjsouza"):
        super().__init__(name="github")
        self.service = GitHubService(owner=default_owner)
        self.default_repo = "The-Moon"

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute GitHub actions.
        Expected actions: 'list_repos', 'create_issue', 'get_repo_info'.
        """
        action = params.get("action")
        repo = params.get("repo", self.default_repo)
        owner = params.get("owner", self.service.owner)
        
        try:
            if action == "list_repos":
                # Implementation will be handled by the Agent using MCP tools
                return {"success": True, "message": "List repositories action requested. Use MCP search_repositories."}
                
            elif action == "create_issue":
                title = params.get("title")
                body = params.get("body", "")
                if not title:
                    return {"success": False, "error": "Title is required for issues"}
                
                # Proxy to MCP: mcp_github-mcp-server_issue_write
                return {
                    "success": True, 
                    "proxy_to": "mcp_github-mcp-server_issue_write",
                    "args": {
                        "owner": owner,
                        "repo": repo,
                        "title": title,
                        "body": body,
                        "method": "create"
                    }
                }
                
            elif action == "get_repo_info":
                return {
                    "success": True,
                    "proxy_to": "mcp_github-mcp-server_search_repositories",
                    "args": {"query": f"repo:{owner}/{repo}"}
                }
                
            else:
                return {"success": False, "error": f"Unknown action: {action}"}
                
        except Exception as e:
            logger.error(f"Error executing GitHub action {action}: {e}")
            return {"success": False, "error": str(e)}
