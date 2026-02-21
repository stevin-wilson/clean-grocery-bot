# Clean Grocery Bot — Implementation Plan

## Context

The project is a serverless Telegram chatbot that recommends clean grocery products using Open Food Facts data and Claude AI on AWS. The codebase is currently a cookiecutter-poetry scaffold with placeholder code (`foo.py`, `test_foo.py`). The full PRD lives at `.plans/requirements.md` and specifies a `src/` layout with 6 modules, tests, a deployment script, and documentation.

This plan implements the complete bot from the scaffold, incorporating up-to-date API research:

- **Open Food Facts**: taxonomy suggestions API (v3) is verified correct; product search uses v2 API with `countries_tags` (plural) filtering
- **AWS Bedrock**: Claude Haiku 4.5 (`anthropic.claude-haiku-4-5-20251001-v1:0`) via the Converse API (AWS-recommended over InvokeModel)
- **Python**: bumped to 3.12+ to match current Lambda runtimes
- **Pydantic**: used for all data models — provides JSON parsing, validation, and immutability out of the box

---

## Phase 0: Project Restructuring

Migrate from the cookiecutter flat layout to the `src/` layout required by the PRD.

### 0.1 — Restructure directories

- Create `src/clean_grocery_bot/`
- Move `clean_grocery_bot/__init__.py` → `src/clean_grocery_bot/__init__.py`
- Delete `clean_grocery_bot/foo.py` and `tests/test_foo.py` (placeholders)
- Delete empty `clean_grocery_bot/` directory

### 0.2 — Update `pyproject.toml`

- Python: `">=3.12,<4.0"`
- Package layout: `packages = [{include = "clean_grocery_bot", from = "src"}]`
- Add runtime deps: `pydantic = "^2.10"`, `httpx = "^0.28"`, `boto3 = "^1.35"`
- Update dev deps: `pytest = "^8.0"`, `pytest-cov = "^6.0"`, `deptry = "^0.22"`, `pre-commit = "^4.0"`, add `boto3-stubs` (with `bedrock-runtime` + `ssm` extras), `respx = "^0.22"`, `pytest-mock = "^3.14"`
- Update tool paths: pyright `include = ["src/clean_grocery_bot"]`, coverage `source = ["src/clean_grocery_bot"]`, ruff `target-version = "py312"`

### 0.3 — Update CI/tooling configs

- `tox.ini`: envlist → `py312, py313`; gh-actions mapping → `3.12: py312`, `3.13: py313`
- `.github/workflows/main.yml`: matrix → `["3.12", "3.13"]`; codecov → `matrix.python-version == '3.12'`
- `.github/actions/setup-poetry-env/action.yml`: default python → `"3.12"`, Poetry version → `"1.8.5"`
- `.pre-commit-config.yaml`: bump `ruff-pre-commit` to latest (`v0.9.x`), bump `pre-commit-hooks` to `v5.0.0`, bump `mirrors-prettier` to `v4.0.0-alpha.8`. Ruff handles both linting (`ruff check --fix`) and formatting (`ruff format`) — no other formatter needed
- `Makefile`: `deptry .` → `deptry src`
- Delete `Dockerfile` (not a PRD deliverable; deployment is via Lambda zip)

### 0.4 — Copy config to repo root

- Copy `.plans/dietary_preference_config.json` → `dietary_preference_config.json` (repo root)

### 0.5 — Verify

- `poetry lock && poetry install`
- `poetry run ruff check src/` and `poetry run pyright` should pass on empty package

---

## Phase 1: Data Models + Config Loader

### 1.1 — Define data models in `src/clean_grocery_bot/models.py`

Use Pydantic `BaseModel` with `model_config = ConfigDict(frozen=True)` for immutability. Pydantic gives us JSON parsing, validation, and clear error messages for free.

