# Clean Grocery Bot — Product Requirements Document

> **Note for Claude Code:** This document is the single source of truth for the project. Implement exactly what is specified here. Key files to produce: `pyproject.toml`, `src/clean_grocery_bot/` package modules, `tests/`, `dietary_preference_config.json`, `deploy.sh`, and `README.md`. Follow the `src/` Poetry layout, security controls in Section 8, and request flow in Section 5.2 precisely.

**Version 1.2 | February 2026**

> A serverless Telegram chatbot that helps you make cleaner food choices while grocery shopping. Search by product category and get AI-powered recommendations ranked by ingredient cleanliness — avoiding seed oils, artificial additives, and ultra-processed foods — based on your own configurable dietary preferences.

---

## 1. Purpose & Goal

Clean Grocery Bot is a family-focused Telegram chatbot that helps adults make healthier, informed food choices while physically shopping in a grocery store. Users type a product category into Telegram and receive curated product recommendations ranked by ingredient cleanliness — powered by Open Food Facts and Claude AI on AWS.

The project is also designed to be openly reproducible: code and setup instructions will be published so others can deploy their own instance.

---

## 2. Users & Context of Use

| Field         | Detail                                            |
| ------------- | ------------------------------------------------- |
| Primary users | Adults in a single family                         |
| Usage context | While physically shopping in a grocery store      |
| Interface     | Telegram chat app (iOS / Android)                 |
| Scale         | Personal / family use only — not a public product |

---

## 3. Functional Requirements

### 3.1 Product Search by Category

The user sends a message with a product category (e.g. "cereal", "crackers", "yogurt"). The bot searches Open Food Facts for matching products and retrieves ingredient data.

### 3.2 Cleanliness Ranking

Claude AI analyzes and ranks products based on the definition of clean ingredients, loaded from `dietary_preference_config.json`. The default ranking criteria, in priority order, are:

1. No artificial additives or preservatives (e.g. BHA, BHT, sodium benzoate, artificial colors)
2. No seed oils (canola, soybean, sunflower, corn oil, etc.)
3. Organic ingredients preferred over conventional
4. Avoid ultra-processed foods — short, recognizable ingredient lists prioritized

### 3.3 Recommendations Response

The bot returns the user's requested number of top recommendations. The user can specify how many they want (e.g. "top 3 cereals"), otherwise the bot uses `default_count` from the config. Each recommendation is presented in medium-detail format:

- Product name and brand
- 2–3 bullet points explaining why it scored well (or any caveats)
- A simple verdict (e.g. ✅ Very Clean / ⚠️ Acceptable / ❌ Avoid)

### 3.5 Whole-Food Fallback

If no sufficiently clean packaged product is found, the bot suggests a simple whole-food alternative with a brief note on why it's the cleaner choice. This behaviour is controlled by the `whole_food_fallback` setting in the config.

### 3.6 Multi-User Household Support

The bot supports multiple users sharing a single cloud deployment. Each user interacts with the bot independently via their own Telegram conversation — Telegram isolates sessions by `chat_id`, so queries from different users do not interfere with each other.

Access is controlled by a whitelist of approved `chat_id` values stored in AWS Parameter Store. Any message from an unrecognised `chat_id` is silently ignored before any processing occurs. To find their `chat_id`, users message `@userinfobot` on Telegram.

### 3.7 Language

English only by default. Configurable via `dietary_preference_config.json`.

---

## 4. Non-Functional Requirements

### 4.1 Cost

The solution must run at near-zero monthly cost. All cloud components should stay within free tiers wherever possible. The only expected recurring cost is Claude API usage (target: under $1/month for family use). A CloudWatch billing alarm is set at $5/month to catch any unexpected cost spikes early.

### 4.2 Security

The deployment must be protected against unauthorised access and cost-driving abuse. Full details in Section 8. Key controls are: chat ID whitelist, Telegram webhook secret token verification, Lambda concurrency limit, API Gateway throttling, least-privilege IAM role, and all secrets stored in Parameter Store.

### 4.3 Stateless

The bot does not store user history or preferences between sessions. Each query is fully self-contained. User preferences are encoded in `dietary_preference_config.json` and applied to every request uniformly.

### 4.4 Response Speed

Responses should arrive within 5–8 seconds. The user is standing in a store aisle — speed matters more than exhaustive results.

