"""
Unit tests for the Rule Engine.

These tests are the first line of defense against data quality regressions.
Every rule must have at least one positive (passes) and one negative (violates) test.

Design note: Tests are written before implementation (TDD) and serve as
executable documentation of the rule set.
"""
from __future__ import annotations

import pytest
from fkg_rules.rule_engine import RuleEngine, RuleSeverity


@pytest.fixture
def engine() -> RuleEngine:
    """Rule engine with critical (hardcoded) rules only — no YAML needed."""
    return RuleEngine()


@pytest.fixture
def valid_dish() -> dict:
    """A minimal valid dish dict that passes all critical rules."""
    return {
        "name": "Biryani",
        "description": "A fragrant mixed rice dish with spices and meat.",
        "cuisine_hint": "Indian Cuisine",
        "country_hint": "India",
        "meal_types": ["lunch", "dinner"],
        "category": "traditional",
        "confidence": 0.92,
        "dietary": {
            "is_vegetarian": False,
            "is_vegan": False,
        },
        "nutrition": {
            "calories_kcal": 450,
            "protein_g": 25,
            "carbohydrates_g": 55,
            "fat_g": 12,
            "per_serving_g": 350,
        },
    }


# ── NUT_001: Calories cannot be negative ──────────────────────────────────────

class TestCaloriesNonNegative:
    def test_passes_with_zero_calories(self, engine, valid_dish):
        valid_dish["nutrition"]["calories_kcal"] = 0
        result = engine.validate_dish(valid_dish)
        assert not result.has_error("NUT_001")

    def test_passes_with_positive_calories(self, engine, valid_dish):
        valid_dish["nutrition"]["calories_kcal"] = 500
        result = engine.validate_dish(valid_dish)
        assert not result.has_error("NUT_001")

    def test_fails_with_negative_calories(self, engine, valid_dish):
        valid_dish["nutrition"]["calories_kcal"] = -10
        result = engine.validate_dish(valid_dish)
        assert result.has_error("NUT_001")
        assert not result.passed

    def test_violation_has_correct_severity(self, engine, valid_dish):
        valid_dish["nutrition"]["calories_kcal"] = -1
        result = engine.validate_dish(valid_dish)
        error = next(v for v in result.errors if v.rule_id == "NUT_001")
        assert error.severity == RuleSeverity.ERROR


# ── NUT_002: Protein cannot exceed serving size ───────────────────────────────

class TestProteinWeightBound:
    def test_passes_when_protein_less_than_serving(self, engine, valid_dish):
        valid_dish["nutrition"]["protein_g"] = 25
        valid_dish["nutrition"]["per_serving_g"] = 350
        result = engine.validate_dish(valid_dish)
        assert not result.has_error("NUT_002")

    def test_passes_when_protein_equals_serving(self, engine, valid_dish):
        valid_dish["nutrition"]["protein_g"] = 100
        valid_dish["nutrition"]["per_serving_g"] = 100
        result = engine.validate_dish(valid_dish)
        assert not result.has_error("NUT_002")

    def test_fails_when_protein_exceeds_serving(self, engine, valid_dish):
        valid_dish["nutrition"]["protein_g"] = 400  # More than 350g serving!
        valid_dish["nutrition"]["per_serving_g"] = 350
        result = engine.validate_dish(valid_dish)
        assert result.has_error("NUT_002")


# ── COMP_001: Dish name is required ──────────────────────────────────────────

class TestDishNameRequired:
    def test_passes_with_valid_name(self, engine, valid_dish):
        result = engine.validate_dish(valid_dish)
        assert not result.has_error("COMP_001")

    def test_fails_with_empty_name(self, engine, valid_dish):
        valid_dish["name"] = ""
        result = engine.validate_dish(valid_dish)
        assert result.has_error("COMP_001")

    def test_fails_with_missing_name(self, engine, valid_dish):
        del valid_dish["name"]
        result = engine.validate_dish(valid_dish)
        assert result.has_error("COMP_001")

    def test_fails_with_none_name(self, engine, valid_dish):
        valid_dish["name"] = None
        result = engine.validate_dish(valid_dish)
        assert result.has_error("COMP_001")