```python
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

class Priority(BaseModel):
    model_config = ConfigDict(frozen=True)
    rank: int
    label: str
    description: str

class CleanlinessCriteria(BaseModel):
    model_config = ConfigDict(frozen=True)
    priorities: list[Priority]

class DietaryRestrictions(BaseModel):
    model_config = ConfigDict(frozen=True)
    exclude_ingredients: list[str] = Field(default_factory=list)

class Market(BaseModel):
    model_config = ConfigDict(frozen=True)
    country: str
    country_name: str

class Recommendations(BaseModel):
    model_config = ConfigDict(frozen=True)
    default_count: int = 3
    max_count: int = 10
    max_prefetch: int = 20

class WholeFoodFallback(BaseModel):
    model_config = ConfigDict(frozen=True)
    enabled: bool = True
    trigger: str = "no_clean_packaged_option"

class ResponseConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    language: str = "English"
    format: str = "medium"

class DietaryConfig(BaseModel):
    """Top-level config model. Parsed directly from dietary_preference_config.json.
    Keys starting with '_' (comments) are ignored via model_config."""
    model_config = ConfigDict(frozen=True, extra="ignore")  # extra="ignore" strips _comment, _instructions, etc.
    cleanliness_criteria: CleanlinessCriteria
    dietary_restrictions: DietaryRestrictions = Field(default_factory=DietaryRestrictions)
    market: Market
    recommendations: Recommendations = Field(default_factory=Recommendations)
    whole_food_fallback: WholeFoodFallback = Field(default_factory=WholeFoodFallback)
    response: ResponseConfig = Field(default_factory=ResponseConfig)

class Product(BaseModel):
    """A product from Open Food Facts."""
    model_config = ConfigDict(frozen=True)
    name: str
    brand: str
    ingredients_text: str
    ingredients_tags: list[str] = Field(default_factory=list)

class RankedProduct(BaseModel):
    """A product scored by Claude."""
    model_config = ConfigDict(frozen=True)
    name: str
    brand: str
    score: int = Field(ge=0, le=100)
    verdict: Literal["Very Clean", "Acceptable", "Avoid"]
    bullets: list[str] = Field(min_length=2, max_length=3)
```

Key Pydantic advantages used here:

- `extra="ignore"` on `DietaryConfig` automatically strips `_comment`, `_instructions`, and `_format_options` keys — no manual stripping needed
- `RankedProduct` validates Claude's JSON output: `score` must be 0-100, `verdict` must be one of three literals, `bullets` must have 2-3 items
- Defaults on optional sections mean a minimal config with just `cleanliness_criteria` and `market` is valid
- `model_validate_json()` parses and validates in one call for config loading

Re-export models from `src/clean_grocery_bot/__init__.py` for clean imports:

```python
from clean_grocery_bot.models import (
    DietaryConfig, Product, RankedProduct, Priority, ...
)
```

### 1.2 — Implement `src/clean_grocery_bot/config_loader.py`

- `load_config(path: str | None = None) -> DietaryConfig`
- Default path: `/var/task/dietary_preference_config.json` (Lambda) with fallback to repo root for local dev
- Uses `DietaryConfig.model_validate_json(file.read())` — Pydantic handles all parsing and validation; invalid configs produce clear `ValidationError` messages
- Module-level cache (`_cached_config`) to avoid re-reading on warm Lambda invocations

### 1.3 — Write `tests/test_config_loader.py` (~7 tests)

Test valid config, missing keys, empty excludes, custom exclusions, file not found, invalid JSON, comment key stripping. Use `tmp_path` fixture for temp config files.

---

## Phase 2: Security Module

### 2.1 — Implement `src/clean_grocery_bot/security.py`

Two functions + module-level caching of SSM values:

- `verify_webhook_secret(event: dict) -> bool` — reads `x-telegram-bot-api-secret-token` header (lowercase, API Gateway normalizes), compares against `/clean-grocery-bot/webhook-secret` in Parameter Store using `hmac.compare_digest` (constant-time comparison to prevent timing attacks)
- `is_chat_allowed(chat_id: int) -> bool` — fetches `/clean-grocery-bot/allowed-chat-ids`, parses comma-separated ints, caches in module-level `set[int]`
- SSM client cached at module level for Lambda warm starts

### 2.2 — Write `tests/test_security.py` (~6 tests)

Mock `boto3.client("ssm")` via `pytest-mock`. Test valid/invalid/missing webhook secret, valid/invalid chat IDs, caching behavior. Reset module-level caches between tests with a fixture.

---

## Phase 3: Food Search Module

### 3.1 — Implement `src/clean_grocery_bot/food_search.py`

Two functions using `httpx`:

