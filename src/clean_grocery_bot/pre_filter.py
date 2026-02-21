"""Rule-based ingredient pre-filter applied before sending products to Claude."""

from __future__ import annotations

import logging

from clean_grocery_bot.models import DietaryConfig, Product

logger = logging.getLogger(__name__)

# Hard-coded exclusion lists representing the bot's built-in knowledge.
# These run before the AI call to reduce cost and improve consistency.
SEED_OILS: frozenset[str] = frozenset({
    "canola oil",
    "soybean oil",
    "sunflower oil",
    "safflower oil",
    "corn oil",
    "cottonseed oil",
    "grapeseed oil",
    "rapeseed oil",
    "vegetable oil",
})

ARTIFICIAL_ADDITIVES: frozenset[str] = frozenset({
    "bha",
    "bht",
    "tbhq",
    "sodium benzoate",
    "potassium sorbate",
    "red 40",
    "yellow 5",
    "yellow 6",
    "blue 1",
    "blue 2",
    "red 3",
    "green 3",
    "carrageenan",
    "artificial color",
    "artificial colour",
    "artificial flavor",
    "artificial flavour",
    "high fructose corn syrup",
})


def _build_exclusion_set(config: DietaryConfig) -> frozenset[str]:
    """Combine built-in lists with the user's personal exclusions (lowercased)."""
    user_excludes = frozenset(term.lower() for term in config.dietary_restrictions.exclude_ingredients)
    return SEED_OILS | ARTIFICIAL_ADDITIVES | user_excludes


def filter_products(products: list[Product], config: DietaryConfig) -> list[Product]:
    """Remove products that contain any hard-excluded ingredient.

    Matching is case-insensitive substring search on ``ingredients_text``.
    The ``products`` list is not mutated.

    Args:
        products: Candidate products from Open Food Facts.
        config: The loaded dietary preference configuration.

    Returns:
        A new list containing only products that pass all exclusion checks.
    """
    exclusions = _build_exclusion_set(config)
    result: list[Product] = []
    for product in products:
        text_lower = product.ingredients_text.lower()
        if any(term in text_lower for term in exclusions):
            logger.debug("Excluded %r (matched exclusion rule)", product.name)
            continue
        result.append(product)

    logger.info("pre_filter: %d → %d products after filtering", len(products), len(result))
    return result
