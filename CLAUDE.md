# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies + pre-commit hooks
make install          # or: uv sync --all-groups && uv run pre-commit install

# Run tests with coverage
uv run pytest --cov --cov-config=pyproject.toml --cov-report=term-missing

# Run a single test file
uv run pytest tests/test_ai_ranker.py

# Lint and format check
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/

# Full quality suite (pre-commit + pyright + deptry)
make check

# Build and deploy Lambda
bash deploy.sh        # requires LAMBDA_FUNCTION_NAME and AWS_REGION env vars
```

## Architecture

A serverless Telegram chatbot deployed on AWS Lambda. The request pipeline is:

```
Telegram → API Gateway → Lambda handler
  → security.py     (verify webhook secret + chat whitelist from SSM Parameter Store)
  → food_search.py  (Open Food Facts taxonomy lookup + product search)
  → pre_filter.py   (hard exclude seed oils, artificial additives, user exclusions)
  → ai_ranker.py    (Bedrock scores + ranks; OCR via Nova 2 Lite, scoring via Claude Sonnet 4.6; photo messages use multimodal analysis)
  → lambda_handler  (format and send back to Telegram)
```

**Two message types are handled:**
- **Text messages**: category search flow (search → filter → rank → reply)
- **Photo messages**: label analysis flow (download → resize with Pillow → Bedrock multimodal → reply)

### Key files

| File | Role |
|------|------|
| `src/clean_grocery_bot/lambda_handler.py` | AWS Lambda entry point; orchestrates all modules |
| `src/clean_grocery_bot/models.py` | Pydantic models (all frozen + extra="ignore") |
| `src/clean_grocery_bot/config_loader.py` | Loads/caches `dietary_preference_config.json` |
| `src/clean_grocery_bot/food_search.py` | Open Food Facts API v2/v3 with tenacity retry |
| `src/clean_grocery_bot/pre_filter.py` | Substring-match exclusion of seed oils and additives |
| `src/clean_grocery_bot/ai_ranker.py` | Bedrock Converse API calls; parses JSON from model |
| `src/clean_grocery_bot/security.py` | HMAC webhook verification + SSM chat-ID whitelist |
| `src/clean_grocery_bot/image_utils.py` | Pillow resize + JPEG re-encode for Bedrock limits |
| `dietary_preference_config.json` | User-configurable priorities, market, exclusions |
| `deploy.sh` | Builds `lambda-package.zip` and pushes to Lambda |

### AWS integrations

- **Bedrock**: two models via `client.converse()`; region `us-east-2` — overridable via `BEDROCK_REGION`
  - OCR (photo Call 1): `us.amazon.nova-2-lite-v1:0` — overridable via `BEDROCK_OCR_MODEL_ID`
  - Scoring (photo Call 2 + text ranking): `us.anthropic.claude-sonnet-4-6` — overridable via `BEDROCK_SCORING_MODEL_ID`
- **SSM Parameter Store** paths: `/clean-grocery-bot/telegram-token`, `/clean-grocery-bot/webhook-secret`, `/clean-grocery-bot/allowed-chat-ids`
- Lambda handler is `clean_grocery_bot.lambda_handler.handler`; always returns HTTP 200 to avoid Telegram retries

### Config loading

`config_loader.py` checks `/var/task/dietary_preference_config.json` (Lambda) then repo root, with `GROCERY_BOT_CONFIG` env var as fallback. The config is cached at module level for warm starts.

### Deploy notes

`deploy.sh` auto-detects build machine architecture (`x86_64` vs `arm64`) and sets the Lambda architecture accordingly — native extensions like `pydantic_core` must match. `boto3`/`botocore` are stripped from the zip since Lambda provides them (~50 MB saved). `dietary_preference_config.json` is bundled into the zip at the root of the package.
