"""Loads and validates the dietary_preference_config.json configuration file."""

from __future__ import annotations

import os
from pathlib import Path

from clean_grocery_bot.models import DietaryConfig

# Lambda deploys the config to /var/task/; fall back to the repo root for local dev.
_LAMBDA_PATH = Path("/var/task/dietary_preference_config.json")
_LOCAL_PATH = Path(__file__).parent.parent.parent / "dietary_preference_config.local.json"
_REPO_ROOT_PATH = Path(__file__).parent.parent.parent / "dietary_preference_config.json"

_cached_config: DietaryConfig | None = None


def load_config(path: str | None = None) -> DietaryConfig:
    """Return the validated DietaryConfig, caching it for Lambda warm starts.

    Args:
        path: Optional explicit path to the config file. When omitted the
              function checks ``/var/task/`` (Lambda) then the repo root.

    Returns:
        A validated, frozen :class:`DietaryConfig` instance.

    Raises:
        FileNotFoundError: If the config file cannot be found.
        pydantic.ValidationError: If the config file has schema violations.
    """
    global _cached_config
    if _cached_config is not None:
        return _cached_config

    config_path = _resolve_path(path)
    raw = config_path.read_text(encoding="utf-8")
    _cached_config = DietaryConfig.model_validate_json(raw)
    return _cached_config


def _resolve_path(path: str | None) -> Path:
    if path is not None:
        return Path(path)
    if _LAMBDA_PATH.exists():
        return _LAMBDA_PATH
    if _LOCAL_PATH.exists():
        return _LOCAL_PATH
    if _REPO_ROOT_PATH.exists():
        return _REPO_ROOT_PATH
    # Allow override via environment variable for testing
    env_path = os.environ.get("GROCERY_BOT_CONFIG")
    if env_path:
        return Path(env_path)
    msg = f"dietary_preference_config.json not found. Searched: {_LAMBDA_PATH}, {_LOCAL_PATH}, {_REPO_ROOT_PATH}"
    raise FileNotFoundError(msg)