- `get_taxonomy_categories(search_term: str) -> list[str]`
  - Endpoint: `GET https://world.openfoodfacts.org/api/v3/taxonomy_suggestions?tagtype=categories&string=<term>`
  - Returns `data["suggestions"]` list
  - Set `User-Agent: CleanGroceryBot/1.0` header (OFF API etiquette)

- `search_products(categories: list[str], country: str, max_results: int = 20) -> list[Product]`
  - Endpoint: `GET https://world.openfoodfacts.net/api/v2/search`
  - Params: `categories_tags_en=<cat>`, `countries_tags=en:<country>`, `fields=product_name,brands,ingredients_text,ingredients_tags`, `page_size=<max>`, `sort_by=popularity_key`
  - Silently excludes products with empty `product_name` or `ingredients_text` (PRD §7.5)
  - Iterates through categories, stops at `max_results`

### 3.2 — Write `tests/test_food_search.py` (~7 tests)

Use `respx` to mock httpx calls. Test successful taxonomy lookup, empty results, HTTP errors, product filtering (missing ingredients/name), max_results limit, multi-category combination.

---

## Phase 4: Pre-Filter Module

### 4.1 — Implement `src/clean_grocery_bot/pre_filter.py`

- Hard-coded `SEED_OILS` frozenset: canola oil, soybean oil, sunflower oil, safflower oil, corn oil, cottonseed oil, grapeseed oil, rapeseed oil, vegetable oil
- Hard-coded `ARTIFICIAL_ADDITIVES` frozenset: BHA, BHT, TBHQ, sodium benzoate, potassium sorbate, Red 40, Yellow 5/6, Blue 1/2, Red 3, Green 3, carrageenan, artificial color/flavor, high fructose corn syrup
- `_build_exclusion_set(config)` merges hard-coded lists with `config.dietary_restrictions.exclude_ingredients`
- `filter_products(products, config) -> list[Product]` — case-insensitive substring match of each exclusion term against `product.ingredients_text`

### 4.2 — Write `tests/test_pre_filter.py` (~8 tests)

Test seed oil removal, additive removal, clean product passes, case insensitivity, user custom exclusions, empty input, all-excluded case, input not mutated.

---

## Phase 5: AI Ranker Module

### 5.1 — Implement `src/clean_grocery_bot/ai_ranker.py`

- Model ID: `anthropic.claude-haiku-4-5-20251001-v1:0`
- Bedrock client cached at module level
- `_build_prompt(products, config) -> str` — builds scoring prompt with:
  - Rubric from `config.cleanliness_criteria.priorities`
  - Deduction guidelines (seed oil: -40, additive: -40, not organic: -20, >10 ingredients: -10 per 5 over)
  - Verdict bands (80-100: Very Clean, 50-79: Acceptable, <50: Avoid)
  - Product list with names, brands, ingredients
  - Instruction to return JSON array only
- `rank_products(products, config) -> list[RankedProduct]` — calls Bedrock Converse API:

  ```python
  client.converse(
      modelId=_MODEL_ID,
      messages=[{"role": "user", "content": [{"text": prompt}]}],
      inferenceConfig={"maxTokens": 2048, "temperature": 0.0},
  )
  ```

  - `temperature=0.0` for deterministic scoring (PRD success criterion)
  - Parses response with Pydantic: `TypeAdapter(list[RankedProduct]).validate_json(output_text)` — validates score range, verdict enum, and bullet count automatically
  - Sorts by score descending

### 5.2 — Write `tests/test_ai_ranker.py` (~6 tests)

Mock `boto3.client("bedrock-runtime")`. Test prompt contains all products/rubric, successful parse+sort, empty input skips Bedrock call, score sorting order, invalid JSON raises `ValidationError`.

---

## Phase 6: Lambda Handler

### 6.1 — Implement `src/clean_grocery_bot/lambda_handler.py`

Main orchestrator following PRD §5.2 (15-step request flow):

