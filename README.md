# clean-grocery-bot

[![Build status](https://img.shields.io/github/actions/workflow/status/stevin-wilson/clean-grocery-bot/main.yml?branch=main)](https://github.com/stevin-wilson/clean-grocery-bot/actions/workflows/main.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/stevin-wilson/clean-grocery-bot/branch/main/graph/badge.svg)](https://codecov.io/gh/stevin-wilson/clean-grocery-bot)
[![License](https://img.shields.io/github/license/stevin-wilson/clean-grocery-bot)](https://img.shields.io/github/license/stevin-wilson/clean-grocery-bot)

A serverless Telegram chatbot that recommends clean grocery products. Tell it a category — "yogurt", "top 5 crackers", "3 cereals" — and it searches Open Food Facts, filters out seed oils and artificial additives, then asks Claude AI to rank the survivors by ingredient cleanliness according to your own configurable priorities.

---

## How it works

```text
User → Telegram → API Gateway → Lambda
                                  │
                         ┌────────▼────────┐
                         │  security.py    │  verify webhook secret + chat whitelist
                         └────────┬────────┘
                         ┌────────▼────────┐
                         │  food_search.py │  Open Food Facts taxonomy + product search
                         └────────┬────────┘
                         ┌────────▼────────┐
                         │  pre_filter.py  │  remove seed oils, additives, user exclusions
                         └────────┬────────┘
                         ┌────────▼────────┐
                         │  ai_ranker.py   │  Claude Haiku 4.5 on AWS Bedrock scores + ranks
                         └────────┬────────┘
                                  │
                         format → send back to Telegram
```

**Cost controls:** webhook (not polling) · serverless Lambda · Claude Haiku (cheapest model) · hard pre-filter before AI call · 20-product cap · no database

---

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (package manager)
- AWS account with access to:
  - Lambda
  - API Gateway
  - AWS Bedrock (Claude Haiku 4.5 enabled in your region)
  - Systems Manager Parameter Store
  - CloudWatch
- Telegram bot token (create via [@BotFather](https://t.me/botfather))

---

## Quick start

### 1. Clone and install

```bash
git clone https://github.com/stevin-wilson/clean-grocery-bot.git
cd clean-grocery-bot
uv sync --all-groups
```

### 2. Configure your preferences

Edit `dietary_preference_config.json` at the repo root:

```jsonc
{
  "market": { "country": "US", "country_name": "United States" },
  "dietary_restrictions": {
    "exclude_ingredients": [], // add e.g. "gluten", "dairy", "nuts"
  },
  "recommendations": {
    "default_count": 3, // returned when user doesn't specify
    "max_count": 10,
    "max_prefetch": 20, // fetched from OFF before filtering
  },
  // ...see file for full schema
}
```

### 3. Create AWS Parameter Store secrets

```bash
# Telegram bot token (from BotFather)
aws ssm put-parameter \
    --name "/clean-grocery-bot/telegram-token" \
    --value "YOUR_BOT_TOKEN" \
    --type SecureString

# Random string used to authenticate Telegram webhooks (generate with: openssl rand -hex 32)
aws ssm put-parameter \
    --name "/clean-grocery-bot/webhook-secret" \
    --value "YOUR_WEBHOOK_SECRET" \
    --type SecureString

# Comma-separated list of Telegram chat IDs allowed to use the bot
aws ssm put-parameter \
    --name "/clean-grocery-bot/allowed-chat-ids" \
    --value "123456789" \
    --type SecureString
```

### 4. Create the Lambda function

1. Create a Lambda function named `clean-grocery-bot` with **Python 3.12** runtime
2. Attach an IAM role with these permissions:
   - `bedrock:InvokeModel` on `arn:aws:bedrock:*::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0`
   - `ssm:GetParameter` on `/clean-grocery-bot/*`
   - `logs:CreateLogGroup`, `logs:CreateLogStream`, `logs:PutLogEvents`
3. Set **Handler** to `clean_grocery_bot.lambda_handler.handler`
4. Set **Reserved concurrency** to **5** (cost guard)
5. Set **Timeout** to **30 seconds**

### 5. Create the API Gateway endpoint

1. Create an **HTTP API** with a POST route (e.g. `POST /webhook`)
2. Integrate with the Lambda function
3. Enable **throttling**: 10 requests/sec, burst 20
4. Note the invoke URL

### 6. Deploy

```bash
export LAMBDA_FUNCTION_NAME=clean-grocery-bot
export AWS_REGION=us-east-1
bash deploy.sh
```

### 7. Register the Telegram webhook

```bash
curl -X POST "https://api.telegram.org/botYOUR_BOT_TOKEN/setWebhook" \
    -H "Content-Type: application/json" \
    -d '{
        "url": "https://YOUR_API_GATEWAY_URL/webhook",
        "secret_token": "YOUR_WEBHOOK_SECRET"
    }'
```

---

## Security checklist

After deployment, verify all of the following:

- [ ] **Billing alarm** — set a CloudWatch billing alarm at $5/month
- [ ] **Lambda concurrency** — reserved concurrency set to 5
- [ ] **API Gateway throttling** — 10 req/sec rate, 20 burst
- [ ] **IAM least privilege** — Lambda role scoped to only the resources above
- [ ] **Bot username** — use a non-obvious username in BotFather (avoid `*bot*` suffix)
- [ ] **Bot discoverability** — disable via BotFather (`/setprivacy`, `Allow Groups: disabled`)
- [ ] **Secrets in Parameter Store** — never commit tokens to the repo

---

## Configuration reference

| Section                           | Key                            | Description                                                     |
| --------------------------------- | ------------------------------ | --------------------------------------------------------------- |
| `cleanliness_criteria.priorities` | `rank`, `label`, `description` | Ordered scoring rubric passed to Claude                         |
| `dietary_restrictions`            | `exclude_ingredients`          | Hard-excluded ingredient substrings (pre-filter, before Claude) |
| `market`                          | `country`                      | ISO 3166-1 alpha-2 code for Open Food Facts country filter      |
| `recommendations`                 | `default_count`                | Products returned when user omits a count                       |
| `recommendations`                 | `max_count`                    | Upper bound on user-requested count                             |
| `recommendations`                 | `max_prefetch`                 | Products fetched from OFF before filtering                      |
| `whole_food_fallback`             | `enabled`                      | Suggest whole-food alternative when nothing passes the filter   |
| `response`                        | `language`                     | Response language (e.g. `"English"`, `"French"`)                |
| `response`                        | `format`                       | `"short"` · `"medium"` · `"detailed"`                           |

---

## Development

```bash
# Install all dependencies
uv sync --all-groups

# Run tests with coverage
uv run pytest --cov --cov-config=pyproject.toml --cov-report=term-missing

# Lint + format check
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/

# All quality checks (pre-commit + pyright + deptry)
make check
```

---

## Supported query formats

| User message     | Behaviour                                  |
| ---------------- | ------------------------------------------ |
| `yogurt`         | Returns `default_count` results for yogurt |
| `top 5 crackers` | Returns up to 5 results for crackers       |
| `3 cereals`      | Returns up to 3 results for cereals        |
