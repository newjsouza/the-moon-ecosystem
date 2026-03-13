"""
core/github_workflow.py
Orchestrates GitHub-related background tasks.
"""
import asyncio
from agents.github_agent import GithubAgent
from utils.logger import setup_logger

logger = setup_logger("GithubWorkflow")

class MoonGithubMonitor:
    def __init__(self):
        self.agent = GithubAgent()
        self.targets = [] # Repositories to monitor

    def add_target(self, repo_full_name):
        if repo_full_name not in self.targets:
            self.targets.append(repo_full_name)
            logger.info(f"Target added: {repo_full_name}")

    async def run_monitoring_cycle(self):
        logger.info("Starting GitHub monitoring cycle.")
        results = {}
        for repo in self.targets:
            res = await self.agent.execute(f"Monitor {repo}", action="monitor", repo=repo)
            if res.success:
                results[repo] = res.data
                logger.info(f"Report for {repo}: {res.data['message'][:50]}...")
        return results

async def main_test():
    monitor = MoonGithubMonitor()
    monitor.add_target("browserbase/stagehand")
    monitor.add_target("anthropics/claude-code")
    await monitor.run_monitoring_cycle()

if __name__ == "__main__":
    asyncio.run(main_test())
