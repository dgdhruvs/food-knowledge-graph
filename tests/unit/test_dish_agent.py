"""
Unit tests for DishInformationAgent.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from fkg_agents.dish_information_agent import DishInformationAgent
from fkg_common.models.dish import DishOutput
from fkg_common.models.parsed_page import ParsedPage


@pytest.fixture
def agent() -> DishInformationAgent:
    return DishInformationAgent(model_name="THUDM/GLM-Z1-9B-0414")


@pytest.fixture
def sample_page() -> ParsedPage:
    return ParsedPage(
        url="https://en.wikipedia.org/wiki/Biryani",
        title="Biryani - Wikipedia",
        main_text="Biryani is a mixed rice dish originated among the Muslims of the Indian subcontinent.",
        language="en",
    )


class TestDishInformationAgent:
    def test_agent_type(self, agent):
        assert agent.agent_type == "dish_information"

    def test_build_prompt(self, agent, sample_page):
        prompt = agent.build_prompt(
            sample_page,
            context={
                "dish_name": "Biryani",
                "country_context": "India",
                "cuisine_context": "Indian Cuisine",
            },
        )
        assert "Biryani" in prompt
        assert "India" in prompt
        assert "Indian Cuisine" in prompt

    def test_parse_valid_json_output(self, agent):
        raw_json = """
        {
          "name": "Biryani",
          "description": "Fragrant basmati rice cooked with saffron, spices, and marinated mutton.",
          "category": "traditional",
          "meal_types": ["lunch", "dinner"],
          "cuisine_hint": "Indian Cuisine",
          "country_hint": "India",
          "confidence": 0.92,
          "reasoning": "Well-documented dish extracted from authoritative text."
        }
        """
        parsed = agent.parse_output(raw_json)
        assert isinstance(parsed, DishOutput)
        assert parsed.name == "Biryani"
        assert parsed.confidence == 0.92

    def test_parse_markdown_wrapped_json(self, agent):
        markdown_json = """```json
        {
          "name": "Pani Puri",
          "description": "Crispy hollow puris filled with spiced potato and tamarind water.",
          "category": "street_food",
          "meal_types": ["snack", "street_food"],
          "cuisine_hint": "Indian Cuisine",
          "country_hint": "India",
          "confidence": 0.94,
          "reasoning": "Extracted from street food list page with clear ingredient list."
        }
        ```"""
        parsed = agent.parse_output(markdown_json)
        assert isinstance(parsed, DishOutput)
        assert parsed.name == "Pani Puri"

    def test_parse_invalid_json_raises_value_error(self, agent):
        with pytest.raises(ValueError):
            agent.parse_output("This is plain text, not JSON.")

    @patch.object(DishInformationAgent, "_call_llm")
    def test_run_success(self, mock_llm, agent, sample_page):
        mock_json = """
        {
          "name": "Biryani",
          "description": "Fragrant basmati rice cooked with saffron, spices, and marinated mutton.",
          "category": "traditional",
          "meal_types": ["lunch", "dinner"],
          "cuisine_hint": "Indian Cuisine",
          "country_hint": "India",
          "confidence": 0.92,
          "reasoning": "Valid extraction from authoritative Wikipedia source content."
        }
        """
        mock_llm.return_value = (mock_json, 150, 200, "vllm/THUDM/GLM-Z1-9B-0414")

        output, run_record = agent.run(
            sample_page,
            context={"dish_name": "Biryani", "country_context": "India", "cuisine_context": "Indian Cuisine"},
        )

        assert isinstance(output, DishOutput)
        assert run_record.model_name == "vllm/THUDM/GLM-Z1-9B-0414"
        assert run_record.confidence == 0.92
        assert run_record.validation_passed is True
