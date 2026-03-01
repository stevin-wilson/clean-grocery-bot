"""AWS Bedrock integration — ingredient-cleanliness scoring and ranking."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any, cast

import boto3
from pydantic import BaseModel, ConfigDict, TypeAdapter

from clean_grocery_bot.models import DietaryConfig, LabelAnalysis, Product, RankedProduct

if TYPE_CHECKING:
    from mypy_boto3_bedrock_runtime import BedrockRuntimeClient

logger = logging.getLogger(__name__)

_DEFAULT_MODEL_ID = "amazon.nova-2-lite-v1:0"
_MAX_TOKENS = 4096

_bedrock_client: BedrockRuntimeClient | None = None
_ranked_product_list_adapter: TypeAdapter[list[RankedProduct]] = TypeAdapter(list[RankedProduct])
_label_analysis_adapter: TypeAdapter[LabelAnalysis] = TypeAdapter(LabelAnalysis)


class _OcrResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    product_name: str = "Unknown"
    ingredients_text: str = ""


_ocr_result_adapter: TypeAdapter[_OcrResult] = TypeAdapter(_OcrResult)


def _get_bedrock_client() -> BedrockRuntimeClient:
    global _bedrock_client
    if _bedrock_client is None:
        _bedrock_client = boto3.client("bedrock-runtime", region_name="us-east-2")  # type: ignore[assignment]
    return _bedrock_client


def _build_prompt(products: list[Product], config: DietaryConfig) -> str:
    """Build the scoring prompt from the product list and user config priorities."""
    rubric_lines = "\n".join(
        f"  Priority {p.rank}: {p.label} — {p.description}" for p in config.cleanliness_criteria.priorities
    )

    product_lines = "\n".join(
        f"{i}. {p.name} (Brand: {p.brand})\n   Ingredients: {p.ingredients_text}" for i, p in enumerate(products, 1)
    )

    if config.household.members:
        member_lines = "\n".join(f"  - {m}" for m in config.household.members)
        household_section = (
            f"Household profiles — flag any ingredient that poses a specific risk to a member:\n{member_lines}\n\n"
        )
    else:
        household_section = ""

    return f"""You are a registered dietitian and nutritionist. Score each product's ingredient cleanliness (0-100).

Scoring priorities (in order of importance):
{rubric_lines}

Professional scoring guidance:
- Ingredient order matters: ingredients are listed by descending weight. An undesirable
  ingredient near the top of the list is far more concerning than one listed last.
- NOVA classification: prefer minimally processed foods (NOVA 1-2). Ultra-processed
  products (NOVA 4) should score lower even without explicit harmful additives.
- Whole, recognisable ingredients are a positive signal and can increase the score.
- A short ingredient list of real foods scores higher than a long list, even if the
  long list contains no outright harmful items.
- Apply your professional judgment — do not treat the above priorities as a mechanical
  checklist. Weigh each factor in proportion to its impact on ingredient cleanliness.

Verdict bands:
  - 80-100: "Very Clean" — minimal processing, whole ingredients, no or trace harmful additives
  - 50-79:  "Acceptable" — moderate processing or minor harmful ingredients not in primary positions
  - 0-49:   "Avoid" — harmful ingredients are primary components or product is ultra-processed

{household_section}Products to score:
{product_lines}

