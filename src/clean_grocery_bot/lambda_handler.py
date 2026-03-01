"""AWS Lambda entry point — orchestrates the full 15-step request flow."""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mypy_boto3_ssm import SSMClient

import boto3
import httpx

from clean_grocery_bot.ai_ranker import analyze_label_image, rank_products
from clean_grocery_bot.config_loader import load_config
from clean_grocery_bot.food_search import get_taxonomy_categories, search_products
from clean_grocery_bot.image_utils import prepare_image_for_bedrock
from clean_grocery_bot.models import DietaryConfig, LabelAnalysis, RankedProduct
from clean_grocery_bot.pre_filter import filter_products
from clean_grocery_bot.security import is_chat_allowed, verify_webhook_secret

logger = logging.getLogger(__name__)

_SSM_TELEGRAM_TOKEN = "/clean-grocery-bot/telegram-token"  # noqa: S105
_TELEGRAM_API = "https://api.telegram.org"

_bot_token: str | None = None

_VERDICT_EMOJI: dict[str, str] = {
    "Very Clean": "\u2705",  # ✅
    "Acceptable": "\u26a0\ufe0f",  # ⚠️
    "Avoid": "\u274c",  # ❌
}


def _get_bot_token() -> str:
    global _bot_token
    if _bot_token is None:
        ssm: SSMClient = boto3.client("ssm")  # type: ignore[assignment]
        response = ssm.get_parameter(Name=_SSM_TELEGRAM_TOKEN, WithDecryption=True)
        value = response["Parameter"].get("Value")
        if value is None:
            raise ValueError("SSM parameter has no Value")  # noqa: TRY003
        _bot_token = str(value)
    return _bot_token


def _parse_user_message(text: str) -> tuple[str, int | None]:
    """Extract search term and optional count from user input.

    Supported patterns (case-insensitive):
      * ``"cereal"``         → ``("cereal", None)``
      * ``"top 5 cereals"`` → ``("cereals", 5)``
      * ``"3 yogurts"``     → ``("yogurts", 3)``

    Args:
        text: Raw message text from the Telegram user.

    Returns:
        A ``(search_term, count_or_none)`` tuple.
    """
    stripped = text.strip()
    match = re.match(r"(?:top\s+)?(\d+)\s+(.+)", stripped, re.IGNORECASE)
    if match:
        return match.group(2).strip(), int(match.group(1))
    return stripped, None


def _format_response(ranked: list[RankedProduct], search_term: str, config: DietaryConfig) -> str:
    """Render ranked products as a Telegram Markdown message.

    Args:
        ranked: Scored products sorted by descending score.
        search_term: The user's original search term (used in the header).
        config: Dietary config (reserved for future format variants).

    Returns:
        A Telegram-safe Markdown string.
    """
    lines: list[str] = [f'*Top results for "{search_term}":*\n']
    for i, product in enumerate(ranked, 1):
        emoji = _VERDICT_EMOJI.get(product.verdict, "")
        lines.append(f"*{i}. {product.name}* ({product.brand})")
        lines.append(f"   {emoji} {product.verdict} — Score: {product.score}/100")
        for bullet in product.bullets:
            lines.append(f"   • {bullet}")
        if product.harms:
            lines.append("   *Evidence:*")
            for harm in product.harms:
                lines.append(f"   ⚠ *{harm.ingredient}:* {harm.evidence}")
        lines.append("")
    return "\n".join(lines)


def _send_telegram_message(chat_id: int, text: str, token: str) -> None:
    """POST a message to the Telegram Bot API.

    Args:
        chat_id: Destination Telegram chat ID.
        text: Message text (Markdown formatted).
        token: Telegram bot token.
    """
    url = f"{_TELEGRAM_API}/bot{token}/sendMessage"
    with httpx.Client(timeout=10.0) as client:
        response = client.post(
            url,
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
        )
    if not response.is_success:
        logger.warning("Telegram sendMessage returned %d", response.status_code)


def _download_telegram_photo(photo_list: list[dict[str, Any]], token: str) -> bytes:
    """Download the highest-resolution photo from a Telegram photo array.

    Telegram sends photos as an ascending-size array of ``PhotoSize`` objects.
    We pick the last (largest) entry, resolve its ``file_path`` via the
    ``getFile`` API, and download the raw bytes.

    Args:
        photo_list: The ``message.photo`` array from Telegram.
        token: Telegram bot token.

    Returns:
        Raw image bytes.
    """
    file_id: str = photo_list[-1]["file_id"]

    with httpx.Client(timeout=15.0) as client:
        # Resolve file_id → file_path
        get_file_url = f"{_TELEGRAM_API}/bot{token}/getFile"
        file_resp = client.post(get_file_url, json={"file_id": file_id})
        file_resp.raise_for_status()
        file_path: str = file_resp.json()["result"]["file_path"]

        # Download the actual file
        download_url = f"{_TELEGRAM_API}/file/bot{token}/{file_path}"
        dl_resp = client.get(download_url)
        dl_resp.raise_for_status()

    return dl_resp.content