### 4.5 Availability

Best-effort availability. As a personal family tool, occasional cold start delays (1–2 seconds from Lambda) or brief downtime are acceptable.

### 4.6 Reproducibility

The codebase and deployment steps must be clear enough for a non-expert to replicate with their own AWS account and Telegram bot token. Secrets must never be hardcoded. Dietary preferences must be fully customizable via `dietary_preference_config.json` without touching any bot logic.

The project uses a `src/` layout compatible with Poetry conventions — the package lives at `src/clean_grocery_bot/` and matches the project name in `pyproject.toml`. This ensures clean imports and correct Lambda packaging. A `tests/` folder is included with unit tests for the config loader, pre-filter, food search, and AI ranker modules — covering the logic most likely to break when the config format changes or new exclusion rules are added.

---

## 5. Technical Architecture

### 5.1 Components

| Component      | Service                                      | Purpose                                                    |
| -------------- | -------------------------------------------- | ---------------------------------------------------------- |
| Chat interface | Telegram Bot (webhook)                       | User-facing interface                                      |
| Compute        | AWS Lambda (Python)                          | Bot logic and orchestration                                |
| API trigger    | AWS API Gateway                              | Receives Telegram webhook POSTs (throttled)                |
| AI / LLM       | AWS Bedrock — Claude Haiku                   | Ingredient analysis and ranking                            |
| Food data      | Open Food Facts API                          | Product and ingredient database (country-filtered)         |
| Secrets        | AWS Parameter Store                          | Telegram token, webhook secret, allowed chat IDs           |
| Dietary config | `dietary_preference_config.json` (repo root) | Dietary preferences, cleanliness criteria, country setting |

### 5.2 Request Flow

1. User sends product category message in Telegram
2. Telegram delivers webhook POST to API Gateway (throttled at 10 req/sec)
3. Lambda wakes — `security.py` immediately verifies the Telegram webhook secret token; invalid requests return HTTP 403 and stop
4. `security.py` checks the sender's `chat_id` against the allowed list in Parameter Store; unrecognised users are silently ignored
5. Lambda loads `dietary_preference_config.json`
6. `food_search.py` calls the Open Food Facts taxonomy suggestions API to map the user's search term to official category labels
7. If no matching taxonomy categories are found, the bot replies with a helpful message (e.g. "I couldn't find that category — try something like 'yogurt', 'crackers', or 'cereal'") and stops. No further processing occurs
8. Lambda queries Open Food Facts for matching products (top 20 candidates) using the taxonomy terms, filtered by configured country
9. Products with missing or incomplete ingredient data are silently excluded
10. Lambda runs a rule-based pre-filter in Python — any product containing a hard-excluded ingredient (seed oils, artificial additives) is discarded before reaching Claude
11. If no products remain after pre-filtering, the bot checks the whole-food fallback setting and responds accordingly without calling Bedrock
12. Remaining candidates + scoring rubric + config criteria sent to Bedrock (Claude Haiku)
13. Claude scores and ranks products, returns structured JSON
14. Lambda parses JSON and formats the Telegram message in Python
15. Lambda sends formatted message back to user via Telegram Bot API

### 5.3 Cost Design Decisions

- Webhook (not polling) eliminates need for an always-on server
- Lambda serverless model — pay only per invocation
- Claude Haiku used instead of Sonnet — ~20x cheaper, sufficient for this task
- Max 20 products fetched from Open Food Facts, pre-filtered in Python before Claude call — Claude only receives genuinely borderline candidates, keeping token usage efficient
- Country filter applied at Open Food Facts query level — reduces irrelevant results and improves product relevance
- No database or caching layer needed given stateless, low-volume usage

---

## 6. Dietary Preference Config

Dietary preferences and cleanliness criteria are stored in `dietary_preference_config.json` at the root of the repository. This file is loaded by Lambda at runtime and injected into the Claude prompt — no code changes are needed to customize the bot's behaviour.

Other users deploying their own instance only need to edit this file to match their own preferences.

### 6.1 File Location

