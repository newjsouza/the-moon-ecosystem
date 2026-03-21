"""
EvaluationCriteria — loads and exposes evaluation rules from YAML.
Used by EvaluatorAgent to score TaskResult outputs.
"""
import yaml
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_CRITERIA_PATH = Path("evaluation_criteria.yaml")


class EvaluationCriteria:
    """Load and query evaluation criteria from YAML config."""

    def __init__(self, config_path: Path = None):
        self._path = config_path or _CRITERIA_PATH
        self._config = self._load()

    def _load(self) -> dict:
        try:
            with open(self._path) as f:
                config = yaml.safe_load(f)
            logger.info(f"Evaluation criteria loaded from {self._path}")
            return config
        except FileNotFoundError:
            logger.warning(f"Criteria file not found: {self._path} — using defaults")
            return self._default_config()
        except Exception as e:
            logger.error(f"Failed to load criteria: {e}")
            return self._default_config()

    def get_criteria(self, domain: str) -> dict:
        """Get criteria config for a domain. Falls back to 'default'."""
        return self._config.get(domain, self._config.get("default", self._default_config()["default"]))

    def get_threshold(self, domain: str) -> float:
        """Get minimum passing score for a domain."""
        return self.get_criteria(domain).get("threshold", 0.65)

    def get_max_retries(self, domain: str) -> int:
        """Get max retry attempts for a domain."""
        return self.get_criteria(domain).get("max_retries", 3)

    def get_weights(self, domain: str) -> dict:
        """Get {criterion_name: weight} for a domain."""
        criteria = self.get_criteria(domain).get("criteria", {})
        return {k: v["weight"] for k, v in criteria.items()}

    def list_domains(self) -> list:
        return list(self._config.keys())

    @staticmethod
    def _default_config() -> dict:
        return {
            "default": {
                "threshold": 0.65,
                "max_retries": 3,
                "criteria": {
                    "completeness": {"weight": 0.35, "description": "Fully addresses task"},
                    "relevance": {"weight": 0.35, "description": "On-topic response"},
                    "quality": {"weight": 0.30, "description": "Overall quality"},
                }
            }
        }