Return ONLY a JSON array (no markdown, no extra text) with one object per product.
Each object must have exactly these fields:
  "name"    -- string (product name as given above)
  "brand"   -- string
  "score"   -- integer 0-100
  "verdict" -- one of "Very Clean", "Acceptable", "Avoid"
  "bullets" -- array of 2-3 short strings explaining the score
  "harms"   -- array of {{"ingredient": ..., "evidence": ...}} (plain health-claim only, e.g.
               "raises LDL cholesterol" or "classified possible carcinogen by IARC"; no paper citations; [] if none)
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

    model_id = os.environ.get("BEDROCK_MODEL_ID", _DEFAULT_MODEL_ID)
    response: dict[str, Any] = cast(
        "dict[str, Any]",
        client.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": _MAX_TOKENS, "temperature": 0.0},
        ),
    )

    output_text: str = response["output"]["message"]["content"][0]["text"]
    logger.debug("Bedrock raw response (%d chars): %s", len(output_text), output_text[:500])

    # Strip markdown code fences that the model sometimes wraps around the JSON.
    output_text = output_text.strip()
    if output_text.startswith("```"):
        output_text = output_text.split("\n", 1)[-1]
        output_text = output_text.rsplit("```", 1)[0].strip()

    try:
        ranked = _ranked_product_list_adapter.validate_json(output_text)
    except Exception:
        # Log the end of the response to help diagnose truncation issues
        logger.exception(
            "Failed to parse AI ranker output (final 200 chars): ...%s",
            output_text[-200:] if len(output_text) > 200 else output_text,
        )
        raise
    ranked.sort(key=lambda r: r.score, reverse=True)

    logger.info("ai_ranker scored %d products", len(ranked))
    return ranked


def _build_label_prompt(config: DietaryConfig, caption: str | None = None) -> str:
    """Build the scoring prompt for a single ingredient label."""
    rubric_lines = "\n".join(
        f"  Priority {p.rank}: {p.label} — {p.description}" for p in config.cleanliness_criteria.priorities
    )

    if config.household.members:
        member_lines = "\n".join(f"  - {m}" for m in config.household.members)
        household_section = (
            f"Household profiles — flag any ingredient that poses a specific risk to a member:\n{member_lines}\n\n"
        )
    else:
        household_section = ""

    user_note = f"\nUser note: {caption}\n" if caption else ""

    return f"""You are a registered dietitian and nutritionist. Analyze the provided ingredient list.

1. Score the product on ingredient cleanliness (0-100).

Scoring priorities (in order of importance):
{rubric_lines}

Professional scoring guidance:
- Ingredient order matters: ingredients are listed by descending weight. An undesirable
  ingredient near the top of the list is far more concerning than one listed last.
- NOVA classification: prefer minimally processed foods (NOVA 1-2). Ultra-processed
  products (NOVA 4) should score lower even without explicit harmful additives.
- Whole, recognisable ingredients are a positive signal and can increase the score.
- A short ingredient list of real foods scores higher than a long list, even if the
  long list contains no outright harmful items.
- Apply your professional judgment — do not treat the above priorities as a mechanical
  checklist. Weigh each factor in proportion to its impact on ingredient cleanliness.

Verdict bands:
  - 80-100: "Very Clean" — minimal processing, whole ingredients, no or trace harmful additives
  - 50-79:  "Acceptable" — moderate processing or minor harmful ingredients not in primary positions
  - 0-49:   "Avoid" — harmful ingredients are primary components or product is ultra-processed

{household_section}{user_note}Return ONLY a JSON object (no markdown, no extra text) with exactly these fields:
  "product_name"       -- string (product name if known, otherwise "Unknown")
  "ingredients_text"   -- string (all ingredients as provided)
  "score"              -- integer 0-100
  "verdict"            -- one of "Very Clean", "Acceptable", "Avoid"
  "bullets"            -- array of 2-4 short strings explaining the score
  "flags"              -- array of strings listing any concerning ingredients found
  "harms"              -- array of {{"ingredient": ..., "evidence": ...}} (plain health-claim only, e.g.
                          "raises LDL cholesterol" or "classified possible carcinogen by IARC"; no paper citations; [] if none)
"""


