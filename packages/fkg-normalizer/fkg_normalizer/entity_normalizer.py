"""
Normalizer — Unicode, alias resolution, unit normalization, and translation.

Why normalization happens BEFORE AI?

Without normalization, the same ingredient appears as:
- "Capsicum" (British English)
- "Bell Pepper" (American English)
- "Shimla Mirch" (Hindi)
- "Paprika" (some European recipes — different meaning!)

The AI would treat these as 4 different ingredients, causing:
1. Duplicate ingredient nodes in the graph
2. Missed relationships ("Dish contains Bell Pepper" but not "Capsicum")
3. Inconsistent nutritional data
4. Broken ingredient substitution chains

By normalizing FIRST, we ensure:
- One canonical name per ingredient
- All aliases mapped to the canonical
- AI receives clean, consistent input
- Graph has no accidental duplicates from normalization issues
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
import json
import re

import ftfy
import structlog

log = structlog.get_logger()

# Load alias dictionaries at module level (loaded once, reused forever)
_ALIAS_DIR = Path(__file__).parent / "dictionaries"


def _load_aliases(filename: str) -> dict[str, str]:
    """Load alias → canonical mapping from JSON file.

    File format: {"alias_lowercase": "Canonical Name", ...}
    """
    path = _ALIAS_DIR / filename
    if not path.exists():
        log.warning("normalizer.alias_file_missing", file=str(path))
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


INGREDIENT_ALIASES: dict[str, str] = _load_aliases("ingredient_aliases.json")
COUNTRY_ALIASES: dict[str, str] = _load_aliases("country_aliases.json")
CUISINE_ALIASES: dict[str, str] = _load_aliases("cuisine_aliases.json")


@dataclass
class NormalizationResult:
    """Result of normalizing a single text field."""

    original: str
    normalized: str
    canonical: str | None = None  # Set if alias was resolved
    alias_resolved: bool = False
    language_detected: str | None = None
    changes_made: list[str] = field(default_factory=list)


class UnicodeNormalizer:
    """Normalize Unicode text to consistent NFC form and fix encoding issues.

    Uses ftfy to fix mojibake and other common encoding problems.
    Uses unicodedata.normalize('NFC') for canonical Unicode composition.

    Example transformations:
    - "Café" (NFD) → "Café" (NFC)
    - "â€œBiryaniâ€" → "\"Biryani\""  (ftfy fixes this)
    - "Paniâ€¦Puri" → "Pani…Puri"
    """

    def normalize(self, text: str) -> NormalizationResult:
        original = text
        changes = []

        # Fix encoding issues (mojibake, broken UTF-8)
        fixed = ftfy.fix_text(text)
        if fixed != text:
            changes.append("ftfy_fix")
            text = fixed

        # Canonical NFC normalization
        nfc = unicodedata.normalize("NFC", text)
        if nfc != text:
            changes.append("unicode_nfc")
            text = nfc

        # Strip leading/trailing whitespace
        stripped = text.strip()
        if stripped != text:
            changes.append("strip_whitespace")
            text = stripped

        # Collapse multiple spaces
        collapsed = re.sub(r"\s+", " ", text)
        if collapsed != text:
            changes.append("collapse_spaces")
            text = collapsed

        return NormalizationResult(
            original=original,
            normalized=text,
            changes_made=changes,
        )


class EntityNormalizer:
    """Resolve entity names to their canonical forms using alias dictionaries.

    Alias resolution is the most important normalization step for data quality.
    Without it, the graph will contain duplicate nodes for the same real-world entity.

    Examples:
        "Capsicum" → "Bell Pepper"      (ingredient alias)
        "Coriander" → "Cilantro"        (regional naming)
        "Curd" → "Yogurt"               (Indian English)
        "Bombay" → "Mumbai"             (historical city name)
        "Burma" → "Myanmar"             (country name change)
    """

    INVALID_DISH_KEYWORDS: set[str] = {
        "popular recipe", "popular recipes", "latest recipes", "featured recipe",
        "recipe compilations", "search recipes", "browse recipes", "truly 100% vegetarian recipes",
        "quick links", "subscribe", "leave a reply", "all recipes", "home", "about",
        "contact us", "privacy policy", "terms of service", "recipes by category",
        "festive sweets", "diwali sweets", "holi recipes", "quick breakfast recipes",
        "popular categories", "top recipes", "recipe index", "side dishes", "main course"
    }

    COLLECTION_HEADER_PATTERNS: list[str] = [
        r"^(festive|diwali|holi|eid|christmas|party|quick|easy|top\s*\d*|best|popular|featured|latest|favorite|seasonal)\s+(sweets|recipes|dishes|snacks|curries|desserts|collections|ideas|menu|items|food|starters)$",
        r"^(sweets|recipes|dishes|curries|desserts|collections|ideas|categories|starters|mains)$",
        r".*\b(compilations?|collection|categories|roundup|menu ideas|recipes index)\b.*",
        r".*truly\s*100%\s*vegetarian.*",
        r".*recipes\s*indian\s*&\s*global.*",
        r".*100%\s*vegetarian.*",
        r".*\b(indian & global|global recipes|all rights reserved|site title|leave a reply|search recipes)\b.*",
    ]

    def normalize_dish_name(self, name: str) -> NormalizationResult | None:
        """Clean dish titles by removing noise, trailing 'Recipe' suffixes, and parentheticals.

        Returns None if the name is a non-food website header/noise.
        """
        clean = name.strip()
        lower = clean.lower()

        # Reject generic web headers
        if lower in self.INVALID_DISH_KEYWORDS or any(kw == lower for kw in self.INVALID_DISH_KEYWORDS):
            return None

        for pattern in self.COLLECTION_HEADER_PATTERNS:
            if re.match(pattern, lower, flags=re.IGNORECASE):
                log.info("normalizer.rejected_collection_header", raw_name=name)
                return None

        changes = []
        original = name

        # 1. Remove parentheticals: "Cold Coffee Recipe (Creamy Café Style)" → "Cold Coffee Recipe"
        no_parens = re.sub(r"\([^)]*\)", "", clean).strip()
        if no_parens != clean and len(no_parens) > 2:
            clean = no_parens
            changes.append("remove_parentheticals")

        # 2. Remove pipe subtitles: "Kadhi Recipe | Punjabi Kadhi Pakora" → "Kadhi Recipe"
        if "|" in clean:
            clean = clean.split("|")[0].strip()
            changes.append("remove_pipe_subtitle")

        # 3. Strip trailing "Recipe" or "Recipes": "Paneer Butter Masala Recipe" → "Paneer Butter Masala"
        stripped_recipe = re.sub(r"\s+recipes?$", "", clean, flags=re.IGNORECASE).strip()
        if stripped_recipe != clean and len(stripped_recipe) > 2:
            clean = stripped_recipe
            changes.append("strip_recipe_suffix")

        if clean.lower() in self.INVALID_DISH_KEYWORDS:
            return None

        return NormalizationResult(original=original, normalized=clean, changes_made=changes)

    def normalize_ingredient(self, name: str) -> NormalizationResult:
        return self._resolve(name, INGREDIENT_ALIASES, "ingredient")

    def normalize_country(self, name: str) -> NormalizationResult:
        return self._resolve(name, COUNTRY_ALIASES, "country")

    def normalize_cuisine(self, name: str) -> NormalizationResult:
        return self._resolve(name, CUISINE_ALIASES, "cuisine")

    def _resolve(self, name: str, alias_map: dict, entity_type: str) -> NormalizationResult:
        """Perform case-insensitive alias lookup."""
        key = name.strip().lower()
        canonical = alias_map.get(key)

        if canonical and canonical != name:
            log.debug(
                "normalizer.alias_resolved",
                entity_type=entity_type,
                original=name,
                canonical=canonical,
            )
            return NormalizationResult(
                original=name,
                normalized=canonical,
                canonical=canonical,
                alias_resolved=True,
                changes_made=["alias_resolution"],
            )

        return NormalizationResult(original=name, normalized=name)


class UnitNormalizer:
    """Normalize measurement units to standard forms.

    Examples:
        "tbsp" → "tablespoon"
        "tsp" → "teaspoon"
        "250 ml" → {"amount": 250, "unit": "ml"}
        "1 cup" → {"amount": 1, "unit": "cup"}
        "2-3 pieces" → {"amount": "2-3", "unit": "piece"}
    """

    UNIT_MAP: dict[str, str] = {
        "tbsp": "tablespoon",
        "tbs": "tablespoon",
        "tablespoons": "tablespoon",
        "tsp": "teaspoon",
        "teaspoons": "teaspoon",
        "c": "cup",
        "cups": "cup",
        "ml": "milliliter",
        "mls": "milliliter",
        "l": "liter",
        "g": "gram",
        "gms": "gram",
        "grams": "gram",
        "kg": "kilogram",
        "kilograms": "kilogram",
        "oz": "ounce",
        "ounces": "ounce",
        "lb": "pound",
        "lbs": "pound",
        "pounds": "pound",
        "pcs": "piece",
        "pieces": "piece",
    }

    def normalize_unit(self, unit: str | None) -> str | None:
        if not unit:
            return unit
        return self.UNIT_MAP.get(unit.strip().lower(), unit.strip().lower())
