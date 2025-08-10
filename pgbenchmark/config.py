"""Configuration management for pgbenchmark."""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


class Config:
    """Global configuration manager."""

    DEFAULT_CONFIG = {
        "database": {
            "host": "localhost",
            "port": 5432,
            "dbname": "postgres",
            "user": "postgres",
            "password": "",
        },
        "benchmark": {
            "default_runs": 100,
            "warmup_runs": 5,
            "timeout": None,
            "batch_size": None,
        },
        "parallel": {"default_processes": 4, "max_processes": 16},
        "async": {"default_concurrency": 10, "max_concurrency": 100},
        "reporting": {
            "output_format": "json",
            "verbose": False,
            "save_raw_results": False,
        },
    }

    def __init__(self, config_file: Optional[str] = None):
        self.config = self.DEFAULT_CONFIG.copy()

        # Load from environment variables
        self._load_from_env()

        # Load from config file if provided
        if config_file:
            self.load_from_file(config_file)

    def _load_from_env(self):
        """Load configuration from environment variables."""
        env_mapping = {
            "PGBENCH_HOST": ("database", "host"),
            "PGBENCH_PORT": ("database", "port"),
            "PGBENCH_DB": ("database", "dbname"),
            "PGBENCH_USER": ("database", "user"),
            "PGBENCH_PASSWORD": ("database", "password"),
            "PGBENCH_RUNS": ("benchmark", "default_runs"),
            "PGBENCH_WARMUP": ("benchmark", "warmup_runs"),
        }

        for env_var, (section, key) in env_mapping.items():
            value = os.environ.get(env_var)
            if value:
                if key in ["port", "default_runs", "warmup_runs"]:
                    value = int(value)
                self.config[section][key] = value

    def load_from_file(self, filepath: str):
        """Load configuration from JSON file."""
        path = Path(filepath)
        if path.exists():
            with open(path, "r") as f:
                file_config = json.load(f)
                self._merge_config(file_config)

    def _merge_config(self, new_config: Dict[str, Any]):
        """Merge new configuration with existing."""
        for key, value in new_config.items():
            if key in self.config and isinstance(value, dict):
                self.config[key].update(value)
            else:
                self.config[key] = value

    def get(self, section: str, key: Optional[str] = None):
        """Get configuration value."""
        if key:
            return self.config.get(section, {}).get(key)
        return self.config.get(section)

    def set(self, section: str, key: str, value: Any):
        """Set configuration value."""
        if section not in self.config:
            self.config[section] = {}
        self.config[section][key] = value

    def save_to_file(self, filepath: str):
        """Save configuration to JSON file."""
        with open(filepath, "w") as f:
            json.dump(self.config, f, indent=2)


# Global config instance
global_config = Config()
