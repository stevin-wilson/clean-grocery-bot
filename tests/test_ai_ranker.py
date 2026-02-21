"""Tests for ai_ranker.py."""

import json

import pytest
from pydantic import ValidationError

import clean_grocery_bot.ai_ranker as ai_ranker_module
from clean_grocery_bot.ai_ranker import _build_prompt, rank_products
from clean_grocery_bot.models import (
    CleanlinessCriteria,
    DietaryConfig,
    Market,
    Priority,
    Product,
    RankedProduct,
)


@pytest.fixture(autouse=True)
def reset_bedrock_client() -> None:
    ai_ranker_module._bedrock_client = None
    yield
    ai_ranker_module._bedrock_client = None


def _make_config() -> DietaryConfig:
    return DietaryConfig(
        cleanliness_criteria=CleanlinessCriteria(
            priorities=[
                Priority(rank=1, label="No seed oils", description="Avoid seed oils"),
                Priority(rank=2, label="No additives", description="Avoid artificial additives"),
            ]
        ),
        market=Market(country="US", country_name="United States"),
    )


def _make_product(name: str = "Oat Flakes", ingredients: str = "Whole grain oats") -> Product:
    return Product(name=name, brand="Good Brand", ingredients_text=ingredients)


def _mock_bedrock(mocker, response_json: list[dict]) -> None:
    mock_client = mocker.MagicMock()
    mock_client.converse.return_value = {"output": {"message": {"content": [{"text": json.dumps(response_json)}]}}}
    mocker.patch.object(ai_ranker_module, "_get_bedrock_client", return_value=mock_client)


CONFIG = _make_config()

VALID_RANKED = [
    {
        "name": "Oat Flakes",
        "brand": "Good Brand",
        "score": 90,
        "verdict": "Very Clean",
        "bullets": ["Organic", "Short list"],
    },
]


def test_build_prompt_includes_all_products() -> None:
    products = [_make_product("Product A"), _make_product("Product B")]
    prompt = _build_prompt(products, CONFIG)
    assert "Product A" in prompt
    assert "Product B" in prompt


def test_build_prompt_includes_rubric_priorities() -> None:
    prompt = _build_prompt([_make_product()], CONFIG)
    assert "No seed oils" in prompt
    assert "No additives" in prompt


def test_build_prompt_includes_ingredients() -> None:
    product = _make_product(ingredients="Rolled oats, water, sea salt")
    prompt = _build_prompt([product], CONFIG)
    assert "Rolled oats, water, sea salt" in prompt


def test_rank_products_returns_empty_without_calling_bedrock(mocker) -> None:
    mock_client = mocker.MagicMock()
    mocker.patch.object(ai_ranker_module, "_get_bedrock_client", return_value=mock_client)
    result = rank_products([], CONFIG)
    assert result == []
    mock_client.converse.assert_not_called()


def test_rank_products_success(mocker) -> None:
    _mock_bedrock(mocker, VALID_RANKED)
    result = rank_products([_make_product()], CONFIG)
    assert len(result) == 1
    assert isinstance(result[0], RankedProduct)
    assert result[0].name == "Oat Flakes"
    assert result[0].score == 90
    assert result[0].verdict == "Very Clean"


def test_rank_products_sorted_by_score_descending(mocker) -> None:
    response = [
        {"name": "A", "brand": "B", "score": 70, "verdict": "Acceptable", "bullets": ["ok", "fine"]},
        {"name": "B", "brand": "B", "score": 90, "verdict": "Very Clean", "bullets": ["great", "clean"]},
        {"name": "C", "brand": "B", "score": 30, "verdict": "Avoid", "bullets": ["bad", "avoid"]},
    ]
    _mock_bedrock(mocker, response)
    products = [_make_product(f"Product {x}") for x in "ABC"]
    result = rank_products(products, CONFIG)
    scores = [r.score for r in result]
    assert scores == sorted(scores, reverse=True)
    assert scores == [90, 70, 30]


def test_rank_products_invalid_json_raises(mocker) -> None:
    mock_client = mocker.MagicMock()
    mock_client.converse.return_value = {"output": {"message": {"content": [{"text": "not json at all"}]}}}
    mocker.patch.object(ai_ranker_module, "_get_bedrock_client", return_value=mock_client)
    with pytest.raises(ValidationError):
        rank_products([_make_product()], CONFIG)


def test_rank_products_invalid_score_raises(mocker) -> None:
    """Score outside 0-100 must fail Pydantic validation."""
    bad_response = [{"name": "A", "brand": "B", "score": 150, "verdict": "Very Clean", "bullets": ["x", "y"]}]
    _mock_bedrock(mocker, bad_response)
    with pytest.raises(ValidationError):
        rank_products([_make_product()], CONFIG)


def test_rank_products_invalid_verdict_raises(mocker) -> None:
    bad_response = [{"name": "A", "brand": "B", "score": 80, "verdict": "Pretty Good", "bullets": ["x", "y"]}]
    _mock_bedrock(mocker, bad_response)
    with pytest.raises(ValidationError):
        rank_products([_make_product()], CONFIG)
