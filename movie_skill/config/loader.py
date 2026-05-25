"""Load and validate sites.yaml configuration."""

import os
from pathlib import Path
from typing import Optional

import yaml

from .schema import SitesConfig


class ConfigError(Exception):
    """Raised when configuration loading or validation fails."""
    pass


def _resolve_path(path: str) -> Path:
    """Resolve a path string, expanding ~ and env vars."""
    return Path(os.path.expanduser(os.path.expandvars(path))).resolve()


def load_config(path: Optional[str] = None) -> SitesConfig:
    """Load and validate sites.yaml from the given path.

    Args:
        path: Path to sites.yaml. Defaults to ~/.movie_skill/sites.yaml.

    Returns:
        Validated SitesConfig instance.

    Raises:
        ConfigError: If file not found, unreadable, or fails validation.
    """
    config_path = _resolve_path(path or "~/.movie_skill/sites.yaml")

    if not config_path.exists():
        raise ConfigError(f"Config file not found: {config_path}")

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in {config_path}: {e}") from e
    except OSError as e:
        raise ConfigError(f"Cannot read {config_path}: {e}") from e

    if not isinstance(raw, dict):
        raise ConfigError(f"Config must be a top-level mapping (dict), got {type(raw).__name__}")

    try:
        return SitesConfig(**raw)
    except Exception as e:
        raise ConfigError(f"Config validation failed for {config_path}: {e}") from e
