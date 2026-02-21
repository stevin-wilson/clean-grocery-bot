"""Webhook token verification and chat-ID whitelist enforcement."""

from __future__ import annotations

import hmac
import logging
from typing import TYPE_CHECKING, Any

import boto3

if TYPE_CHECKING:
    from mypy_boto3_ssm import SSMClient

logger = logging.getLogger(__name__)

_SSM_WEBHOOK_SECRET = "/clean-grocery-bot/webhook-secret"  # noqa: S105
_SSM_ALLOWED_CHAT_IDS = "/clean-grocery-bot/allowed-chat-ids"

_ssm_client: SSMClient | None = None
_allowed_chat_ids: set[int] | None = None


def _get_ssm_client() -> SSMClient:
    global _ssm_client
    if _ssm_client is None:
        _ssm_client = boto3.client("ssm")  # type: ignore[assignment]
    return _ssm_client


def _fetch_parameter(name: str) -> str:
    response = _get_ssm_client().get_parameter(Name=name, WithDecryption=True)
    return str(response["Parameter"]["Value"])


def verify_webhook_secret(event: dict[str, Any]) -> bool:
    """Return True if the request carries the correct Telegram webhook secret.

    API Gateway normalises header names to lowercase, so we look for
    ``x-telegram-bot-api-secret-token``.  Comparison is done with
    :func:`hmac.compare_digest` to prevent timing-oracle attacks.

    Args:
        event: The raw Lambda event dict from API Gateway.

    Returns:
        ``True`` if the secret header matches the value stored in Parameter Store.
    """
    headers: dict[str, str] = event.get("headers") or {}
    token = headers.get("x-telegram-bot-api-secret-token", "")
    if not token:
        logger.warning("Webhook request missing secret token header")
        return False

    expected = _fetch_parameter(_SSM_WEBHOOK_SECRET)
    return hmac.compare_digest(token, expected)


def is_chat_allowed(chat_id: int) -> bool:
    """Return True if *chat_id* appears in the Parameter Store whitelist.

    The allowed-chat-ids parameter is a comma-separated list of integers,
    e.g. ``"123456789,987654321"``.  The parsed set is cached at module
    level so SSM is only queried once per Lambda cold start.

    Args:
        chat_id: The Telegram chat ID to check.

    Returns:
        ``True`` if the chat ID is whitelisted.
    """
    global _allowed_chat_ids
    if _allowed_chat_ids is None:
        raw = _fetch_parameter(_SSM_ALLOWED_CHAT_IDS)
        _allowed_chat_ids = {int(cid.strip()) for cid in raw.split(",") if cid.strip()}
    return chat_id in _allowed_chat_ids
