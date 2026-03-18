from __future__ import annotations
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
import threading


@dataclass
class SkillManifest:
    name: str
    version: str
    description: str
    domains: List[str]
    commands: List[str]
    examples: List[str]
    fallback: Optional[str] = None
    cost: str = "zero"
    requires_key: bool = False


# Global registry instance
_skill_registry = None
_registry_lock = threading.Lock()


class SkillRegistry:
    def __init__(self):
        self._manifests: dict[str, SkillManifest] = {}

    def load_from_file(self, path: str) -> SkillManifest:
        """Load a skill manifest from a JSON file."""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return SkillManifest(**data)

    def register(self, manifest: SkillManifest) -> None:
        """Register a skill manifest."""
        self._manifests[manifest.name] = manifest

    def get(self, name: str) -> Optional[SkillManifest]:
        """Get a skill manifest by name."""
        return self._manifests.get(name)

    def list_by_domain(self, domain: str) -> List[SkillManifest]:
        """List all skill manifests that support a given domain."""
        return [manifest for manifest in self._manifests.values() 
                if domain in manifest.domains]

    def list_all(self) -> List[SkillManifest]:
        """List all registered skill manifests."""
        return list(self._manifests.values())

    def discover(self, base_path: str = "skills") -> int:
        """Discover skill.json files in the given base path and register them.
        
        Returns the number of manifests loaded.
        """
        count = 0
        base = Path(base_path)
        
        if not base.exists():
            return 0
        
        # Find all skill.json files recursively
        for skill_json in base.rglob("skill.json"):
            try:
                manifest = self.load_from_file(str(skill_json))
                self.register(manifest)
                count += 1
            except Exception:
                # Skip invalid files
                continue
                
        return count


def get_skill_registry() -> SkillRegistry:
    """Get the global skill registry instance (singleton)."""
    global _skill_registry
    
    with _registry_lock:
        if _skill_registry is None:
            _skill_registry = SkillRegistry()
    
    return _skill_registry