"""Tests for pre_filter.py."""

from clean_grocery_bot.models import (
    CleanlinessCriteria,
    DietaryConfig,
    DietaryRestrictions,
    Market,
    Priority,
    Product,
)
from clean_grocery_bot.pre_filter import ARTIFICIAL_ADDITIVES, SEED_OILS, filter_products


def _make_config(exclude_ingredients: list[str] | None = None) -> DietaryConfig:
    return DietaryConfig(
        cleanliness_criteria=CleanlinessCriteria(
            priorities=[Priority(rank=1, label="No seed oils", description="Avoid seed oils")]
        ),
        dietary_restrictions=DietaryRestrictions(exclude_ingredients=exclude_ingredients or []),
        market=Market(country="US", country_name="United States"),
    )


def _make_product(ingredients_text: str, name: str = "Test Product") -> Product:
    return Product(name=name, brand="Test Brand", ingredients_text=ingredients_text)


CONFIG = _make_config()


def test_filter_removes_seed_oil_product() -> None:
    products = [_make_product("whole wheat flour, soybean oil, salt")]
    assert filter_products(products, CONFIG) == []


def test_filter_removes_artificial_additive() -> None:
    products = [_make_product("water, sugar, Red 40, natural flavor")]
    assert filter_products(products, CONFIG) == []


def test_filter_keeps_clean_product() -> None:
    clean = _make_product("whole wheat flour, water, salt")
    assert filter_products([clean], CONFIG) == [clean]


def test_filter_case_insensitive_seed_oil() -> None:
    products = [_make_product("CANOLA OIL, Sugar")]
    assert filter_products(products, CONFIG) == []


def test_filter_case_insensitive_additive() -> None:
    products = [_make_product("Water, BHT, natural flavor")]
    assert filter_products(products, CONFIG) == []


def test_filter_with_user_exclusions() -> None:
    config = _make_config(exclude_ingredients=["gluten"])
    dirty = _make_product("enriched flour (gluten), salt")
    clean = _make_product("rolled oats, water")
    result = filter_products([dirty, clean], config)
    assert result == [clean]


def test_filter_user_exclusion_case_insensitive() -> None:
    config = _make_config(exclude_ingredients=["Dairy"])
    products = [_make_product("whole milk (dairy), sugar")]
    assert filter_products(products, config) == []


def test_filter_empty_product_list() -> None:
    assert filter_products([], CONFIG) == []


def test_filter_all_excluded() -> None:
    products = [
        _make_product("canola oil, sugar", "Product A"),
        _make_product("water, bht", "Product B"),
    ]
    assert filter_products(products, CONFIG) == []


def test_filter_does_not_mutate_input() -> None:
    products = [
        _make_product("whole oats, water", "Clean"),
        _make_product("soybean oil, salt", "Dirty"),
    ]
    original = list(products)
    filter_products(products, CONFIG)
    assert products == original


def test_filter_mixed_list() -> None:
    clean = _make_product("rolled oats, water, salt", "Clean")
    dirty = _make_product("vegetable oil, sugar", "Dirty")
    result = filter_products([clean, dirty], CONFIG)
    assert result == [clean]


def test_seed_oils_and_additives_are_frozensets() -> None:
    """Sanity-check that the constants are frozensets for O(1) lookup."""
    assert isinstance(SEED_OILS, frozenset)
    assert isinstance(ARTIFICIAL_ADDITIVES, frozenset)
    assert "canola oil" in SEED_OILS
    assert "red 40" in ARTIFICIAL_ADDITIVES
