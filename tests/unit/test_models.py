"""
Unit tests for core Pydantic models.

Validates that our data contracts enforce business rules at the model level
(before the rule engine even runs). Pydantic validators are our first
line of defense.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from fkg_common.models.dish import (
    DietaryInfo,
    DishCategory,
    DishOutput,
    MealType,
    NutritionEstimate,
)


# ── NutritionEstimate ─────────────────────────────────────────────────────────

class TestNutritionEstimate:
    def test_valid_nutrition(self):
        n = NutritionEstimate(
            calories_kcal=450,
            protein_g=25,
            per_serving_g=350,
        )
        assert n.calories_kcal == 450

    def test_negative_calories_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            NutritionEstimate(calories_kcal=-10)
        assert "calories_kcal" in str(exc_info.value)

    def test_protein_exceeding_serving_rejected(self):
        with pytest.raises(ValidationError):
            NutritionEstimate(protein_g=400, per_serving_g=350)

    def test_zero_values_accepted(self):
        n = NutritionEstimate(calories_kcal=0, protein_g=0)
        assert n.calories_kcal == 0

    def test_default_confidence_is_low(self):
        """Nutrition confidence defaults to 0.3 — high uncertainty by design."""
        n = NutritionEstimate()
        assert n.confidence == 0.3


# ── DietaryInfo ───────────────────────────────────────────────────────────────

class TestDietaryInfo:
    def test_vegan_and_vegetarian_consistent(self):
        d = DietaryInfo(is_vegan=True, is_vegetarian=True)
        assert d.is_vegan is True
        assert d.is_vegetarian is True

    def test_vegan_sets_vegetarian_automatically(self):
        """Setting vegan=True should auto-set vegetarian=True."""
        d = DietaryInfo(is_vegan=True)
        assert d.is_vegetarian is True

    def test_vegan_false_not_vegetarian_is_valid(self):
        d = DietaryInfo(is_vegan=False, is_vegetarian=False)
        assert d.is_vegan is False

    def test_vegan_true_not_vegetarian_raises(self):
        with pytest.raises(ValidationError):
            DietaryInfo(is_vegan=True, is_vegetarian=False)


# ── DishOutput (core model) ───────────────────────────────────────────────────

class TestDishOutput:
    def _minimal_dish(self, **overrides) -> dict:
        base = {
            "name": "Test Dish",
            "description": "A test dish with at least 20 characters in description.",
            "category": "traditional",
            "meal_types": ["lunch"],
            "cuisine_hint": "Indian Cuisine",
            "country_hint": "India",
            "confidence": 0.85,
            "reasoning": "This is a test reasoning string that is long enough.",
        }
        base.update(overrides)
        return base

    def test_valid_dish_creates_successfully(self):
        dish = DishOutput(**self._minimal_dish())
        assert dish.name == "Test Dish"

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            DishOutput(**self._minimal_dish(name=""))

    def test_short_description_rejected(self):
        with pytest.raises(ValidationError):
            DishOutput(**self._minimal_dish(description="Too short"))

    def test_confidence_above_1_rejected(self):
        with pytest.raises(ValidationError):
            DishOutput(**self._minimal_dish(confidence=1.5))

    def test_confidence_below_0_rejected(self):
        with pytest.raises(ValidationError):
            DishOutput(**self._minimal_dish(confidence=-0.1))

    def test_meal_types_required_at_least_one(self):
        with pytest.raises(ValidationError):
            DishOutput(**self._minimal_dish(meal_types=[]))

    def test_invalid_meal_type_rejected(self):
        with pytest.raises(ValidationError):
            DishOutput(**self._minimal_dish(meal_types=["midnight_feast"]))

    def test_aliases_default_to_empty_list(self):
        dish = DishOutput(**self._minimal_dish())
        assert dish.aliases == []

    def test_ingredients_default_to_empty_list(self):
        dish = DishOutput(**self._minimal_dish())
        assert dish.ingredients == []

    def test_prep_time_cannot_be_negative(self):
        with pytest.raises(ValidationError):
            DishOutput(**self._minimal_dish(prep_time_min=-1))

    def test_cook_time_max_one_week(self):
        with pytest.raises(ValidationError):
            DishOutput(**self._minimal_dish(cook_time_min=99999))
