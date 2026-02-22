"""Tests for lambda_handler.py — pure helper functions and full handler pipeline."""

import json

import httpx
import pytest
import respx

import clean_grocery_bot.lambda_handler as lambda_handler_module
from clean_grocery_bot.lambda_handler import (
    _format_response,
    _get_bot_token,
    _parse_user_message,
    _send_telegram_message,
    handler,
)
from clean_grocery_bot.models import (
    CleanlinessCriteria,
    DietaryConfig,
    Market,
    Priority,
    Product,
    RankedProduct,
    WholeFoodFallback,
)


def _make_config() -> DietaryConfig:
    return DietaryConfig(
        cleanliness_criteria=CleanlinessCriteria(
            priorities=[Priority(rank=1, label="No seed oils", description="Avoid seed oils")]
        ),
        market=Market(country="US", country_name="United States"),
    )


def _make_ranked(name: str = "Oat Flakes", score: int = 90, verdict: str = "Very Clean") -> RankedProduct:
    return RankedProduct(
        name=name,
        brand="Good Brand",
        score=score,
        verdict=verdict,  # type: ignore[arg-type]
        bullets=["Clean ingredients", "Short list"],
    )


CONFIG = _make_config()


@pytest.fixture(autouse=True)
def reset_bot_token_cache() -> None:
    """Reset the module-level _bot_token cache before and after each test."""
    lambda_handler_module._bot_token = None
    yield
    lambda_handler_module._bot_token = None


def _make_event(
    text: str = "cereal",
    chat_id: int = 12345,
    secret: str = "correct-secret",  # noqa: S107
    body: str | None = None,
) -> dict:
    """Build a minimal API Gateway proxy event for handler() tests."""
    if body is None:
        body = json.dumps({"message": {"chat": {"id": chat_id}, "text": text}})
    return {"headers": {"x-telegram-bot-api-secret-token": secret}, "body": body}


def _mock_pipeline(mocker, **overrides) -> dict:
    """Patch all handler() dependencies to happy-path defaults.

    Returns a dict of mocks keyed by short name so tests can make targeted
    assertions or set side_effect overrides.
    """
    product = Product(name="Oat Flakes", brand="Good Brand", ingredients_text="oats", ingredients_tags=[])
    mocks = {
        "verify_webhook_secret": mocker.patch(
            "clean_grocery_bot.lambda_handler.verify_webhook_secret", return_value=True
        ),
        "is_chat_allowed": mocker.patch("clean_grocery_bot.lambda_handler.is_chat_allowed", return_value=True),
        "get_bot_token": mocker.patch("clean_grocery_bot.lambda_handler._get_bot_token", return_value="fake-token"),
        "load_config": mocker.patch("clean_grocery_bot.lambda_handler.load_config", return_value=_make_config()),
        "get_taxonomy_categories": mocker.patch(
            "clean_grocery_bot.lambda_handler.get_taxonomy_categories", return_value=["en:cereals"]
        ),
        "search_products": mocker.patch("clean_grocery_bot.lambda_handler.search_products", return_value=[product]),
        "filter_products": mocker.patch("clean_grocery_bot.lambda_handler.filter_products", return_value=[product]),
        "rank_products": mocker.patch("clean_grocery_bot.lambda_handler.rank_products", return_value=[_make_ranked()]),
        "send_telegram": mocker.patch("clean_grocery_bot.lambda_handler._send_telegram_message"),
    }
    for key, value in overrides.items():
        mocks[key].return_value = value
    return mocks


# --- _parse_user_message ---


def test_parse_bare_term() -> None:
    assert _parse_user_message("cereal") == ("cereal", None)


def test_parse_top_n_term() -> None:
    assert _parse_user_message("top 5 cereals") == ("cereals", 5)


def test_parse_n_term() -> None:
    assert _parse_user_message("3 yogurts") == ("yogurts", 3)


