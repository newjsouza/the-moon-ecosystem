"""
core/config.py
Configuration system with singleton.
Loads from YAML, env, defaults.
"""
import os
import yaml
from typing import Any, Dict
from dotenv import load_dotenv

# Security layer
from core.security.secrets import SecretManager

class Config:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Config, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, '_initialized', False):
            return

        load_dotenv()
        
        # Security: Validate secrets on boot
        _secrets = SecretManager()
        if not _secrets.validate_boot():
            import logging
            logging.getLogger(__name__).error("BOOT: Missing required secrets — check .env")
        
        self._config: Dict[str, Any] = {}
        self._load_defaults()
        self._load_yaml()
        self._initialized = True

    def _load_defaults(self):
        self._config = {
            "system": {
                "name": "The Moon AI",
                "version": "1.0.0",
                "debug": False,
                "log_level": "INFO",
                "max_concurrent_agents": 5,
                "learning_enabled": True
            },
            "llm": {
                "provider": "groq",
                "model": "llama-3.3-70b-versatile",
                "temperature": 0.7,
                "max_tokens": 4096,
                "api_key": os.environ.get("GROQ_API_KEY", "")
            },
            "agents": {}
        }

    def _load_yaml(self):
        config_path = os.environ.get("MOON_CONFIG_PATH", "config/default.yaml")
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    yaml_config = yaml.safe_load(f)
                    if yaml_config:
                        self._merge_dicts(self._config, yaml_config)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Error loading config file {config_path}: {e}")

    def _merge_dicts(self, dict1: dict, dict2: dict):
        for k, v in dict2.items():
            if isinstance(dict1.get(k), dict) and isinstance(v, dict):
                self._merge_dicts(dict1[k], v)
            else:
                dict1[k] = v

    def get(self, key_path: str, default: Any = None) -> Any:
        keys = key_path.split('.')
        value = self._config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value

    def set(self, key_path: str, value: Any):
        keys = key_path.split('.')
        target = self._config
        for key in keys[:-1]:
            target = target.setdefault(key, {})
        target[keys[-1]] = value
