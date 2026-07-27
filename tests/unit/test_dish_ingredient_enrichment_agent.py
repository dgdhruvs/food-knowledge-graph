"""
Unit tests for DishIngredientEnrichmentAgent (Agent 7).
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from fkg_agents.dish_ingredient_enrichment_agent import DishIngredientEnrichmentAgent
from fkg_common.models.dish import DishIngredientEnrichmentOutput


@pytest.fixture
def agent() -> DishIngredientEnrichmentAgent:
    return DishIngredientEnrichmentAgent(model_name="THUDM/GLM-Z1-9B-0414")


class TestDishIngredientEnrichmentAgent:
    def test_agent_type(self, agent):
        assert agent.agent_type == "dish_ingredient_enrichment"

    def test_search_recipe_online_fallback(self, agent):
        snippet, url = agent.search_recipe_online("Kulfi", "Indian Cuisine")
        assert "Kulfi" in snippet
        assert "google.com" in url or "wikipedia.org" in url

    def test_parse_valid_llm_json(self, agent):
        raw_json = """
        {
          "dish_name": "Kulfi",
          "is_found": true,
          "ingredients": ["milk", "sugar", "cardamom", "saffron", "pistachio"],
          "recipe_summary": "Frozen Indian dairy dessert.",
          "confidence": 0.95,
          "source_url": "https://en.wikipedia.org/wiki/Kulfi",
          "reasoning": "Extracted key ingredients from recipe snippet."
        }
        """
        parsed = agent.parse_output(raw_json)
        assert isinstance(parsed, DishIngredientEnrichmentOutput)
        assert parsed.dish_name == "Kulfi"
        assert "milk" in parsed.ingredients
        assert "saffron" in parsed.ingredients

    def test_enrich_dish_fallback_kulfi(self, agent):
        with patch.object(DishIngredientEnrichmentAgent, "run") as mock_run:
            mock_run.side_effect = RuntimeError("LLM offline")
            res = agent.enrich_dish("Kulfi", description="sweet frozen milk dessert with cardamom", cuisine_hint="Indian Cuisine")
            assert isinstance(res, DishIngredientEnrichmentOutput)
            assert res.is_found is True
            assert "milk" in res.ingredients
            assert "cardamom" in res.ingredients

    def test_enrich_dish_fallback_imarti(self, agent):
        with patch.object(DishIngredientEnrichmentAgent, "run") as mock_run:
            mock_run.side_effect = RuntimeError("LLM offline")
            res = agent.enrich_dish("Imarti", description="sweet made of moong dal batter dipped in sugary syrup", cuisine_hint="Indian Cuisine")
            assert isinstance(res, DishIngredientEnrichmentOutput)
            assert "moong dal" in res.ingredients or "sugar" in res.ingredients