def test_parse_strips_whitespace() -> None:
    assert _parse_user_message("  crackers  ") == ("crackers", None)


def test_parse_case_insensitive_top() -> None:
    assert _parse_user_message("TOP 3 chips") == ("chips", 3)


def test_parse_single_word_with_extra_spaces() -> None:
    term, count = _parse_user_message("  oats  ")
    assert term == "oats"
    assert count is None


# --- _format_response ---


def test_format_response_contains_product_name() -> None:
    ranked = [_make_ranked("Quinoa Puffs")]
    result = _format_response(ranked, "cereal", CONFIG)
    assert "Quinoa Puffs" in result


def test_format_response_contains_score() -> None:
    ranked = [_make_ranked(score=85)]
    result = _format_response(ranked, "cereal", CONFIG)
    assert "85" in result


def test_format_response_contains_verdict() -> None:
    ranked = [_make_ranked(verdict="Acceptable")]
    result = _format_response(ranked, "chips", CONFIG)
    assert "Acceptable" in result


def test_format_response_contains_bullets() -> None:
    ranked = [_make_ranked()]
    result = _format_response(ranked, "oats", CONFIG)
    assert "Clean ingredients" in result
    assert "Short list" in result


def test_format_response_contains_search_term_header() -> None:
    ranked = [_make_ranked()]
    result = _format_response(ranked, "granola", CONFIG)
    assert "granola" in result


def test_format_response_multiple_products_numbered() -> None:
    ranked = [_make_ranked("Product A"), _make_ranked("Product B", score=70, verdict="Acceptable")]
    result = _format_response(ranked, "snacks", CONFIG)
    assert "1." in result
    assert "2." in result
    assert "Product A" in result
    assert "Product B" in result


# --- _get_bot_token ---


def test_get_bot_token_returns_ssm_value(mocker) -> None:
    mock_ssm = mocker.MagicMock()
    mock_ssm.get_parameter.return_value = {"Parameter": {"Value": "my-bot-token"}}
    mocker.patch("clean_grocery_bot.lambda_handler.boto3.client", return_value=mock_ssm)

    result = _get_bot_token()

    assert result == "my-bot-token"
    mock_ssm.get_parameter.assert_called_once_with(Name="/clean-grocery-bot/telegram-token", WithDecryption=True)


def test_get_bot_token_caches_value(mocker) -> None:
    mock_ssm = mocker.MagicMock()
    mock_ssm.get_parameter.return_value = {"Parameter": {"Value": "my-bot-token"}}
    mocker.patch("clean_grocery_bot.lambda_handler.boto3.client", return_value=mock_ssm)

    result1 = _get_bot_token()
    result2 = _get_bot_token()

    assert result1 == "my-bot-token"
    assert result2 == "my-bot-token"
    mock_ssm.get_parameter.assert_called_once()


def test_get_bot_token_raises_when_value_is_missing(mocker) -> None:
    mock_ssm = mocker.MagicMock()
    mock_ssm.get_parameter.return_value = {"Parameter": {}}  # no "Value" key
    mocker.patch("clean_grocery_bot.lambda_handler.boto3.client", return_value=mock_ssm)

    with pytest.raises(ValueError):
        _get_bot_token()


# --- _send_telegram_message ---

_SEND_URL = "https://api.telegram.org/botfake-token/sendMessage"


@respx.mock
def test_send_telegram_message_posts_correct_payload() -> None:
    respx.post(_SEND_URL).mock(return_value=httpx.Response(200, json={"ok": True}))

    _send_telegram_message(chat_id=99, text="Hello", token="fake-token")  # noqa: S106

    assert respx.calls.call_count == 1
    payload = json.loads(respx.calls[0].request.content)
    assert payload == {"chat_id": 99, "text": "Hello", "parse_mode": "Markdown"}


@respx.mock
def test_send_telegram_message_non_200_does_not_raise() -> None:
    respx.post(_SEND_URL).mock(return_value=httpx.Response(400))

    # Non-2xx response is logged as a warning, not raised
    _send_telegram_message(chat_id=99, text="Hello", token="fake-token")  # noqa: S106


