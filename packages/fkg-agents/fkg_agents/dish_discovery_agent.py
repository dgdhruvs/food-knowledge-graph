"""
Dish Discovery Agent — evaluates candidate strings extracted from web pages
and uses LLM reasoning to discover valid, specific real-world dish entities
while rejecting generic category headers (e.g. 'Festive Sweets', 'Popular Recipes').
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import httpx
import jinja2
import structlog
from pydantic import BaseModel, Field, ValidationError

from fkg_agents.base_agent import BaseAgent
from fkg_common.models.parsed_page import ParsedPage
from fkg_normalizer.entity_normalizer import EntityNormalizer

log = structlog.get_logger()
PROMPT_DIR = Path(__file__).parent / "prompts"


class DishDiscoveryOutput(BaseModel):
    """Pydantic contract for Dish Discovery Agent output."""

    candidate_name: str = Field(..., description="Original candidate dish string")
    is_valid_dish: bool = Field(..., description="True if string represents a specific culinary dish entity")
    canonical_name: str = Field(..., description="Cleaned canonical name of the dish")
    category: str = Field("traditional", description="Dish category (e.g. traditional, street_food)")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0")
    reasoning: str = Field(..., min_length=20, description="Detailed explanation for validation decision")


class DishDiscoveryAgent(BaseAgent[DishDiscoveryOutput]):
    """Agent 3 — Validates candidate dish names and filters out generic category headers."""

    def __init__(
        self,
        model_name: str | None = None,
        vllm_url: str | None = None,
        ollama_url: str | None = None,
        openai_api_key: str | None = None,
    ) -> None:
        self._model_name = model_name or os.getenv("LLM_MODEL_NAME", "THUDM/GLM-Z1-9B-0414")
        self._vllm_url = vllm_url or os.getenv("VLLM_BASE_URL", os.getenv("OPENAI_BASE_URL", "http://localhost:8000/v1"))
        self._ollama_url = ollama_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self._openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")

        loader = jinja2.FileSystemLoader(str(PROMPT_DIR))
        self._jinja_env = jinja2.Environment(loader=loader, autoescape=False)
        self._template = self._jinja_env.get_template("dish_discovery_agent.jinja2")
        self._normalizer = EntityNormalizer()

    @property
    def agent_type(self) -> str:
        return "dish_discovery"

    def build_prompt(self, page: ParsedPage, context: dict | None = None) -> str:
        ctx = context or {}
        return self._template.render(
            page_title=page.title or "Unknown Page",
            url=page.url,
            candidate_name=ctx.get("candidate_name", "Unknown Candidate"),
            source_snippet=(page.main_text or "")[:1500],
        )

    def parse_output(self, raw: str) -> DishDiscoveryOutput:
        clean_text = raw.strip()
        if clean_text.startswith("```"):
            clean_text = re.sub(r"^```(?:json)?\s*", "", clean_text)
            clean_text = re.sub(r"\s*```$", "", clean_text)

        try:
            data = json.loads(clean_text)
            return DishDiscoveryOutput(**data)
        except (json.JSONDecodeError, ValidationError) as exc:
            log.warning("dish_discovery_agent.parse_error", raw_snippet=clean_text[:200], error=str(exc))
            raise ValueError(f"Failed to parse LLM response into DishDiscoveryOutput: {exc}") from exc

    def validate_candidate(self, page: ParsedPage, candidate_name: str) -> DishDiscoveryOutput:
        """Helper method to validate a candidate dish name with LLM reasoning or fallback."""
        # 1. First run deterministic normalizer check
        norm = self._normalizer.normalize_dish_name(candidate_name)
        if not norm:
            return DishDiscoveryOutput(
                candidate_name=candidate_name,
                is_valid_dish=False,
                canonical_name=candidate_name,
                category="noise",
                confidence=0.99,
                reasoning=f"Rejected as generic website section/collection header: '{candidate_name}'.",
            )

        # 2. Invoke LLM for AI reasoning validation
        try:
            output, _ = self.run(page, context={"candidate_name": norm.normalized})
            return output
        except Exception as exc:
            log.warning("dish_discovery_agent.llm_fallback", candidate=candidate_name, error=str(exc))
            # Deterministic fallback when LLM is unreachable
            return DishDiscoveryOutput(
                candidate_name=candidate_name,
                is_valid_dish=True,
                canonical_name=norm.normalized,
                category="traditional",
                confidence=0.85,
                reasoning=f"Passed deterministic normalizer checks for valid dish name '{norm.normalized}'.",
            )

    def _call_llm(self, prompt: str) -> tuple[str, int, int, str]:
        try:
            return self._call_vllm(prompt)
        except Exception as exc:
            log.warning("dish_discovery_agent.vllm_failed", error=str(exc))
            if self._openai_api_key and not self._openai_api_key.startswith("your_"):
                return self._call_openai(prompt)
            return self._call_ollama(prompt)

    def _call_vllm(self, prompt: str) -> tuple[str, int, int, str]:
        url = f"{self._vllm_url.rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self._openai_api_key and not self._openai_api_key.startswith("your_"):
            headers["Authorization"] = f"Bearer {self._openai_api_key}"
        else:
            headers["Authorization"] = "Bearer EMPTY"
        payload = {
            "model": self._model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
        }
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]
            usage = data.get("usage", {})
            return choice["message"]["content"], usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0), f"vllm/{self._model_name}"

    def _call_ollama(self, prompt: str) -> tuple[str, int, int, str]:
        url = f"{self._ollama_url.rstrip('/')}/api/generate"
        payload = {
            "model": self._model_name,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            response_text = data.get("response", "")
            return response_text, data.get("prompt_eval_count", 0), data.get("eval_count", 0), f"ollama/{self._model_name}"

    def _call_openai(self, prompt: str) -> tuple[str, int, int, str]:
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self._openai_api_key}", "Content-Type": "application/json"}
        payload = {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
        }
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]
            usage = data.get("usage", {})
            return choice["message"]["content"], usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0), "openai/gpt-4o-mini"
