"""AWS Bedrock Claude integration — ingredient-cleanliness scoring and ranking."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import boto3
from pydantic import TypeAdapter

from clean_grocery_bot.models import DietaryConfig, Product, RankedProduct

if TYPE_CHECKING:
    from mypy_boto3_bedrock_runtime import BedrockRuntimeClient

logger = logging.getLogger(__name__)

_MODEL_ID = "anthropic.claude-haiku-4-5-20251001-v1:0"
_MAX_TOKENS = 2048

_bedrock_client: BedrockRuntimeClient | None = None
_ranked_product_list_adapter: TypeAdapter[list[RankedProduct]] = TypeAdapter(list[RankedProduct])


def _get_bedrock_client() -> BedrockRuntimeClient:
    global _bedrock_client
    if _bedrock_client is None:
        _bedrock_client = boto3.client("bedrock-runtime", region_name="us-east-1")  # type: ignore[assignment]
    return _bedrock_client


def _build_prompt(products: list[Product], config: DietaryConfig) -> str:
    """Build the scoring prompt from the product list and user config priorities."""
    rubric_lines = "\n".join(
        f"  Priority {p.rank}: {p.label} — {p.description}" for p in config.cleanliness_criteria.priorities
    )

    product_lines = "\n".join(
        f"{i}. {p.name} (Brand: {p.brand})\n   Ingredients: {p.ingredients_text}" for i, p in enumerate(products, 1)
    )

    return f"""You are a food ingredient analyst. Score each product on ingredient cleanliness (0-100).

Scoring rubric (start at 100, deduct points):
{rubric_lines}

Standard deductions:
  - Contains a seed oil: -40 points
  - Contains an artificial additive or preservative: -40 points
  - Not organic (when an organic alternative exists in the list): -20 points
  - More than 10 ingredients: -10 points per 5 ingredients over the threshold

Verdict bands:
  - 80-100: "Very Clean"
  - 50-79:  "Acceptable"
  - 0-49:   "Avoid"

Products to score:
{product_lines}

Return ONLY a JSON array (no markdown, no extra text) with one object per product.
Each object must have exactly these fields:
  "name"    -- string (product name as given above)
  "brand"   -- string
  "score"   -- integer 0-100
  "verdict" -- one of "Very Clean", "Acceptable", "Avoid"
  "bullets" -- array of 2-3 short strings explaining the score
"""


def rank_products(products: list[Product], config: DietaryConfig) -> list[RankedProduct]:
    """Send products to Claude Haiku on Bedrock for cleanliness scoring.

    Products are scored according to the priorities in *config* and returned
    sorted from highest to lowest score.  Returns an empty list immediately
    if *products* is empty (no Bedrock call is made).

    Args:
        products: Pre-filtered candidate products.
        config: The loaded dietary preference configuration.

    Returns:
        A list of :class:`~clean_grocery_bot.models.RankedProduct` objects
        sorted by ``score`` descending.

    Raises:
        pydantic.ValidationError: If Claude returns JSON that fails schema validation.
        botocore.exceptions.ClientError: On Bedrock API errors.
    """
    if not products:
        return []

    prompt = _build_prompt(products, config)
    client = _get_bedrock_client()

    response: dict[str, Any] = client.converse(
        modelId=_MODEL_ID,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": _MAX_TOKENS, "temperature": 0.0},
    )

    output_text: str = response["output"]["message"]["content"][0]["text"]
    logger.debug("Bedrock raw response: %s", output_text[:500])

    ranked = _ranked_product_list_adapter.validate_json(output_text)
    ranked.sort(key=lambda r: r.score, reverse=True)

    logger.info("ai_ranker scored %d products", len(ranked))
    return ranked