@respx.mock
def test_send_telegram_message_timeout_propagates() -> None:
    respx.post(_SEND_URL).mock(side_effect=httpx.TimeoutException("timed out"))

    with pytest.raises(httpx.TimeoutException):
        _send_telegram_message(chat_id=99, text="Hello", token="fake-token")  # noqa: S106


@respx.mock
def test_send_telegram_message_connect_error_propagates() -> None:
    respx.post(_SEND_URL).mock(side_effect=httpx.ConnectError("connection refused"))

    with pytest.raises(httpx.ConnectError):
        _send_telegram_message(chat_id=99, text="Hello", token="fake-token")  # noqa: S106


# --- handler() — early-exit branches ---


def test_handler_rejects_invalid_webhook_secret(mocker) -> None:
    mocker.patch("clean_grocery_bot.lambda_handler.verify_webhook_secret", return_value=False)

    result = handler(_make_event(), context=None)

    assert result == {"statusCode": 403, "body": "Forbidden"}


def test_handler_returns_ok_on_invalid_json_body(mocker) -> None:
    mocker.patch("clean_grocery_bot.lambda_handler.verify_webhook_secret", return_value=True)

    result = handler(_make_event(body="not-json"), context=None)

    assert result == {"statusCode": 200, "body": "OK"}


def test_handler_returns_ok_on_missing_chat_id(mocker) -> None:
    mocker.patch("clean_grocery_bot.lambda_handler.verify_webhook_secret", return_value=True)
    body = json.dumps({"message": {"text": "cereal"}})  # no "chat" key

    result = handler(_make_event(body=body), context=None)

    assert result == {"statusCode": 200, "body": "OK"}


def test_handler_returns_ok_on_empty_text(mocker) -> None:
    mocker.patch("clean_grocery_bot.lambda_handler.verify_webhook_secret", return_value=True)
    body = json.dumps({"message": {"chat": {"id": 42}, "text": ""}})

    result = handler(_make_event(body=body), context=None)

    assert result == {"statusCode": 200, "body": "OK"}


def test_handler_ignores_non_whitelisted_chat(mocker) -> None:
    mocker.patch("clean_grocery_bot.lambda_handler.verify_webhook_secret", return_value=True)
    mocker.patch("clean_grocery_bot.lambda_handler.is_chat_allowed", return_value=False)
    mock_token = mocker.patch("clean_grocery_bot.lambda_handler._get_bot_token")
    mock_send = mocker.patch("clean_grocery_bot.lambda_handler._send_telegram_message")

    result = handler(_make_event(), context=None)

    assert result == {"statusCode": 200, "body": "OK"}
    mock_token.assert_not_called()
    mock_send.assert_not_called()


# --- handler() — pipeline branches ---


def test_handler_gate1_no_taxonomy_match_sends_help_message(mocker) -> None:
    mocks = _mock_pipeline(mocker)
    mocks["get_taxonomy_categories"].return_value = []

    result = handler(_make_event(text="xyzzy"), context=None)

    assert result == {"statusCode": 200, "body": "OK"}
    mocks["send_telegram"].assert_called_once()
    sent_text = mocks["send_telegram"].call_args.args[1]
    assert "couldn't find" in sent_text
    mocks["rank_products"].assert_not_called()


def test_handler_gate2_filtered_out_sends_whole_food_fallback(mocker) -> None:
    mocks = _mock_pipeline(mocker)
    mocks["filter_products"].return_value = []
    # Default config has WholeFoodFallback(enabled=True)

    result = handler(_make_event(), context=None)

    assert result == {"statusCode": 200, "body": "OK"}
    mocks["send_telegram"].assert_called_once()
    sent_text = mocks["send_telegram"].call_args.args[1]
    assert "whole-food alternative" in sent_text
    mocks["rank_products"].assert_not_called()


