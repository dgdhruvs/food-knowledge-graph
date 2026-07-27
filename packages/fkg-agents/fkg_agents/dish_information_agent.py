"""
Dish Information Agent — extracts rich structured dish knowledge using LLM reasoning.

Integrates with:
- Local LLM: Ollama (http://ollama:11434)
- Cloud LLM: OpenAI API (or compatible local endpoints)

Outputs: DishOutput Pydantic model with confidence score and reasoning log.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import httpx
import jinja2
import structlog
from pydantic import ValidationError

from fkg_agents.base_agent import BaseAgent
from fkg_common.models.dish import DishOutput
from fkg_common.models.parsed_page import ParsedPage

log = structlog.get_logger()

PROMPT_DIR = Path(__file__).parent / "prompts"


class DishInformationAgent(BaseAgent[DishOutput]):
    """Agent responsible for detailed, per-dish culinary metadata extraction."""

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

        # Setup Jinja2 template environment
        loader = jinja2.FileSystemLoader(str(PROMPT_DIR))
        self._jinja_env = jinja2.Environment(loader=loader, autoescape=False)
        self._template = self._jinja_env.get_template("dish_information_agent.jinja2")

    @property
    def agent_type(self) -> str:
        return "dish_information"

    def build_prompt(self, page: ParsedPage, context: dict | None = None) -> str:
        """Render prompt template with page and context variables."""
        ctx = context or {}
        return self._template.render(
            dish_name=ctx.get("dish_name", page.title or "Unknown Dish"),
            country_context=ctx.get("country_context", "Unknown"),
            cuisine_context=ctx.get("cuisine_context", "Unknown"),
            source_content=page.main_text[:4000],
        )

    def parse_output(self, raw: str) -> DishOutput:
        """Clean markdown code blocks and parse into DishOutput model."""
        clean_text = raw.strip()
        # Remove ```json ... ``` wrapper if present
        if clean_text.startswith("```"):
            clean_text = re.sub(r"^```(?:json)?\s*", "", clean_text)
            clean_text = re.sub(r"\s*```$", "", clean_text)

        try:
            data = json.loads(clean_text)
            return DishOutput(**data)
        except (json.JSONDecodeError, ValidationError) as exc:
            log.warning("dish_agent.parse_error", raw_snippet=clean_text[:200], error=str(exc))
            raise ValueError(f"Failed to parse LLM response into DishOutput: {exc}") from exc

    def _call_llm(self, prompt: str) -> tuple[str, int, int, str]:
        """Invoke vLLM, local Ollama instance, or OpenAI API."""
        try:
            return self._call_vllm(prompt)
        except Exception as exc:
            log.warning("dish_information_agent.vllm_failed", error=str(exc))
            if self._openai_api_key and not self._openai_api_key.startswith("your_"):
                return self._call_openai(prompt)
            return self._call_ollama(prompt)

    def _call_vllm(self, prompt: str) -> tuple[str, int, int, str]:
        """Invoke vLLM OpenAI-compatible endpoint."""
        url = f"{self._vllm_url.rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self._openai_api_key and not self._openai_api_key.startswith("your_"):
            headers["Authorization"] = f"Bearer {self._openai_api_key}"
        else:
            headers["Authorization"] = "Bearer EMPTY"
        payload = {
            "model": self._model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]
            content = choice["message"]["content"]
            usage = data.get("usage", {})
            return (
                content,
                usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0),
                f"vllm/{self._model_name}",
            )

    def _call_ollama(self, prompt: str) -> tuple[str, int, int, str]:
        """Invoke Ollama REST endpoint."""
        url = f"{self._ollama_url.rstrip('/')}/api/generate"
        payload = {
            "model": self._model_name,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            response_text = data.get("response", "")
            eval_count = data.get("eval_count", 0)
            prompt_eval_count = data.get("prompt_eval_count", 0)
            return response_text, prompt_eval_count, eval_count, f"ollama/{self._model_name}"

    def _call_openai(self, prompt: str) -> tuple[str, int, int, str]:
        """Invoke OpenAI Chat Completions endpoint."""
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._openai_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]
            content = choice["message"]["content"]
            usage = data.get("usage", {})
            return (
                content,
                usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0),
                "openai/gpt-4o-mini",
            )
