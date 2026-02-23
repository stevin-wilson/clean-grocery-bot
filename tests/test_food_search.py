"""Tests for food_search.py."""

import httpx
import pytest
import respx

from clean_grocery_bot.food_search import (
    _SEARCH_URL,
    _TAXONOMY_URL,
    get_taxonomy_categories,
    search_products,
)
from clean_grocery_bot.models import Product

_PRODUCT = {
    "product_name": "Organic Oats",
    "brands": "Nature's Best",
    "ingredients_text": "Whole grain oats",
    "ingredients_tags": ["en:oats"],
}

_PRODUCT_NO_INGREDIENTS = {
    "product_name": "Mystery Bar",
    "brands": "Unknown Co",
    "ingredients_text": "",
    "ingredients_tags": [],
}

_PRODUCT_NO_NAME = {
    "product_name": "",
    "brands": "Some Brand",
    "ingredients_text": "Water, salt",
    "ingredients_tags": [],
}


@respx.mock
def test_get_taxonomy_categories_success() -> None:
    respx.get(_TAXONOMY_URL).mock(
        return_value=httpx.Response(200, json={"suggestions": ["en:cereals", "en:breakfast-cereals"]})
    )
    result = get_taxonomy_categories("cereal")
    assert result == ["en:cereals", "en:breakfast-cereals"]


@respx.mock
def test_get_taxonomy_categories_empty() -> None:
    respx.get(_TAXONOMY_URL).mock(return_value=httpx.Response(200, json={"suggestions": []}))
    assert get_taxonomy_categories("xyzzy") == []


@respx.mock
def test_get_taxonomy_categories_missing_key() -> None:
    """API returning no 'suggestions' key is handled gracefully."""
    respx.get(_TAXONOMY_URL).mock(return_value=httpx.Response(200, json={}))
    assert get_taxonomy_categories("cereal") == []


@respx.mock
def test_get_taxonomy_categories_http_error() -> None:
    respx.get(_TAXONOMY_URL).mock(return_value=httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        get_taxonomy_categories("cereal")


@respx.mock
def test_search_products_success() -> None:
    respx.get(_SEARCH_URL).mock(return_value=httpx.Response(200, json={"products": [_PRODUCT]}))
    result = search_products(["en:cereals"], "US")
    assert len(result) == 1
    assert isinstance(result[0], Product)
    assert result[0].name == "Organic Oats"
    assert result[0].brand == "Nature's Best"


@respx.mock
def test_search_products_filters_missing_ingredients() -> None:
    respx.get(_SEARCH_URL).mock(
        return_value=httpx.Response(200, json={"products": [_PRODUCT, _PRODUCT_NO_INGREDIENTS]})
    )
    result = search_products(["en:cereals"], "US")
    assert len(result) == 1
    assert result[0].name == "Organic Oats"


@respx.mock
def test_search_products_filters_missing_name() -> None:
    respx.get(_SEARCH_URL).mock(return_value=httpx.Response(200, json={"products": [_PRODUCT_NO_NAME, _PRODUCT]}))
    result = search_products(["en:cereals"], "US")
    assert len(result) == 1
    assert result[0].name == "Organic Oats"


@respx.mock
def test_search_products_respects_max_results() -> None:
    five_products = [
        {**_PRODUCT, "product_name": f"Product {i}", "ingredients_text": f"Ingredient {i}"} for i in range(5)
    ]
    respx.get(_SEARCH_URL).mock(return_value=httpx.Response(200, json={"products": five_products}))
    result = search_products(["en:cereals"], "US", max_results=2)
    assert len(result) == 2


@respx.mock
def test_search_products_multiple_categories() -> None:
    product_a = {**_PRODUCT, "product_name": "Product A", "ingredients_text": "Oats"}
    product_b = {**_PRODUCT, "product_name": "Product B", "ingredients_text": "Wheat"}
    respx.get(_SEARCH_URL).mock(
        side_effect=[
            httpx.Response(200, json={"products": [product_a]}),
            httpx.Response(200, json={"products": [product_b]}),
        ]
    )
    result = search_products(["en:cereals", "en:bread"], "US", max_results=10)
    assert len(result) == 2
    names = {p.name for p in result}
    assert names == {"Product A", "Product B"}


@respx.mock
def test_search_products_stops_at_max_across_categories() -> None:
    """Should not query later categories once max_results is reached."""
    respx.get(_SEARCH_URL).mock(return_value=httpx.Response(200, json={"products": [_PRODUCT]}))
    result = search_products(["en:a", "en:b", "en:c"], "US", max_results=1)
    assert len(result) == 1
    # Only the first category should have been queried
    assert respx.calls.call_count == 1


# --- Retry behaviour ---


@respx.mock
def test_get_taxonomy_categories_retries_on_timeout(mocker: pytest.fixture) -> None:  # type: ignore[type-arg]
    """Should retry on ReadTimeout and succeed on the third attempt."""
    mocker.patch("tenacity.nap.sleep")
    respx.get(_TAXONOMY_URL).mock(
        side_effect=[
            httpx.ReadTimeout("timeout 1"),
            httpx.ReadTimeout("timeout 2"),
            httpx.Response(200, json={"suggestions": ["en:cereals"]}),
        ]
    )
    result = get_taxonomy_categories("cereal")
    assert result == ["en:cereals"]
    assert respx.calls.call_count == 3


@respx.mock
def test_get_taxonomy_categories_raises_after_max_retries(mocker: pytest.fixture) -> None:  # type: ignore[type-arg]
    """Should raise TimeoutException after exhausting all 3 attempts."""
    mocker.patch("tenacity.nap.sleep")
    respx.get(_TAXONOMY_URL).mock(side_effect=httpx.ReadTimeout("timeout"))
    with pytest.raises(httpx.TimeoutException):
        get_taxonomy_categories("cereal")
    assert respx.calls.call_count == 3


@respx.mock
def test_get_taxonomy_categories_no_retry_on_http_error() -> None:
    """Should NOT retry on HTTP 5xx — fails immediately after 1 attempt."""
    respx.get(_TAXONOMY_URL).mock(return_value=httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        get_taxonomy_categories("cereal")
    assert respx.calls.call_count == 1


@respx.mock
def test_search_products_retries_on_timeout(mocker: pytest.fixture) -> None:  # type: ignore[type-arg]
    """Should retry search_products on ReadTimeout and succeed on the third attempt."""
    mocker.patch("tenacity.nap.sleep")
    respx.get(_SEARCH_URL).mock(
        side_effect=[
            httpx.ReadTimeout("timeout 1"),
            httpx.ReadTimeout("timeout 2"),
            httpx.Response(200, json={"products": [_PRODUCT]}),
        ]
    )
    result = search_products(["en:cereals"], "US")
    assert len(result) == 1
    assert respx.calls.call_count == 3