- `_parse_user_message(text) -> tuple[str, int | None]` — extracts category + optional count from patterns: `"cereal"`, `"top 5 cereals"`, `"3 yogurts"`
- `_format_response(ranked, search_term, config) -> str` — formats Telegram Markdown with verdicts (✅/⚠️/❌), scores, bullets
- `_send_telegram_message(chat_id, text, bot_token)` — POST to `https://api.telegram.org/bot<token>/sendMessage` with `parse_mode=Markdown`
- `handler(event, context) -> dict` — the full flow:
  1. Verify webhook secret → 403 if invalid
  2. Parse body, extract chat_id + text
  3. Check chat whitelist → silent 200 if unauthorized
  4. Load config
  5. Parse message → search_term + count
  6. Get taxonomy categories → Gate 1 (no match → helpful message, stop)
  7. Search products
  8. Pre-filter → Gate 2 (empty → whole-food fallback or "no clean options", stop)
  9. AI rank → limit to count → format → send
  10. Catch-all exception handler sends "something went wrong" to user
  - Always returns 200 to Telegram (non-200 causes retries)

Bot token cached at module level via SSM.

### 6.2 — Write `tests/test_lambda_handler.py` (~5 tests)

Test the pure functions: `_parse_user_message` (bare term, "top N", "N term", whitespace) and `_format_response` (verify output contains names, scores, verdicts, bullets).

---

## Phase 7: Deployment & Documentation

### 7.1 — Create `deploy.sh`

- `poetry export --without-hashes -o requirements.txt`
- `pip install` to build dir (exclude boto3 — Lambda provides it)
- Copy `src/clean_grocery_bot/` and `dietary_preference_config.json` into build dir
- Zip and `aws lambda update-function-code`
- Configurable via `LAMBDA_FUNCTION_NAME` and `AWS_REGION` env vars

### 7.2 — Update `README.md`

Replace cookiecutter placeholder with: project description, prerequisites, quick start (clone → install → configure → deploy → register webhook), security checklist (PRD §8.10: billing alarm $5, Lambda concurrency 5, API Gateway throttle 10 req/s burst 20, least-privilege IAM, non-obvious bot username, disable discoverability), configuration reference, architecture overview, development commands.

---

## Phase 8: Final Quality Checks

Ruff is the sole linter and formatter for this project (no black, isort, flake8, etc.).

```bash
poetry install
poetry run ruff check src/ tests/         # Lint (flake8-equivalent + isort + pyupgrade + bandit rules)
poetry run ruff format --check src/ tests/ # Format check (black-equivalent)
poetry run pyright                         # Type checking (strict mode)
poetry run pytest tests/ --cov --cov-config=pyproject.toml --cov-report=term-missing
poetry run deptry src                      # Unused/missing dependency check
```

Expected: ~39 tests across 6 test files, all passing. Pyright strict mode clean. Ruff lint + format clean.

---

## Files to Create/Modify

| Action | File                                                         |
| ------ | ------------------------------------------------------------ |
| Modify | `pyproject.toml`                                             |
| Modify | `tox.ini`                                                    |
| Modify | `.github/workflows/main.yml`                                 |
| Modify | `.github/actions/setup-poetry-env/action.yml`                |
| Modify | `.pre-commit-config.yaml`                                    |
| Modify | `Makefile`                                                   |
| Delete | `Dockerfile`                                                 |
| Delete | `clean_grocery_bot/foo.py`                                   |
| Delete | `tests/test_foo.py`                                          |
| Delete | `clean_grocery_bot/` (old directory)                         |
| Create | `src/clean_grocery_bot/__init__.py` (re-exports from models) |
| Create | `src/clean_grocery_bot/models.py` (Pydantic data models)     |
| Create | `src/clean_grocery_bot/config_loader.py`                     |
| Create | `src/clean_grocery_bot/security.py`                          |
| Create | `src/clean_grocery_bot/food_search.py`                       |
| Create | `src/clean_grocery_bot/pre_filter.py`                        |
| Create | `src/clean_grocery_bot/ai_ranker.py`                         |
| Create | `src/clean_grocery_bot/lambda_handler.py`                    |
| Create | `dietary_preference_config.json` (repo root)                 |
| Create | `deploy.sh`                                                  |
| Create | `tests/__init__.py` (if not exists)                          |
| Create | `tests/test_config_loader.py`                                |
| Create | `tests/test_security.py`                                     |
| Create | `tests/test_food_search.py`                                  |
| Create | `tests/test_pre_filter.py`                                   |
| Create | `tests/test_ai_ranker.py`                                    |
| Create | `tests/test_lambda_handler.py`                               |
| Modify | `README.md`                                                  |