# ── COMP_002: Cuisine is required ─────────────────────────────────────────────

class TestCuisineRequired:
    def test_fails_with_missing_cuisine(self, engine, valid_dish):
        del valid_dish["cuisine_hint"]
        result = engine.validate_dish(valid_dish)
        assert result.has_error("COMP_002")

    def test_fails_with_empty_cuisine(self, engine, valid_dish):
        valid_dish["cuisine_hint"] = ""
        result = engine.validate_dish(valid_dish)
        assert result.has_error("COMP_002")


# ── TAX_001: Meal type is required ────────────────────────────────────────────

class TestMealTypeRequired:
    def test_fails_with_empty_meal_types(self, engine, valid_dish):
        valid_dish["meal_types"] = []
        result = engine.validate_dish(valid_dish)
        assert result.has_error("TAX_001")

    def test_passes_with_one_meal_type(self, engine, valid_dish):
        valid_dish["meal_types"] = ["dinner"]
        result = engine.validate_dish(valid_dish)
        assert not result.has_error("TAX_001")


# ── TAX_002: Valid meal types ─────────────────────────────────────────────────

class TestValidMealTypes:
    def test_fails_with_invalid_meal_type(self, engine, valid_dish):
        valid_dish["meal_types"] = ["brunch", "midnight_snack"]  # midnight_snack is invalid
        result = engine.validate_dish(valid_dish)
        assert result.has_error("TAX_002")

    def test_passes_with_all_valid_meal_types(self, engine, valid_dish):
        valid_dish["meal_types"] = ["breakfast", "lunch", "dinner", "snack", "dessert"]
        result = engine.validate_dish(valid_dish)
        assert not result.has_error("TAX_002")


# ── TAX_003: Vegan implies vegetarian ─────────────────────────────────────────

class TestVeganImpliesVegetarian:
    def test_fails_when_vegan_but_not_vegetarian(self, engine, valid_dish):
        valid_dish["dietary"]["is_vegan"] = True
        valid_dish["dietary"]["is_vegetarian"] = False
        result = engine.validate_dish(valid_dish)
        assert result.has_error("TAX_003")

    def test_passes_when_vegan_and_vegetarian(self, engine, valid_dish):
        valid_dish["dietary"]["is_vegan"] = True
        valid_dish["dietary"]["is_vegetarian"] = True
        result = engine.validate_dish(valid_dish)
        assert not result.has_error("TAX_003")

    def test_passes_when_not_vegan(self, engine, valid_dish):
        valid_dish["dietary"]["is_vegan"] = False
        valid_dish["dietary"]["is_vegetarian"] = False
        result = engine.validate_dish(valid_dish)
        assert not result.has_error("TAX_003")


# ── CONF_001: Confidence score valid ─────────────────────────────────────────

class TestConfidenceValid:
    def test_fails_with_none_confidence(self, engine, valid_dish):
        valid_dish["confidence"] = None
        result = engine.validate_dish(valid_dish)
        assert result.has_error("CONF_001")

    def test_fails_with_confidence_above_1(self, engine, valid_dish):
        valid_dish["confidence"] = 1.5
        result = engine.validate_dish(valid_dish)
        assert result.has_error("CONF_001")

    def test_passes_with_boundary_values(self, engine, valid_dish):
        for val in [0.0, 0.5, 1.0]:
            valid_dish["confidence"] = val
            result = engine.validate_dish(valid_dish)
            assert not result.has_error("CONF_001"), f"Failed for confidence={val}"


# ── Integration: a fully valid dish has no errors ─────────────────────────────

class TestFullyValidDish:
    def test_valid_dish_passes_all_critical_rules(self, engine, valid_dish):
        result = engine.validate_dish(valid_dish)
        assert result.passed
        assert len(result.errors) == 0