```
clean-grocery-bot/
├── src/
│   └── clean_grocery_bot/             # Python package — matches pyproject.toml project name
│       ├── __init__.py
│       ├── lambda_handler.py          # Entry point — orchestrates all modules
│       ├── security.py                # Webhook token verification + chat ID whitelist
│       ├── food_search.py             # Open Food Facts taxonomy suggestions + product search
│       ├── pre_filter.py              # Rule-based ingredient filter (runs before Claude)
│       ├── ai_ranker.py               # Bedrock prompt, structured JSON output, parsing
│       └── config_loader.py           # Loads and validates dietary_preference_config.json
├── tests/
│   ├── __init__.py
│   ├── test_config_loader.py          # Validates config parsing and schema
│   ├── test_security.py               # Validates whitelist and token verification logic
│   ├── test_pre_filter.py             # Validates ingredient exclusion logic
│   ├── test_food_search.py            # Validates taxonomy suggestions + product query
│   └── test_ai_ranker.py              # Validates Claude prompt output parsing
├── dietary_preference_config.json     # Edit this file to customize preferences
├── pyproject.toml                     # Poetry dependency manifest
├── poetry.lock                        # Locked dependency versions for reproducibility
├── deploy.sh                          # One-command deployment script
└── README.md
```

### 6.2 Example Configuration

The following is the default configuration. It reflects the deploying preferences and serves as a reference for others.

```json
{
  "_comment": "Clean Grocery Bot — Dietary Preference Config",
  "_instructions": "Edit this file to match your preferences. This file is loaded at runtime and passed to the AI prompt. No code changes needed.",

  "cleanliness_criteria": {
    "_comment": "Ordered list of criteria used to rank products. Higher priority items are weighted more heavily. Add, remove, or reorder to match your definition of clean.",
    "priorities": [
      {
        "rank": 1,
        "label": "No artificial additives or preservatives",
        "description": "Exclude products containing artificial preservatives (e.g. BHA, BHT, TBHQ, sodium benzoate) or artificial colors (e.g. Red 40, Yellow 5, Blue 1)"
      },
      {
        "rank": 2,
        "label": "No seed oils",
        "description": "Exclude products containing canola oil, soybean oil, sunflower oil, safflower oil, corn oil, cottonseed oil, or grapeseed oil"
      },
      {
        "rank": 3,
        "label": "Organic preferred",
        "description": "Prefer certified organic products over conventional when available"
      },
      {
        "rank": 4,
        "label": "Avoid ultra-processed foods",
        "description": "Prefer products with short, recognizable ingredient lists. Penalize products with more than 10 ingredients or with many unrecognizable chemical names"
      }
    ]
  },

  "dietary_restrictions": {
    "_comment": "Hard filters — products containing any of these will be excluded entirely. Add items such as 'gluten', 'dairy', 'nuts', 'soy' as needed.",
    "exclude_ingredients": []
  },

  "market": {
    "_comment": "Controls which country's products are returned by Open Food Facts. Use ISO 3166-1 alpha-2 country codes (e.g. 'US', 'GB', 'CA', 'AU', 'FR'). This filters results to products sold in that country, improving relevance.",
    "country": "US",
    "country_name": "United States"
  },

  "recommendations": {
    "_comment": "Default number of recommendations when the user does not specify a quantity. max_prefetch is the number of products fetched from Open Food Facts before pre-filtering — a larger number improves coverage but slightly increases Lambda execution time.",
    "default_count": 3,
    "max_count": 10,
    "max_prefetch": 20
  },

  "whole_food_fallback": {
    "_comment": "When enabled, suggests a whole-food alternative if no clean packaged product is found.",
    "enabled": true,
    "trigger": "no_clean_packaged_option"
  },

  "response": {
    "_comment": "Controls how the bot formats its replies.",
    "language": "English",
    "format": "medium",
    "_format_options": "short (name + one line) | medium (name + 2-3 bullets) | detailed (full ingredient breakdown)"
  }
}
```

### 6.3 Common Customizations

**Changing country** — to show products available in the UK:

```json
"market": { "country": "GB", "country_name": "United Kingdom" }
```

**Adding dietary restrictions** — to exclude dairy and gluten from all results:

```json
"exclude_ingredients": ["dairy", "milk", "gluten", "wheat"]
```

**Changing cleanliness priorities** — to deprioritize organic and focus on additives only, simply remove or reorder items in the `priorities` array.

**Changing response style** — to get a shorter, faster response while shopping:

```json
"format": "short"
```

**Changing default recommendation count:**

```json
"default_count": 5
```

---

## 7. AI Engineering Design