def test_handler_gate2_filtered_out_fallback_disabled(mocker) -> None:
    config_no_fallback = DietaryConfig(
        cleanliness_criteria=CleanlinessCriteria(
            priorities=[Priority(rank=1, label="No seed oils", description="Avoid seed oils")]
        ),
        market=Market(country="US", country_name="United States"),
        whole_food_fallback=WholeFoodFallback(enabled=False),
    )
    mocks = _mock_pipeline(mocker)
    mocks["filter_products"].return_value = []
    mocks["load_config"].return_value = config_no_fallback

    result = handler(_make_event(), context=None)

    assert result == {"statusCode": 200, "body": "OK"}
    mocks["send_telegram"].assert_called_once()
    sent_text = mocks["send_telegram"].call_args.args[1]
    assert "No clean options found" in sent_text
    assert "whole-food alternative" not in sent_text


def test_handler_full_happy_path(mocker) -> None:
    mocks = _mock_pipeline(mocker)

    result = handler(_make_event(text="cereal"), context=None)

    assert result == {"statusCode": 200, "body": "OK"}
    mocks["get_taxonomy_categories"].assert_called_once_with("cereal")
    mocks["search_products"].assert_called_once()
    mocks["filter_products"].assert_called_once()
    mocks["rank_products"].assert_called_once()
    mocks["send_telegram"].assert_called_once()
    sent_text = mocks["send_telegram"].call_args.args[1]
    assert "Oat Flakes" in sent_text


def test_handler_happy_path_respects_count_limit(mocker) -> None:
    five_ranked = [_make_ranked(name=f"Product {i}") for i in range(1, 6)]
    mocks = _mock_pipeline(mocker)
    mocks["rank_products"].return_value = five_ranked

    result = handler(_make_event(text="top 2 cereals"), context=None)

    assert result == {"statusCode": 200, "body": "OK"}
    sent_text = mocks["send_telegram"].call_args.args[1]
    assert "Product 1" in sent_text
    assert "Product 2" in sent_text
    assert "Product 3" not in sent_text


def test_handler_exception_in_pipeline_sends_error_and_returns_200(mocker) -> None:
    mocks = _mock_pipeline(mocker)
    mocks["load_config"].side_effect = RuntimeError("boom")

    result = handler(_make_event(), context=None)

    assert result == {"statusCode": 200, "body": "OK"}
    mocks["send_telegram"].assert_called_once()
    sent_text = mocks["send_telegram"].call_args.args[1]
    assert "something went wrong" in sent_text


def test_handler_token_fetch_failure_propagates(mocker) -> None:
    mocker.patch("clean_grocery_bot.lambda_handler.verify_webhook_secret", return_value=True)
    mocker.patch("clean_grocery_bot.lambda_handler.is_chat_allowed", return_value=True)
    mocker.patch("clean_grocery_bot.lambda_handler._get_bot_token", side_effect=ValueError("SSM down"))
    mock_send = mocker.patch("clean_grocery_bot.lambda_handler._send_telegram_message")

    with pytest.raises(ValueError):
        handler(_make_event(), context=None)

    mock_send.assert_not_called()


# --- handler() — body-parsing edge cases ---


def test_handler_body_none_treated_as_empty(mocker) -> None:
    mocker.patch("clean_grocery_bot.lambda_handler.verify_webhook_secret", return_value=True)
    event = {"headers": {"x-telegram-bot-api-secret-token": "s"}, "body": None}

    result = handler(event, context=None)

    assert result == {"statusCode": 200, "body": "OK"}


def test_handler_message_key_missing_returns_ok(mocker) -> None:
    mocker.patch("clean_grocery_bot.lambda_handler.verify_webhook_secret", return_value=True)
    body = json.dumps({"update_id": 1})  # no "message" key

    result = handler(_make_event(body=body), context=None)

    assert result == {"statusCode": 200, "body": "OK"}
