"""Tests for lambda_handler.py — pure helper functions."""

from clean_grocery_bot.lambda_handler import _format_response, _parse_user_message
from clean_grocery_bot.models import (
    CleanlinessCriteria,
    DietaryConfig,
    Market,
    Priority,
    RankedProduct,
)


def _make_config() -> DietaryConfig:
    return DietaryConfig(
        cleanliness_criteria=CleanlinessCriteria(
            priorities=[Priority(rank=1, label="No seed oils", description="Avoid seed oils")]
        ),
        market=Market(country="US", country_name="United States"),
    )


def _make_ranked(name: str = "Oat Flakes", score: int = 90, verdict: str = "Very Clean") -> RankedProduct:
    return RankedProduct(
        name=name,
        brand="Good Brand",
        score=score,
        verdict=verdict,  # type: ignore[arg-type]
        bullets=["Clean ingredients", "Short list"],
    )


CONFIG = _make_config()

# --- _parse_user_message ---


def test_parse_bare_term() -> None:
    assert _parse_user_message("cereal") == ("cereal", None)


def test_parse_top_n_term() -> None:
    assert _parse_user_message("top 5 cereals") == ("cereals", 5)


def test_parse_n_term() -> None:
    assert _parse_user_message("3 yogurts") == ("yogurts", 3)


def test_parse_strips_whitespace() -> None:
    assert _parse_user_message("  crackers  ") == ("crackers", None)


def test_parse_case_insensitive_top() -> None:
    assert _parse_user_message("TOP 3 chips") == ("chips", 3)


def test_parse_single_word_with_extra_spaces() -> None:
    term, count = _parse_user_message("  oats  ")
    assert term == "oats"
    assert count is None


# --- _format_response ---


def test_format_response_contains_product_name() -> None:
    ranked = [_make_ranked("Quinoa Puffs")]
    result = _format_response(ranked, "cereal", CONFIG)
    assert "Quinoa Puffs" in result


def test_format_response_contains_score() -> None:
    ranked = [_make_ranked(score=85)]
    result = _format_response(ranked, "cereal", CONFIG)
    assert "85" in result


def test_format_response_contains_verdict() -> None:
    ranked = [_make_ranked(verdict="Acceptable")]
    result = _format_response(ranked, "chips", CONFIG)
    assert "Acceptable" in result


def test_format_response_contains_bullets() -> None:
    ranked = [_make_ranked()]
    result = _format_response(ranked, "oats", CONFIG)
    assert "Clean ingredients" in result
    assert "Short list" in result


def test_format_response_contains_search_term_header() -> None:
    ranked = [_make_ranked()]
    result = _format_response(ranked, "granola", CONFIG)
    assert "granola" in result


def test_format_response_multiple_products_numbered() -> None:
    ranked = [_make_ranked("Product A"), _make_ranked("Product B", score=70, verdict="Acceptable")]
    result = _format_response(ranked, "snacks", CONFIG)
    assert "1." in result
    assert "2." in result
    assert "Product A" in result
    assert "Product B" in result