### 7.1 Scoring Rubric

Rather than asking Claude to rank products loosely, the prompt includes an explicit point-based scoring rubric derived from `dietary_preference_config.json`. This produces consistent, explainable results across calls and makes config changes feel meaningful. Default rubric:

| Criterion                                       | Deduction                                   |
| ----------------------------------------------- | ------------------------------------------- |
| Contains a seed oil                             | −40 points                                  |
| Contains an artificial additive or preservative | −40 points                                  |
| Not organic (when organic alternative exists)   | −20 points                                  |
| More than 10 ingredients                        | −10 points per 5 ingredients over threshold |

Every product starts at 100. Final score drives the verdict: 80–100 = ✅ Very Clean, 50–79 = ⚠️ Acceptable, below 50 = ❌ Avoid.

### 7.2 Rule-Based Pre-Filter

Before any call to Claude, a Python pre-filter reads the ingredient list of each candidate and discards any product that contains a hard-excluded item from the config (seed oils, artificial additives). This means Claude only evaluates genuinely borderline products, which improves ranking quality, reduces token usage, and ensures hard exclusions are enforced deterministically — not left to AI judgment.

### 7.3 Structured JSON Output

Claude is instructed to return a JSON array rather than a formatted message. Python then formats the final Telegram message from the parsed data. This gives full control over presentation, makes response style changes trivial, and makes errors immediately detectable.

Expected Claude output format:

```json
[
  {
    "name": "Organic Valley Whole Milk",
    "brand": "Organic Valley",
    "score": 95,
    "verdict": "Very Clean",
    "bullets": [
      "Only 1 ingredient — organic whole milk",
      "Certified organic",
      "No additives or preservatives"
    ]
  }
]
```

### 7.4 Query Enrichment via Open Food Facts Taxonomy

Open Food Facts maintains a full categories taxonomy — a hierarchical vocabulary of all food categories including synonyms, parent terms, and related categories. A dedicated taxonomy suggestions API endpoint accepts a search term and returns matching official category terms from this taxonomy:

```
GET https://world.openfoodfacts.org/api/v3/taxonomy_suggestions?tagtype=categories&string=crackers
```

When a user types a search term, `food_search.py` first calls this endpoint to retrieve matching taxonomy terms, then uses those terms to query the product database. This means searches use the exact category labels the database understands internally, producing significantly better and more consistent results than free-text search alone.

This approach replaces the originally planned static mapping file (`query_expansions.py`) entirely — no hand-crafted synonym lists to maintain, and coverage automatically reflects the latest state of the Open Food Facts taxonomy. The taxonomy suggestions endpoint is subject to a rate limit of 2 requests per minute for facet queries, which is not a concern at personal household usage volumes.

### 7.5 Incomplete Data Handling

Products returned by Open Food Facts with missing or incomplete ingredient lists are silently excluded from results. They are not shown to the user — a product that cannot be evaluated cannot be recommended or flagged reliably, and presenting it could mislead the user into thinking it was assessed when it was not.

### 7.6 Early Exit Gates

To avoid unnecessary downstream costs, the bot exits early at two points in the pipeline before making any Bedrock call:

**Gate 1 — No taxonomy match:** If the Open Food Facts taxonomy suggestions API returns no matching categories for the user's search term, the bot responds immediately with a helpful message and stops. No product search, pre-filtering, or Bedrock call occurs. Example response: "I couldn't find that category — try something like 'yogurt', 'crackers', or 'cereal'."

**Gate 2 — No products after pre-filtering:** If all fetched products are eliminated by the rule-based pre-filter (or excluded due to incomplete ingredient data), the bot checks the `whole_food_fallback` setting. If enabled, it suggests a whole-food alternative directly without calling Bedrock. If disabled, it informs the user that no clean options were found for that category.

These gates ensure Bedrock is only called when there are genuinely evaluable candidates to rank, keeping costs proportional to actual useful work performed.

---

## 8. Security

The deployment is hardened against unauthorised access and cost-driving abuse through multiple layered controls. All security checks run at the very start of the Lambda function before any expensive operations occur.

### 8.1 Chat ID Whitelist

Every incoming Telegram message carries a `chat_id` identifying the sender. Lambda checks this against an allowed list stored in AWS Parameter Store. Messages from unrecognised users are silently ignored — no response is sent, no Bedrock call is made.

