"""Pydantic data models shared across all modules."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _BaseModel(BaseModel):
    """Base for all models: frozen (immutable) and ignores unknown keys (e.g. _comment fields in JSON)."""

    model_config = ConfigDict(frozen=True, extra="ignore")


class Priority(_BaseModel):
    rank: int
    label: str
    description: str


class CleanlinessCriteria(_BaseModel):
    priorities: list[Priority]


class DietaryRestrictions(_BaseModel):
    exclude_ingredients: list[str] = Field(default_factory=list)


class Market(_BaseModel):
    country: str
    country_name: str


class Recommendations(_BaseModel):
    default_count: int = 3
    max_count: int = 10
    max_prefetch: int = 20


class WholeFoodFallback(_BaseModel):
    enabled: bool = True
    trigger: str = "no_clean_packaged_option"


class ResponseConfig(_BaseModel):
    language: str = "English"
    format: str = "medium"


class HouseholdConfig(_BaseModel):
    members: list[str] = Field(default_factory=list)


class IngredientHarm(_BaseModel):
    ingredient: str
    evidence: str  # plain health-claim, e.g. "increases risk of high blood pressure"


class DietaryConfig(_BaseModel):
    """Top-level config parsed from dietary_preference_config.json."""

    cleanliness_criteria: CleanlinessCriteria
    dietary_restrictions: DietaryRestrictions = Field(default_factory=DietaryRestrictions)
    market: Market
    recommendations: Recommendations = Field(default_factory=Recommendations)
    whole_food_fallback: WholeFoodFallback = Field(default_factory=WholeFoodFallback)
    response: ResponseConfig = Field(default_factory=ResponseConfig)
    household: HouseholdConfig = Field(default_factory=HouseholdConfig)


class Product(_BaseModel):
    """A product returned from the Open Food Facts API."""

    name: str
    brand: str
    ingredients_text: str
    ingredients_tags: list[str] = Field(default_factory=list)


class RankedProduct(_BaseModel):
    """A product scored and explained by Claude."""

    name: str
    brand: str
    score: int = Field(ge=0, le=100)
    verdict: Literal["Very Clean", "Acceptable", "Avoid"]
    bullets: list[str] = Field(min_length=1, max_length=7)
    harms: list[IngredientHarm] = Field(default_factory=lambda: [])


class LabelAnalysis(_BaseModel):
    """Result of analyzing an ingredient label photo."""

    product_name: str = "Unknown"
    ingredients_text: str
    score: int = Field(ge=0, le=100)
    verdict: Literal["Very Clean", "Acceptable", "Avoid"]
    bullets: list[str] = Field(min_length=1, max_length=7)
    harms: list[IngredientHarm] = Field(default_factory=lambda: [])
    flags: list[str] = Field(default_factory=list)