def _extract_ingredients_text(
    image_bytes: bytes,
    image_format: str,
    client: BedrockRuntimeClient,
    model_id: str,
) -> tuple[str, str]:
    """Call 1 of 2: extract product name and ingredients text from the image.

    Returns (product_name, ingredients_text).
    """
    ocr_prompt = (
        "Extract the product name and the full ingredients list verbatim from this label image. "
        "Return ONLY a JSON object with exactly these fields: "
        '"product_name" (string, or "Unknown" if not visible) and '
        '"ingredients_text" (string, all ingredients as printed on the label, or "" if not visible).'
    )

    ocr_messages: list[Any] = [
        {
            "role": "user",
            "content": [
                {"image": {"format": image_format, "source": {"bytes": image_bytes}}},
                {"text": ocr_prompt},
            ],
        }
    ]
    response: dict[str, Any] = cast(
        "dict[str, Any]",
        client.converse(
            modelId=model_id,
            messages=ocr_messages,
            inferenceConfig={"maxTokens": 1024, "temperature": 0.0},
        ),
    )

    output_text: str = response["output"]["message"]["content"][0]["text"]
    output_text = output_text.strip()
    if output_text.startswith("```"):
        output_text = output_text.split("\n", 1)[-1]
        output_text = output_text.rsplit("```", 1)[0].strip()

    try:
        ocr_result = _ocr_result_adapter.validate_json(output_text)
    except Exception:
        logger.warning("OCR extraction failed, returning empty defaults: %s", output_text[:200])
        return "Unknown", ""

    return ocr_result.product_name, ocr_result.ingredients_text


def analyze_label_image(
    image_bytes: bytes,
    image_format: str,
    config: DietaryConfig,
    caption: str | None = None,
) -> LabelAnalysis:
    """Send a label image to Bedrock for multimodal ingredient analysis.

    Uses a two-call pipeline: call 1 extracts ingredients via OCR (image → text),
    call 2 scores the extracted ingredients (text only).

    Args:
        image_bytes: JPEG-encoded image bytes (already resized).
        image_format: Image format string for Bedrock (e.g. ``"jpeg"``).
        config: The loaded dietary preference configuration.
        caption: Optional user-provided caption/note.

    Returns:
        A :class:`~clean_grocery_bot.models.LabelAnalysis` with extracted
        ingredients, score, verdict, and flags.

    Raises:
        pydantic.ValidationError: If the model returns JSON that fails schema validation.
        botocore.exceptions.ClientError: On Bedrock API errors.
    """
    client = _get_bedrock_client()
    model_id = os.environ.get("BEDROCK_MODEL_ID", _DEFAULT_MODEL_ID)

    # Call 1: OCR — extract product name and ingredients text from the image.
    ocr_product_name, ocr_ingredients_text = _extract_ingredients_text(image_bytes, image_format, client, model_id)

    # Call 2: Text-only scoring using the extracted ingredients.
    label_prompt = _build_label_prompt(config, caption)
    augmented_prompt = f"Product name: {ocr_product_name}\nIngredients: {ocr_ingredients_text}\n\n{label_prompt}"

    response: dict[str, Any] = cast(
        "dict[str, Any]",
        client.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": augmented_prompt}]}],
            inferenceConfig={"maxTokens": _MAX_TOKENS, "temperature": 0.0},
        ),
    )

    output_text: str = response["output"]["message"]["content"][0]["text"]
    logger.debug("Bedrock label response (%d chars): %s", len(output_text), output_text[:500])

    # Strip markdown code fences that the model sometimes wraps around the JSON.
    output_text = output_text.strip()
    if output_text.startswith("```"):
        output_text = output_text.split("\n", 1)[-1]
        output_text = output_text.rsplit("```", 1)[0].strip()

    try:
        analysis = _label_analysis_adapter.validate_json(output_text)
    except Exception:
        logger.exception(
            "Failed to parse label analysis output (final 200 chars): ...%s",
            output_text[-200:] if len(output_text) > 200 else output_text,
        )
        raise

    # Prefer the OCR-extracted product name; fall back to the analysis value if OCR returned "Unknown".
    if ocr_product_name != "Unknown":
        analysis = analysis.model_copy(update={"product_name": ocr_product_name})

    logger.info("Label analysis: score=%d verdict=%s", analysis.score, analysis.verdict)
    return analysis
