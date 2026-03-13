"""
learning/adapter.py
Adapts responses and behavior based on user feedback.
"""
from typing import Dict, Any, List
import time

class ContextAdapter:
    def __init__(self):
        self.user_preferences: Dict[str, Any] = {}
        self.adaptation_history: List[Dict[str, Any]] = []

    def update_preference(self, category: str, key: str, value: Any):
        if category not in self.user_preferences:
            self.user_preferences[category] = {}
        self.user_preferences[category][key] = value
        self.adaptation_history.append({
            "timestamp": time.time(),
            "category": category,
            "key": key,
            "value": value
        })

    def get_preference(self, category: str, key: str, default: Any = None) -> Any:
        return self.user_preferences.get(category, {}).get(key, default)

    def adapt_context(self, context: Dict[str, Any], task_type: str) -> Dict[str, Any]:
        """Modifies the context based on learned preferences before passing to LLM."""
        adapted = context.copy()
        prefs = self.user_preferences.get(task_type, {})
        for k, v in prefs.items():
            adapted[f"pref_{k}"] = v
        return adapted