def _format_label_response(analysis: LabelAnalysis) -> str:
    """Render a label analysis as a Telegram Markdown message."""
    emoji = _VERDICT_EMOJI.get(analysis.verdict, "")
    lines: list[str] = [
        f"{emoji} *{analysis.verdict}* — {analysis.score}/100",
        "",
        "*Ingredient Label Analysis*",
        "",
        f"*Product:* {analysis.product_name}",
        f"Score: {analysis.score}/100 — {emoji} {analysis.verdict}",
        f"*Extracted ingredients:* {analysis.ingredients_text}",
        "",
    ]
    for bullet in analysis.bullets:
        lines.append(f"• {bullet}")
    if analysis.harms:
        lines.append("")
        lines.append("*Clinical/Academic Evidence:*")
        for harm in analysis.harms:
            lines.append(f"  ⚠ *{harm.ingredient}:* {harm.evidence}")
    if analysis.flags:
        lines.append("")
        lines.append(f"{emoji} *Flagged:* {', '.join(analysis.flags)}")
    lines.append("")
    lines.append(f"{emoji} *{analysis.verdict}* — {analysis.score}/100")
    return "\n".join(lines)


def _send_typing_indicator(chat_id: int, token: str) -> None:
    """Send a 'typing' chat action so the user sees a progress indicator."""
    url = f"{_TELEGRAM_API}/bot{token}/sendChatAction"
    with httpx.Client(timeout=5.0) as client:
        client.post(url, json={"chat_id": chat_id, "action": "typing"})


def _handle_photo_message(
    chat_id: int,
    photo_list: list[dict[str, Any]],
    caption: str,
    token: str,
) -> None:
    """Process a photo message: download, resize, analyze, and reply."""
    # Download photo from Telegram
    try:
        raw_bytes = _download_telegram_photo(photo_list, token)
    except (httpx.HTTPStatusError, httpx.TimeoutException):
        logger.warning("Failed to download photo for chat %d", chat_id)
        _send_telegram_message(chat_id, "I couldn't download your photo. Please try sending it again.", token)
        return

    # Resize for Bedrock
    try:
        image_bytes, image_format = prepare_image_for_bedrock(raw_bytes)
    except ValueError:
        _send_telegram_message(
            chat_id,
            "I couldn't process that image. Please send a photo (not a document) of the ingredient label.",
            token,
        )
        return

    _send_typing_indicator(chat_id, token)

    config = load_config()
    analysis = analyze_label_image(image_bytes, image_format, config, caption or None)

    # Check if model could actually read the label
    if not analysis.ingredients_text.strip():
        _send_telegram_message(
            chat_id,
            "I couldn't read the ingredients on that label. Please try again with a clearer, well-lit photo.",
            token,
        )
        return

    response_text = _format_label_response(analysis)
    _send_telegram_message(chat_id, response_text, token)


def _handle_text_message(chat_id: int, text: str, token: str) -> None:
    """Process a text message: search, filter, rank, and reply."""
    config = load_config()

    search_term, requested_count = _parse_user_message(text)
    count = min(
        requested_count if requested_count is not None else config.recommendations.default_count,
        config.recommendations.max_count,
    )

    categories = get_taxonomy_categories(search_term)

    if not categories:
        _send_telegram_message(
            chat_id,
            "I couldn't find that category. Try something like 'yogurt', 'crackers', or 'cereal'.",
            token,
        )
        return

    products = search_products(
        categories=categories,
        country=config.market.country,
        max_results=config.recommendations.max_prefetch,
    )

    filtered = filter_products(products, config)

    if not filtered:
        if config.whole_food_fallback.enabled:
            _send_telegram_message(
                chat_id,
                f"No clean packaged options found for '{search_term}'.\n"
                "Consider a whole-food alternative — fresh, unprocessed options are always cleanest!",
                token,
            )
        else:
            _send_telegram_message(
                chat_id,
                f"No clean options found for '{search_term}'.",
                token,
            )
        return

    ranked = rank_products(filtered, config)
    response_text = _format_response(ranked[:count], search_term, config)
    _send_telegram_message(chat_id, response_text, token)


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    """AWS Lambda handler — webhook processing pipeline.

    Always returns HTTP 200 to Telegram.  Non-200 responses would cause
    Telegram to retry the webhook indefinitely.

    Args:
        event: API Gateway proxy event.
        context: Lambda context object (unused).

    Returns:
        API Gateway response dict with ``statusCode`` and ``body``.
    """
    if not verify_webhook_secret(event):
        logger.warning("Rejected request: invalid webhook secret")
        return {"statusCode": 403, "body": "Forbidden"}

    try:
        body: dict[str, Any] = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return {"statusCode": 200, "body": "OK"}

    message: dict[str, Any] = body.get("message") or {}
    chat_obj: Any = message.get("chat") or {}
    chat_raw: Any = chat_obj.get("id")
    chat_id: int | None = int(chat_raw) if isinstance(chat_raw, int) else None
    text: str = (message.get("text") or "").strip()
    photo_list: list[dict[str, Any]] = message.get("photo") or []
    caption: str = (message.get("caption") or "").strip()

    if not chat_id or (not text and not photo_list):
        return {"statusCode": 200, "body": "OK"}

    if not is_chat_allowed(chat_id):
        logger.info("Ignored message from non-whitelisted chat %d", chat_id)
        return {"statusCode": 200, "body": "OK"}

    token = _get_bot_token()

    try:
        if photo_list:
            _handle_photo_message(chat_id, photo_list, caption, token)
        else:
            _handle_text_message(chat_id, text, token)
    except httpx.TimeoutException:
        logger.warning("Timeout processing chat %d, notifying user", chat_id)
        _send_telegram_message(
            chat_id,
            "The request is taking too long to process. Please try again in a moment.",
            token,
        )
    except Exception:
        logger.exception("Unhandled error processing chat %d", chat_id)
        _send_telegram_message(chat_id, "Sorry, something went wrong. Please try again.", token)

    return {"statusCode": 200, "body": "OK"}
