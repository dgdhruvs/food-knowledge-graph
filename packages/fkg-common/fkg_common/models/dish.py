"""
Pydantic models for Dish Discovery Agent (Agent 3) and
Dish Information Agent (Agent 4) output.

These are the most complex models in the system. Every field has
explicit documentation, validation, and an example.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ──────────────────────────────────────────────────────────────────────────────
# Enumerations
# ──────────────────────────────────────────────────────────────────────────────

class MealType(str, Enum):
    BREAKFAST = "breakfast"
    BRUNCH = "brunch"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"
    DESSERT = "dessert"
    BEVERAGE = "beverage"
    STREET_FOOD = "street_food"
    FESTIVAL = "festival"


class DishCategory(str, Enum):
    TRADITIONAL = "traditional"
    STREET_FOOD = "street_food"
    FESTIVAL_FOOD = "festival_food"
    EVERYDAY = "everyday"
    CELEBRATORY = "celebratory"
    HISTORICAL = "historical"
    ROYAL = "royal"
    RELIGIOUS = "religious"


# ──────────────────────────────────────────────────────────────────────────────
# Sub-models
# ──────────────────────────────────────────────────────────────────────────────

class IngredientRef(BaseModel):
    """Reference to an ingredient within a dish, including quantity and notes."""

    name: str = Field(..., min_length=1, description="Canonical ingredient name in English")
    native_name: Optional[str] = Field(None, description="Name in native language/script")
    amount: Optional[str] = Field(None, description="Quantity (e.g. '2', '1/4')")
    unit: Optional[str] = Field(None, description="Measurement unit (e.g. 'cup', 'tsp', 'g')")
    is_optional: bool = Field(False, description="True if ingredient is optional or garnish")
    preparation_note: Optional[str] = Field(
        None,
        description="How the ingredient should be prepared (e.g. 'finely chopped', 'soaked overnight')",
    )


class NutritionEstimate(BaseModel):
    """Estimated nutritional values per serving.

    All values are per the stated serving_size_g.
    The 'confidence' field is critical: nutrition data from recipe sites
    is highly variable and should default to low confidence.
    """

    calories_kcal: Optional[float] = Field(None, ge=0, description="Total calories in kcal")
    protein_g: Optional[float] = Field(None, ge=0, description="Protein in grams")
    carbohydrates_g: Optional[float] = Field(None, ge=0, description="Total carbohydrates in grams")
    fat_g: Optional[float] = Field(None, ge=0, description="Total fat in grams")
    saturated_fat_g: Optional[float] = Field(None, ge=0, description="Saturated fat in grams")
    fiber_g: Optional[float] = Field(None, ge=0, description="Dietary fiber in grams")
    sugar_g: Optional[float] = Field(None, ge=0, description="Total sugar in grams")
    sodium_mg: Optional[float] = Field(None, ge=0, description="Sodium in milligrams")
    per_serving_g: Optional[float] = Field(None, gt=0, description="Serving size this nutrition is based on (grams)")
    confidence: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Confidence in nutrition accuracy. Default low as recipe sites vary widely.",
    )

    @model_validator(mode="after")
    def protein_must_not_exceed_serving(self) -> "NutritionEstimate":
        """Protein cannot physically exceed the total serving weight."""
        if self.protein_g is not None and self.per_serving_g is not None:
            if self.protein_g > self.per_serving_g:
                raise ValueError(
                    f"Protein ({self.protein_g}g) cannot exceed total serving size ({self.per_serving_g}g). "
                    "Rule NUT_002 violation."
                )
        return self


class DietaryInfo(BaseModel):
    """Dietary classification and allergen information for a dish."""

    is_vegetarian: Optional[bool] = Field(None, description="True if dish contains no meat or seafood")
    is_vegan: Optional[bool] = Field(None, description="True if dish contains no animal products")
    is_gluten_free: Optional[bool] = Field(None, description="True if dish contains no gluten")
    contains_dairy: Optional[bool] = Field(None, description="True if dish contains milk, cheese, cream, or ghee")
    contains_egg: Optional[bool] = Field(None, description="True if dish contains eggs")
    contains_meat: Optional[bool] = Field(None, description="True if dish contains red meat or poultry")
    contains_seafood: Optional[bool] = Field(None, description="True if dish contains fish or shellfish")
    allergens: list[str] = Field(
        default_factory=list,
        description="List of common allergens present (e.g. ['gluten', 'nuts', 'dairy'])",
    )
    diet_types: list[str] = Field(
        default_factory=list,
        description="Specific diet types this dish qualifies for (e.g. ['keto', 'halal', 'kosher'])",
    )

    @model_validator(mode="after")
    def vegan_implies_vegetarian(self) -> "DietaryInfo":
        """Logical consistency: a vegan dish must also be vegetarian."""
        if self.is_vegan is True and self.is_vegetarian is False:
            raise ValueError("A vegan dish cannot be non-vegetarian. Rule TAX_003 violation.")
        if self.is_vegan is True:
            self.is_vegetarian = True
        return self


# ──────────────────────────────────────────────────────────────────────────────
# Agent 3 Output — Dish Discovery
# ──────────────────────────────────────────────────────────────────────────────

class DishSummary(BaseModel):
    """A single dish entry discovered by the Dish Discovery Agent (Agent 3).

    This is intentionally lightweight. Detailed extraction is delegated
    to the Dish Information Agent which receives one dish at a time.
    """

    name: str = Field(..., min_length=1, description="English name of the dish")
    native_name: Optional[str] = Field(None, description="Name in native language/script")
    category: DishCategory = Field(..., description="Primary dish category")
    meal_types: list[MealType] = Field(default_factory=list, description="Applicable meal types")
    confidence: float = Field(..., ge=0.0, le=1.0)


class DishListOutput(BaseModel):
    """Complete output of the Dish Discovery Agent (Agent 3).

    Lists all dishes identified in a source page with coarse classification.
    """

    dishes: list[DishSummary] = Field(..., description="All dishes found on this page")
    page_context: str = Field(
        ...,
        description="One-paragraph summary of what this source page is about",
        min_length=20,
    )
    total_found: int = Field(..., ge=0, description="Total number of dishes discovered")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Overall confidence in completeness of discovery")

    @model_validator(mode="after")
    def total_must_match_list(self) -> "DishListOutput":
        if self.total_found != len(self.dishes):
            raise ValueError(
                f"total_found ({self.total_found}) must equal len(dishes) ({len(self.dishes)})"
            )
        return self


# ──────────────────────────────────────────────────────────────────────────────
# Agent 4 Output — Full Dish Information
# ──────────────────────────────────────────────────────────────────────────────

class DishOutput(BaseModel):
    """Complete structured output produced by the Dish Information Agent (Agent 4).

    This is the primary data model of the entire FKG platform.
    Every dish that enters the graph must conform to this schema.

    Design decisions:
    - All fields use Optional with default=None to allow partial extraction.
    - The 'confidence' field drives routing to human review.
    - The 'reasoning' field ensures explainability of every AI decision.
    - The 'missing_fields' list allows targeted re-enrichment later.
    """

    # ── Identity ───────────────────────────────────────────────────────────────
    name: str = Field(..., min_length=1, description="Primary English name of the dish")
    native_name: Optional[str] = Field(None, description="Name in native language/script")
    english_name: Optional[str] = Field(None, description="Standard English translation if different from name")
    aliases: list[str] = Field(
        default_factory=list,
        description="All known regional/local names and alternate spellings",
    )
    description: str = Field(
        ...,
        min_length=20,
        description="Rich, factual description of the dish (min 20 chars)",
    )

    # ── Classification ─────────────────────────────────────────────────────────
    category: DishCategory = Field(..., description="Primary category of this dish")
    meal_types: list[MealType] = Field(
        default_factory=list,
        min_length=1,
        description="Applicable meal types (at least one required)",
    )
    cuisine_hint: str = Field(
        ...,
        description="Cuisine name string; resolved to FK by rule engine (not validated here)",
    )
    country_hint: str = Field(
        ...,
        description="Country name string; resolved to FK by rule engine",
    )

    # ── Culinary Profile ───────────────────────────────────────────────────────
    taste_profile: list[str] = Field(
        default_factory=list,
        description="Flavor descriptors (e.g. ['spicy', 'savory', 'umami', 'tangy'])",
    )
    texture: Optional[str] = Field(None, description="Texture description (e.g. 'crispy outside, soft inside')")
    aroma: Optional[str] = Field(None, description="Aroma description (e.g. 'fragrant with cardamom and rose water')")
    color: Optional[str] = Field(None, description="Visual color description")
    common_accompaniments: list[str] = Field(
        default_factory=list,
        description="Foods or beverages commonly served alongside this dish",
    )

    # ── Ingredients ────────────────────────────────────────────────────────────
    ingredients: list[IngredientRef] = Field(
        default_factory=list,
        description="All ingredients with quantities and preparation notes",
    )

    # ── Cooking ────────────────────────────────────────────────────────────────
    cooking_methods: list[str] = Field(
        default_factory=list,
        description="Cooking techniques used (e.g. ['deep frying', 'steaming', 'dum cooking'])",
    )
    cooking_equipment: list[str] = Field(
        default_factory=list,
        description="Equipment required (e.g. ['tandoor', 'wok', 'clay pot'])",
    )
    prep_time_min: Optional[int] = Field(
        None,
        ge=0,
        le=10080,
        description="Preparation time in minutes (max 1 week for very slow fermented foods)",
    )
    cook_time_min: Optional[int] = Field(
        None,
        ge=0,
        le=10080,
        description="Cooking time in minutes",
    )
    serving_size_g: Optional[float] = Field(None, gt=0, description="Typical serving size in grams")

    # ── Dietary ────────────────────────────────────────────────────────────────
    dietary: DietaryInfo = Field(default_factory=DietaryInfo)

    # ── Nutrition ─────────────────────────────────────────────────────────────
    nutrition: Optional[NutritionEstimate] = Field(
        None,
        description="Estimated nutritional profile per serving. Low confidence by default.",
    )

    # ── Cultural & Historical ─────────────────────────────────────────────────
    history: Optional[str] = Field(None, description="Historical background and cultural significance")
    origin_description: Optional[str] = Field(None, description="Description of geographic and cultural origin")
    interesting_facts: list[str] = Field(
        default_factory=list,
        description="Notable, verifiable facts about this dish",
    )
    festival_association: Optional[str] = Field(
        None,
        description="Festival or occasion this dish is associated with",
    )
    seasonality: list[str] = Field(
        default_factory=list,
        description="Seasons when this dish is traditionally made (e.g. ['winter', 'monsoon'])",
    )
    known_variants: list[str] = Field(
        default_factory=list,
        description="Names of well-known variants or regional versions",
    )

    # ── References ─────────────────────────────────────────────────────────────
    source_urls: list[str] = Field(
        default_factory=list,
        description="Source URLs from which this information was extracted",
    )

    # ── Quality Metadata ───────────────────────────────────────────────────────
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "Agent's overall confidence in the accuracy of this extraction. "
            "Values below 0.72 automatically trigger human review."
        ),
    )
    reasoning: str = Field(
        ...,
        min_length=20,
        description=(
            "Explanation of why key fields were assigned. "
            "Required for explainability and auditability."
        ),
    )
    missing_fields: list[str] = Field(
        default_factory=list,
        description="Field names that could not be extracted from the source",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Biryani",
                "native_name": "بریانی",
                "english_name": "Biryani",
                "aliases": ["Biriyani", "Beriani", "Birani"],
                "description": (
                    "Biryani is a fragrant mixed rice dish cooked with aromatic spices, "
                    "basmati rice, and meat or vegetables, originating from the Indian subcontinent."
                ),
                "category": "traditional",
                "meal_types": ["lunch", "dinner"],
                "cuisine_hint": "Hyderabadi Cuisine",
                "country_hint": "India",
                "taste_profile": ["spicy", "savory", "aromatic", "rich"],
                "texture": "long-grain fluffy rice with tender, juicy meat",
                "aroma": "saffron, fried onions, whole spices, rose water",
                "color": "golden-yellow with caramelized onions",
                "common_accompaniments": ["raita", "mirchi ka salan", "boiled egg"],
                "ingredients": [
                    {
                        "name": "Basmati rice",
                        "amount": "2",
                        "unit": "cups",
                        "is_optional": False,
                        "preparation_note": "soaked for 30 minutes",
                    },
                    {
                        "name": "Saffron",
                        "amount": "1",
                        "unit": "pinch",
                        "is_optional": True,
                        "preparation_note": "dissolved in warm milk",
                    },
                ],
                "cooking_methods": ["dum cooking", "sautéing", "layering"],
                "cooking_equipment": ["heavy-bottomed pot", "tawa", "flat dough seal"],
                "prep_time_min": 60,
                "cook_time_min": 45,
                "serving_size_g": 350,
                "dietary": {
                    "is_vegetarian": False,
                    "is_vegan": False,
                    "contains_meat": True,
                    "contains_dairy": True,
                    "allergens": ["dairy"],
                    "diet_types": ["halal"],
                },
                "nutrition": {
                    "calories_kcal": 450,
                    "protein_g": 25,
                    "carbohydrates_g": 55,
                    "fat_g": 12,
                    "per_serving_g": 350,
                    "confidence": 0.55,
                },
                "history": "Biryani's history dates to the Mughal Empire...",
                "known_variants": ["Hyderabadi Biryani", "Lucknowi Biryani", "Kolkata Biryani"],
                "confidence": 0.92,
                "reasoning": "Wikipedia article with Schema.org Recipe markup confirmed by two additional sources.",
                "missing_fields": ["aroma", "seasonality"],
            }
        }
