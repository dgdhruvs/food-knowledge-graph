"""
Unit tests for DishDiscoveryAgent.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch

from fkg_agents.dish_discovery_agent import DishDiscoveryAgent, DishDiscoveryOutput
from fkg_common.models.parsed_page import ParsedPage


@pytest.fixture
def agent() -> DishDiscoveryAgent:
    return DishDiscoveryAgent(model_name="THUDM/GLM-Z1-9B-0414")


@pytest.fixture
def sample_page() -> ParsedPage:
    return ParsedPage(
        url="https://www.vegrecipesofindia.com/",
        title="Veg Recipes of India",
        main_text="Festive Sweets and Paneer Butter Masala recipe.",
        language="en",
    )


class TestDishDiscoveryAgent:
    def test_agent_type(self, agent):
        assert agent.agent_type == "dish_discovery"

    def test_rejects_festive_sweets_deterministic(self, agent, sample_page):
        res = agent.validate_candidate(sample_page, "Festive Sweets")
        assert isinstance(res, DishDiscoveryOutput)
        assert res.is_valid_dish is False
        assert "Rejected as generic" in res.reasoning

    def test_rejects_diwali_sweets(self, agent, sample_page):
        res = agent.validate_candidate(sample_page, "Diwali Sweets")
        assert res.is_valid_dish is False

    def test_accepts_paneer_butter_masala_fallback(self, agent, sample_page):
        with patch.object(DishDiscoveryAgent, "run") as mock_run:
            mock_run.side_effect = RuntimeError("LLM offline")
            res = agent.validate_candidate(sample_page, "Paneer Butter Masala Recipe")
            assert isinstance(res, DishDiscoveryOutput)
            assert res.is_valid_dish is True
            assert res.canonical_name == "Paneer Butter Masala"

    def test_parse_valid_llm_json(self, agent):
        mock_json = """
        {
          "candidate_name": "Festive Sweets",
          "is_valid_dish": false,
          "canonical_name": "Festive Sweets",
          "category": "noise",
          "confidence": 0.99,
          "reasoning": "Festive Sweets is a generic recipe collection section header, not a specific culinary dish entity."
        }
        """
        parsed = agent.parse_output(mock_json)
        assert isinstance(parsed, DishDiscoveryOutput)
        assert parsed.is_valid_dish is False
