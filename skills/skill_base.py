import abc
import logging
from typing import Any, Dict

class SkillBase(abc.ABC):
    """
    Base class for all skills in The Moon ecosystem.
    Standardizes execution, logging, and error handling.
    """
    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"moon.skills.{name}")
        self.logger.setLevel(logging.INFO)

    @abc.abstractmethod
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the skill with the given parameters.
        Returns a dictionary with the results.
        """
        pass

    def log(self, message: str, level: int = logging.INFO):
        self.logger.log(level, message)

    def __repr__(self):
        return f"<Skill: {self.name}>"