To add a new authorised user, update the Parameter Store value — no code changes or redeployment required. Users can find their own `chat_id` by messaging `@userinfobot` on Telegram.

### 8.2 Non-Obvious Bot Username

The Telegram bot must be registered with a non-obvious, randomised username to prevent accidental discovery. A predictable name like `clean_grocery_bot` could be guessed or stumbled upon by strangers. A name like `cgb_xk7r2_bot` is effectively undiscoverable while still being easy to share directly with authorised users.

Additionally, the bot is configured in BotFather with discoverability disabled (not searchable in Telegram) and group joining disabled. These settings reduce exposure, but the chat ID whitelist remains the primary security control — BotFather settings alone cannot prevent a determined user who knows the username from messaging the bot.

### 8.3 Telegram Webhook Secret Token

When registering the webhook with Telegram, a secret token is set. Telegram includes this token in the `X-Telegram-Bot-Api-Secret-Token` header of every request it sends. Lambda verifies this header before any other processing — requests without the correct token return HTTP 403 immediately. This ensures that even if the API Gateway URL is discovered, it cannot be triggered by anything other than genuine Telegram requests.

### 8.4 Lambda Concurrency Limit

A maximum concurrency of 5 is set on the Lambda function. This is a hard ceiling — no matter how many requests arrive simultaneously, at most 5 executions run at once. This caps the maximum possible Bedrock spend even under a sustained attack or accidental loop.

### 8.5 API Gateway Throttling

The API Gateway stage is configured with a rate limit of 10 requests per second and a burst limit of 20. Combined with the Lambda concurrency limit, this makes cost-driving abuse practically impossible.

### 8.6 Least-Privilege IAM Role

The Lambda execution role is granted only the minimum permissions required to operate. Specifically: invoke Bedrock (Claude Haiku only), read from Parameter Store (specific parameter paths only), and write CloudWatch logs. No other AWS services are accessible from the function.

### 8.7 Secrets Management

All secrets are stored in AWS Parameter Store as SecureString (KMS-encrypted at rest). No secrets appear in code, environment variables, or the repository. The three managed secrets are the Telegram bot token, the webhook secret token, and the comma-separated list of allowed chat IDs.

### 8.8 Billing Alarm

A CloudWatch billing alarm is configured at $5/month. An email alert is triggered the moment costs exceed this threshold, providing early warning of any unexpected usage before it becomes a significant expense.

### 8.9 Parameter Store Structure

```
/clean-grocery-bot/telegram-token          # Telegram bot token
/clean-grocery-bot/webhook-secret          # Telegram webhook secret token
/clean-grocery-bot/allowed-chat-ids        # Comma-separated list of authorised chat IDs
```

### 8.10 README Security Checklist

The README includes a one-time security setup checklist covering: setting the billing alarm, configuring the Lambda concurrency limit, setting API Gateway throttling, and creating the least-privilege IAM role. These are all AWS console steps requiring no code changes.

---

## 9. Out of Scope

- Barcode scanning
- User preference memory or session history
- Shopping list management
- Price comparison
- Multi-language support (configurable but not actively supported)
- Mobile app or web interface
- Nutritional goal tracking

---

## 10. Success Criteria

- Family members receive clean product recommendations within 8 seconds of sending a message
- Recommendations consistently avoid seed oils, artificial additives, and ultra-processed products
- Bedrock is never called unless there are valid, pre-filtered products to evaluate — unrecognised queries and fully-filtered result sets exit early at no Bedrock cost
- Hard exclusions (from config) are enforced deterministically by the pre-filter, not by AI judgment
- Claude scoring is consistent — the same product receives the same verdict across multiple calls
- Products with missing or incomplete ingredient data are silently excluded — only fully evaluable products are shown
- Unauthorised Telegram users receive no response and trigger no cloud costs
- The bot username is non-obvious and not discoverable via Telegram search
- Requests without a valid webhook secret token are rejected before any processing occurs
- A sustained spam attack cannot drive monthly costs above $5 due to concurrency and throttling limits
- Monthly AWS + API cost stays under $2 under normal household usage
- Another person can deploy their own instance by following the README in under 30 minutes
- A non-developer can customize their preferences by editing `dietary_preference_config.json` alone
- A non-developer can add a new authorised user by updating a single Parameter Store value
