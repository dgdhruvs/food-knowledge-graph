"""
Pydantic models for Cuisine Agent (Agent 2) output.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class CuisineType(str, Enum):
    """Classification of a cuisine by its primary character."""

    NATIONAL = "national"
    REGIONAL = "regional"
    HISTORICAL = "historical"
    RELIGIOUS = "religious"
    STREET = "street"
    FUSION = "fusion"
    DIASPORA = "diaspora"


class CuisineOutput(BaseModel):
    """Structured output produced by the Cuisine Agent (Agent 2).

    Identifies the cuisine(s) present in a source page, including
    hierarchical classification and cultural context.
    """

    # ── Primary identification ────────────────────────────────────────────────
    cuisine_name: str = Field(
        ...,
        description="Canonical English cuisine name (e.g. 'Hyderabadi Cuisine')",
        min_length=1,
    )
    native_name: Optional[str] = Field(
        None,
        description="Name in the cuisine's native language/script",
    )
    sub_cuisine: Optional[str] = Field(
        None,
        description="More specific sub-cuisine (e.g. 'Awadhi Cuisine' within 'Indian Cuisine')",
    )
    parent_cuisine: Optional[str] = Field(
        None,
        description="Broader cuisine this belongs to (e.g. 'Indian Cuisine')",
    )

    # ── Classification ────────────────────────────────────────────────────────
    cuisine_type: CuisineType = Field(
        ...,
        description="Primary character of this cuisine",
    )

    # ── Context ───────────────────────────────────────────────────────────────
    historical_context: Optional[str] = Field(
        None,
        description="Historical background relevant to this cuisine's development",
    )
    religious_context: Optional[str] = Field(
        None,
        description="Religious dietary laws or traditions that shape this cuisine",
    )
    street_food_culture: Optional[str] = Field(
        None,
        description="Description of street food culture if present",
    )
    notable_ingredients: list[str] = Field(
        default_factory=list,
        description="Ingredients that are distinctively characteristic of this cuisine",
    )
    notable_techniques: list[str] = Field(
        default_factory=list,
        description="Cooking techniques that are distinctively characteristic of this cuisine",
    )

    # ── Quality ───────────────────────────────────────────────────────────────
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str = Field(..., min_length=10)

    class Config:
        json_schema_extra = {
            "example": {
                "cuisine_name": "Hyderabadi Cuisine",
                "native_name": "حیدرآبادی کھانا",
                "sub_cuisine": "Hyderabadi Muslim Cuisine",
                "parent_cuisine": "Indian Cuisine",
                "cuisine_type": "regional",
                "historical_context": (
                    "Developed under the Nizam of Hyderabad, blending Mughal, "
                    "Persian, and Telugu culinary traditions over 400 years."
                ),
                "religious_context": "Strongly influenced by Halal dietary requirements.",
                "street_food_culture": "Famous for Irani chai cafes and Luqmi snacks.",
                "notable_ingredients": ["saffron", "dried plums", "star anise"],
                "notable_techniques": ["dum cooking", "kachchi method"],
                "confidence": 0.93,
                "reasoning": "Page explicitly discusses Hyderabadi Nizam history and dum cooking.",
            }
        }
