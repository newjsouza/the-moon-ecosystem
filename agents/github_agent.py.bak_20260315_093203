"""
agents/github_agent.py
Specialized agent for GitHub and Terminal automation.
"""
from core.agent_base import AgentBase, TaskResult, AgentPriority
from utils.github_utils import GithubManager
from utils.logger import setup_logger
import os

class GithubAgent(AgentBase):
    def __init__(self):
        super().__init__()
        self.priority = AgentPriority.MEDIUM
        self.description = "Autonomous GitHub & Terminal Operator"
        self.logger = setup_logger("GithubAgent")
        self.github = GithubManager()

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        action = kwargs.get("action", "monitor")
        repo_name = kwargs.get("repo", "browserbase/stagehand") # Example target
        
        self.logger.info(f"Executing GitHub action: {action} on {repo_name}")

        try:
            if action == "monitor":
                return await self._monitor_repo(repo_name)
            elif action == "commit":
                message = kwargs.get("message", "Autonomous update from The Moon")
                return await self._commit_changes(message)
            elif action == "search":
                query = kwargs.get("query", "topic:ai-agents")
                return await self._search_trends(query)
            else:
                return TaskResult(success=False, error=f"Unknown action: {action}")
        except Exception as e:
            self.logger.error(f"GitHub operation failed: {e}")
            return TaskResult(success=False, error=str(e))

    async def _monitor_repo(self, repo_full_name):
        owner, repo = repo_full_name.split("/")
        commits = self.github.get_latest_commits(owner, repo)
        if commits:
            latest = commits[0]
            summary = {
                "latest_commit_sha": latest["sha"],
                "message": latest["commit"]["message"],
                "author": latest["commit"]["author"]["name"]
            }
            return TaskResult(success=True, data=summary)
        return TaskResult(success=False, error="No commits found")

    async def _commit_changes(self, message):
        # Stage all changes
        res_add = self.github.run_git_command(["add", "."])
        if not res_add["success"]: return TaskResult(success=False, error=res_add["error"])
        
        # Commit
        res_commit = self.github.run_git_command(["commit", "-m", message])
        return TaskResult(success=res_commit["success"], data=res_commit)

    async def _search_trends(self, query):
        repos = self.github.search_trending_repos(query)
        summary = [{"name": r["full_name"], "stars": r["stargazers_count"], "desc": r["description"]} for r in repos[:5]]
        return TaskResult(success=True, data={"trending": summary})
