"""
core/flow_template.py
System for creating, customizing and instantiating flow templates.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional
import threading
import glob


@dataclass
class FlowTemplateVar:
    """Represents a variable in a flow template."""
    name: str
    description: str
    default: str = ""


@dataclass
class FlowTemplate:
    """Represents a flow template that can be instantiated with variables."""
    name: str
    domain: str
    description: str
    variables: List[FlowTemplateVar]
    steps: List[Dict[str, Any]]
    tags: List[str] = None
    version: str = "1.0.0"

    def __post_init__(self):
        if self.tags is None:
            self.tags = []

    def instantiate(self, values: Dict[str, str]) -> 'MoonFlow':
        """Instantiate a MoonFlow from this template with the given variable values."""
        from core.moon_flow import MoonFlow, FlowStep
        
        # Replace variables in step tasks
        instantiated_steps = []
        for step_data in self.steps:
            step_dict = step_data.copy()
            
            # Replace variables in the task field
            task = step_dict.get("task", "")
            for var in self.variables:
                var_name = var.name
                # Use provided value or default if not provided
                replacement_value = values.get(var_name, var.default)
                task = task.replace(f"{{{var_name}}}", replacement_value)
            
            step_dict["task"] = task
            instantiated_steps.append(FlowStep(**step_dict))
        
        return MoonFlow(
            name=self.name,
            steps=instantiated_steps,
            session_mode="user"  # Default to user mode
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the template to a dictionary."""
        return {
            "name": self.name,
            "domain": self.domain,
            "description": self.description,
            "version": self.version,
            "tags": self.tags,
            "variables": [asdict(var) for var in self.variables],
            "steps": self.steps
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FlowTemplate:
        """Deserialize a template from a dictionary."""
        variables = [FlowTemplateVar(**var_data) for var_data in data["variables"]]
        return cls(
            name=data["name"],
            domain=data["domain"],
            description=data["description"],
            version=data.get("version", "1.0.0"),
            tags=data.get("tags", []),
            variables=variables,
            steps=data["steps"]
        )

    def get_variables_prompt(self) -> str:
        """Return a human-readable string describing the variables."""
        if not self.variables:
            return "Nenhuma variável."
        
        var_descriptions = []
        for var in self.variables:
            var_descriptions.append(f"{var.name} ({var.description})")
        
        return f"Variáveis: {', '.join(var_descriptions)}"


class FlowTemplateRegistry:
    """Registry for managing flow templates."""
    
    def __init__(self):
        self._templates: Dict[str, FlowTemplate] = {}
        self._lock = threading.Lock()

    def register(self, template: FlowTemplate) -> None:
        """Register a template."""
        with self._lock:
            self._templates[template.name] = template

    def get(self, name: str) -> Optional[FlowTemplate]:
        """Get a template by name."""
        with self._lock:
            return self._templates.get(name)

    def list_templates(self) -> List[FlowTemplate]:
        """List all registered templates."""
        with self._lock:
            return list(self._templates.values())

    def list_by_domain(self, domain: str) -> List[FlowTemplate]:
        """List templates by domain."""
        with self._lock:
            return [t for t in self._templates.values() if t.domain == domain]

    def load_from_file(self, path: str) -> FlowTemplate:
        """Load a template from a JSON file."""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return FlowTemplate.from_dict(data)

    def save_to_file(self, template: FlowTemplate, path: str) -> None:
        """Save a template to a JSON file."""
        data = template.to_dict()
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def discover(self, base_path: str = "flow_templates") -> int:
        """Discover and register all templates in the base_path directory."""
        count = 0
        if not os.path.exists(base_path):
            return 0
            
        # Find all JSON files in the directory and subdirectories
        pattern = os.path.join(base_path, "**", "*.json")
        for file_path in glob.glob(pattern, recursive=True):
            try:
                template = self.load_from_file(file_path)
                self.register(template)
                count += 1
            except Exception:
                # Silently ignore invalid template files
                continue
                
        return count


# Singleton instance
_template_registry = None
_template_lock = threading.Lock()


def get_template_registry() -> FlowTemplateRegistry:
    """Get singleton instance of FlowTemplateRegistry."""
    global _template_registry
    
    with _template_lock:
        if _template_registry is None:
            _template_registry = FlowTemplateRegistry()
    
    return _template_registry