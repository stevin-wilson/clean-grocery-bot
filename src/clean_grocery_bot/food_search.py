"""Open Food Facts API — taxonomy suggestions and product search."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from tenacity import (
    Retrying,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from clean_grocery_bot.models import Product

logger = logging.getLogger(__name__)

_USER_AGENT = "CleanGroceryBot/1.0 (https://github.com/stevin-wilson/clean-grocery-bot)"
_TAXONOMY_URL = "https://world.openfoodfacts.org/api/v3/taxonomy_suggestions"
_SEARCH_URL = "https://world.openfoodfacts.net/api/v2/search"
_SEARCH_FIELDS = "product_name,brands,ingredients_text,ingredients_tags"

_RETRY_POLICY: dict[str, Any] = {
    "stop": stop_after_attempt(3),
    "wait": wait_exponential(multiplier=1, min=1, max=4),
    "retry": retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
    "before_sleep": before_sleep_log(logger, logging.WARNING),
    "reraise": True,
}


def get_taxonomy_categories(search_term: str) -> list[str]:
    """Map a user search term to Open Food Facts category tags.

    Calls the v3 taxonomy suggestions API and returns the ``suggestions``
    list, which contains canonical category tag strings such as
    ``"en:breakfast-cereals"``.

    Args:
        search_term: Free-text category entered by the user (e.g. ``"cereal"``).

    Returns:
        A list of matching OFF category tag strings, potentially empty.

    Raises:
        httpx.HTTPStatusError: On non-2xx responses.
        httpx.TimeoutException: If the request exceeds the timeout after all retries.
    """
    with httpx.Client(timeout=15.0, headers={"User-Agent": _USER_AGENT}) as client:
        data: dict[str, Any] = {}
        for attempt in Retrying(**_RETRY_POLICY):
            with attempt:
                response = client.get(
                    _TAXONOMY_URL,
                    params={"tagtype": "categories", "string": search_term},
                )
                response.raise_for_status()
                data = response.json()

    suggestions: list[str] = data.get("suggestions", [])
    logger.info("Taxonomy lookup for %r returned %d suggestions", search_term, len(suggestions))
    return suggestions


def search_products(
    categories: list[str],
    country: str,
    max_results: int = 20,
) -> list[Product]:
    """Fetch products from Open Food Facts matching the given categories.

    Iterates through the ``categories`` list in order, querying the v2 search
    API for each, until ``max_results`` products have been collected.  Products
    with an empty ``product_name`` or ``ingredients_text`` are silently skipped.

    Args:
        categories: OFF category tag strings, e.g. ``["en:breakfast-cereals"]``.
        country: ISO 3166-1 alpha-2 country code (e.g. ``"US"``). Passed to OFF
                 as ``en:<country_lower>``.
        max_results: Maximum number of :class:`~clean_grocery_bot.models.Product`
                     objects to return.

    Returns:
        A list of :class:`~clean_grocery_bot.models.Product` instances, at most
        ``max_results`` long.

    Raises:
        httpx.HTTPStatusError: On non-2xx responses.
        httpx.TimeoutException: If a request exceeds the timeout after all retries.
    """
    products: list[Product] = []
    country_tag = f"en:{country.lower()}"

    with httpx.Client(timeout=15.0, headers={"User-Agent": _USER_AGENT}) as client:
        for category in categories:
            if len(products) >= max_results:
                break

            data: dict[str, Any] = {}
            for attempt in Retrying(**_RETRY_POLICY):
                with attempt:
                    response = client.get(
                        _SEARCH_URL,
                        params={
                            "categories_tags_en": category,
                            "countries_tags": country_tag,
                            "fields": _SEARCH_FIELDS,
                            "page_size": max_results,
                            "sort_by": "popularity_key",
                        },
                    )
                    response.raise_for_status()
                    data = response.json()

            for item in data.get("products", []):
                if len(products) >= max_results:
                    break
                name = (item.get("product_name") or "").strip()
                ingredients_text = (item.get("ingredients_text") or "").strip()
                if not name or not ingredients_text:
                    continue
                products.append(
                    Product(
                        name=name,
                        brand=(item.get("brands") or "Unknown").strip(),
                        ingredients_text=ingredients_text,
                        ingredients_tags=item.get("ingredients_tags") or [],
                    )
                )

    logger.info("search_products returned %d products", len(products))
    return products
