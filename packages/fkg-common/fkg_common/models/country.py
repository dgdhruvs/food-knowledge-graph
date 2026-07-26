"""
Pydantic models for Country Agent (Agent 1) output.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class CountryOutput(BaseModel):
    """Structured output produced by the Country Agent (Agent 1).

    This is the canonical contract between the Country Agent and the
    downstream pipeline. Every field must be present or explicitly None.
    """

    # ── Core identification ──────────────────────────────────────────────────
    country_name: str = Field(
        ...,
        description="Canonical English country name (e.g. 'India', 'France')",
        min_length=1,
    )
    country_iso_alpha2: Optional[str] = Field(
        None,
        description="ISO 3166-1 alpha-2 code (e.g. 'IN', 'FR')",
        pattern=r"^[A-Z]{2}$",
    )
    country_iso_alpha3: Optional[str] = Field(
        None,
        description="ISO 3166-1 alpha-3 code (e.g. 'IND', 'FRA')",
        pattern=r"^[A-Z]{3}$",
    )

    # ── Geographic hierarchy ─────────────────────────────────────────────────
    region: Optional[str] = Field(
        None,
        description="UN macro-region (e.g. 'Asia', 'Europe', 'Africa')",
    )
    sub_region: Optional[str] = Field(
        None,
        description="UN sub-region (e.g. 'Southern Asia', 'Western Europe')",
    )
    state_province: Optional[str] = Field(
        None,
        description="State or province if the content is region-specific",
    )
    cultural_region: Optional[str] = Field(
        None,
        description=(
            "Named cultural/historical region that may cross national boundaries "
            "(e.g. 'Levant', 'Maghreb', 'Bengal')"
        ),
    )

    # ── Quality ──────────────────────────────────────────────────────────────
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Agent's self-assessed confidence in this identification",
    )
    reasoning: str = Field(
        ...,
        description="Concise explanation of why this country was identified",
        min_length=10,
    )
    source_hints: list[str] = Field(
        default_factory=list,
        description="Textual clues from the source that led to this identification",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "country_name": "India",
                "country_iso_alpha2": "IN",
                "country_iso_alpha3": "IND",
                "region": "Asia",
                "sub_region": "Southern Asia",
                "state_province": "Telangana",
                "cultural_region": "Deccan",
                "confidence": 0.97,
                "reasoning": (
                    "Page title and URL both contain 'hyderabadi' which is "
                    "unambiguously in Telangana, India. Language is English with "
                    "many Urdu loanwords consistent with Hyderabadi cuisine."
                ),
                "source_hints": [
                    "hyderabadi biryani",
                    "Telangana state",
                    "Indian subcontinent",
                ],
            }
        }
