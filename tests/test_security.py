"""Tests for security.py."""

import pytest

import clean_grocery_bot.security as security_module
from clean_grocery_bot.security import is_chat_allowed, verify_webhook_secret


@pytest.fixture(autouse=True)
def reset_security_cache() -> None:
    """Reset module-level caches and client before each test."""
    security_module._ssm_client = None
    security_module._allowed_chat_ids = None
    yield
    security_module._ssm_client = None
    security_module._allowed_chat_ids = None


def _make_event(token: str | None = None) -> dict:
    headers = {}
    if token is not None:
        headers["x-telegram-bot-api-secret-token"] = token
    return {"headers": headers}


def _mock_ssm(mocker, *, webhook_secret: str = "correct-secret", allowed_ids: str = "111,222,333"):  # noqa: S107
    mock_client = mocker.MagicMock()
    mock_client.get_parameter.side_effect = lambda Name, WithDecryption: {
        "Parameter": {"Value": webhook_secret if "webhook-secret" in Name else allowed_ids}
    }
    mocker.patch.object(security_module, "_get_ssm_client", return_value=mock_client)
    return mock_client


# --- verify_webhook_secret ---


def test_verify_webhook_secret_valid(mocker) -> None:
    _mock_ssm(mocker)
    assert verify_webhook_secret(_make_event("correct-secret")) is True


def test_verify_webhook_secret_invalid(mocker) -> None:
    _mock_ssm(mocker)
    assert verify_webhook_secret(_make_event("wrong-secret")) is False


def test_verify_webhook_secret_missing_header(mocker) -> None:
    """Missing header returns False without calling SSM."""
    mock_client = _mock_ssm(mocker)
    assert verify_webhook_secret(_make_event(token=None)) is False
    mock_client.get_parameter.assert_not_called()


def test_verify_webhook_secret_empty_headers(mocker) -> None:
    """Event with no headers key returns False without calling SSM."""
    mock_client = _mock_ssm(mocker)
    assert verify_webhook_secret({}) is False
    mock_client.get_parameter.assert_not_called()


# --- is_chat_allowed ---


def test_is_chat_allowed_valid(mocker) -> None:
    _mock_ssm(mocker, allowed_ids="111,222,333")
    assert is_chat_allowed(222) is True


def test_is_chat_allowed_invalid(mocker) -> None:
    _mock_ssm(mocker, allowed_ids="111,222,333")
    assert is_chat_allowed(999) is False


def test_is_chat_allowed_caches_result(mocker) -> None:
    """SSM is only called once even when is_chat_allowed is called multiple times."""
    mock_client = _mock_ssm(mocker, allowed_ids="42")
    assert is_chat_allowed(42) is True
    assert is_chat_allowed(42) is True
    assert is_chat_allowed(99) is False
    # get_parameter called exactly once (for the allowed-ids fetch)
    mock_client.get_parameter.assert_called_once()


def test_is_chat_allowed_whitespace_ids(mocker) -> None:
    """Handles extra whitespace around IDs in the SSM value."""
    _mock_ssm(mocker, allowed_ids=" 42 , 99 , 7 ")
    assert is_chat_allowed(42) is True
    assert is_chat_allowed(7) is True
    assert is_chat_allowed(1) is False
