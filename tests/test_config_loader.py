"""Tests for config_loader.py."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

import clean_grocery_bot.config_loader as config_loader_module
from clean_grocery_bot.config_loader import load_config
from clean_grocery_bot.models import DietaryConfig


@pytest.fixture(autouse=True)
def reset_cache() -> None:
    """Reset the module-level cache before every test."""
    config_loader_module._cached_config = None
    yield
    config_loader_module._cached_config = None


def _write_config(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "dietary_preference_config.json"
    p.write_text(json.dumps(data))
    return p


MINIMAL_VALID = {
    "cleanliness_criteria": {"priorities": [{"rank": 1, "label": "No seed oils", "description": "Avoid seed oils"}]},
    "market": {"country": "US", "country_name": "United States"},
}


def test_load_valid_config(tmp_path: Path) -> None:
    p = _write_config(tmp_path, MINIMAL_VALID)
    config = load_config(str(p))

    assert isinstance(config, DietaryConfig)
    assert config.market.country == "US"
    assert len(config.cleanliness_criteria.priorities) == 1
    assert config.cleanliness_criteria.priorities[0].label == "No seed oils"


def test_load_config_defaults(tmp_path: Path) -> None:
    """Optional sections use sensible defaults when omitted."""
    p = _write_config(tmp_path, MINIMAL_VALID)
    config = load_config(str(p))

    assert config.recommendations.default_count == 3
    assert config.recommendations.max_count == 10
    assert config.recommendations.max_prefetch == 20
    assert config.whole_food_fallback.enabled is True
    assert config.response.language == "English"
    assert config.dietary_restrictions.exclude_ingredients == []


def test_load_config_with_custom_exclusions(tmp_path: Path) -> None:
    data = {**MINIMAL_VALID, "dietary_restrictions": {"exclude_ingredients": ["gluten", "dairy"]}}
    p = _write_config(tmp_path, data)
    config = load_config(str(p))

    assert config.dietary_restrictions.exclude_ingredients == ["gluten", "dairy"]


def test_load_config_strips_comment_keys(tmp_path: Path) -> None:
    """_comment, _instructions, _format_options keys must be silently ignored."""
    data = {
        "_comment": "top level comment",
        "_instructions": "edit this",
        "cleanliness_criteria": {
            "_comment": "nested comment",
            "priorities": [{"rank": 1, "label": "L", "description": "D"}],
        },
        "market": {
            "_comment": "market comment",
            "country": "GB",
            "country_name": "United Kingdom",
        },
        "response": {
            "_comment": "format comment",
            "_format_options": "short | medium | detailed",
            "language": "English",
            "format": "short",
        },
    }
    p = _write_config(tmp_path, data)
    config = load_config(str(p))

    assert config.market.country == "GB"
    assert config.response.format == "short"


def test_load_full_example_config() -> None:
    """The dietary_preference_config.json at the repo root must parse without error."""
    config = load_config()
    assert config.market.country == "US"
    assert len(config.cleanliness_criteria.priorities) == 4


def test_load_config_missing_required_key(tmp_path: Path) -> None:
    """Missing required field (market) raises ValidationError."""
    data = {"cleanliness_criteria": {"priorities": [{"rank": 1, "label": "L", "description": "D"}]}}
    p = _write_config(tmp_path, data)
    with pytest.raises(ValidationError):
        load_config(str(p))


def test_load_config_file_not_found() -> None:
    with pytest.raises(FileNotFoundError):
        load_config("/nonexistent/path/config.json")


def test_load_config_invalid_json(tmp_path: Path) -> None:
    p = tmp_path / "dietary_preference_config.json"
    p.write_text("{ not valid json }")
    with pytest.raises(ValueError):  # Pydantic raises ValueError for malformed JSON
        load_config(str(p))


def test_load_config_caches_result(tmp_path: Path) -> None:
    """Second call returns the exact same object (module-level cache)."""
    p = _write_config(tmp_path, MINIMAL_VALID)
    first = load_config(str(p))
    second = load_config(str(p))
    assert first is second
