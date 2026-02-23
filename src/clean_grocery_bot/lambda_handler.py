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

from clean_grocery_bot.ai_ranker import rank_products
from clean_grocery_bot.config_loader import load_config
from clean_grocery_bot.food_search import get_taxonomy_categories, search_products
from clean_grocery_bot.models import DietaryConfig, RankedProduct
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


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    """AWS Lambda handler — full 15-step webhook processing pipeline.

    Always returns HTTP 200 to Telegram.  Non-200 responses would cause
    Telegram to retry the webhook indefinitely.

    Args:
        event: API Gateway proxy event.
        context: Lambda context object (unused).

    Returns:
        API Gateway response dict with ``statusCode`` and ``body``.
    """
    # Step 3 — verify webhook secret
    if not verify_webhook_secret(event):
        logger.warning("Rejected request: invalid webhook secret")
        return {"statusCode": 403, "body": "Forbidden"}

    # Parse Telegram body
    try:
        body: dict[str, Any] = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return {"statusCode": 200, "body": "OK"}

    message: dict[str, Any] = body.get("message") or {}
    chat_obj: Any = message.get("chat") or {}
    chat_raw: Any = chat_obj.get("id")
    chat_id: int | None = int(chat_raw) if isinstance(chat_raw, int) else None
    text: str = (message.get("text") or "").strip()

    if not chat_id or not text:
        return {"statusCode": 200, "body": "OK"}

    # Step 4 — check chat ID whitelist (silently ignore unauthorized chats)
    if not is_chat_allowed(chat_id):
        logger.info("Ignored message from non-whitelisted chat %d", chat_id)
        return {"statusCode": 200, "body": "OK"}

    token = _get_bot_token()

    try:
        # Step 5 — load config
        config = load_config()

        # Parse user message
        search_term, requested_count = _parse_user_message(text)
        count = min(
            requested_count if requested_count is not None else config.recommendations.default_count,
            config.recommendations.max_count,
        )

        # Step 6 — taxonomy lookup
        categories = get_taxonomy_categories(search_term)

        # Step 7 — Gate 1: no taxonomy match
        if not categories:
            _send_telegram_message(
                chat_id,
                "I couldn't find that category. Try something like 'yogurt', 'crackers', or 'cereal'.",
                token,
            )
            return {"statusCode": 200, "body": "OK"}

        # Steps 8-9 -- search & filter missing-ingredient products
        products = search_products(
            categories=categories,
            country=config.market.country,
            max_results=config.recommendations.max_prefetch,
        )

        # Step 10 — pre-filter (seed oils, additives, user exclusions)
        filtered = filter_products(products, config)

        # Step 11 — Gate 2: nothing survives filtering
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
            return {"statusCode": 200, "body": "OK"}

        # Steps 12-13 -- AI ranking
        ranked = rank_products(filtered, config)

        # Step 14 — format response (limit to requested count)
        response_text = _format_response(ranked[:count], search_term, config)

        # Step 15 — send to user
        _send_telegram_message(chat_id, response_text, token)

    except httpx.TimeoutException:
        logger.warning("Timeout fetching data for chat %d, notifying user", chat_id)
        _send_telegram_message(
            chat_id,
            "The grocery database is taking too long to respond. Please try again in a moment.",
            token,
        )
    except Exception:
        logger.exception("Unhandled error processing chat %d", chat_id)
        _send_telegram_message(chat_id, "Sorry, something went wrong. Please try again.", token)

    return {"statusCode": 200, "body": "OK"}
