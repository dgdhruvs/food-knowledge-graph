"""
Base class for all FKG AI Extraction Agents.

Design principles:
- Every agent has a single, bounded responsibility.
- Agents communicate via typed Pydantic models only.
- All prompts are Jinja2 templates stored as files (not strings in code).
- Agents retry on schema violation up to MAX_RETRIES times.
- Every run is recorded in agent_runs table for provenance.
- AI is used ONLY for tasks requiring reasoning. Everything else is deterministic.
"""
from __future__ import annotations

import abc
import time
from typing import Generic, TypeVar

import structlog
from pydantic import BaseModel

from fkg_common.models.parsed_page import ParsedPage

log = structlog.get_logger()

OutputT = TypeVar("OutputT", bound=BaseModel)

# Confidence threshold below which output triggers human review
REVIEW_CONFIDENCE_THRESHOLD = 0.72
MAX_RETRIES = 3


class AgentRun(BaseModel):
    """Record of a single agent execution, persisted for provenance."""

    agent_type: str
    model_name: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    raw_output: str
    confidence: float
    validation_passed: bool
    validation_errors: list[str]
    retry_count: int


class BaseAgent(abc.ABC, Generic[OutputT]):
    """Abstract base class for all FKG extraction agents.

    Subclasses must implement:
        - `agent_type`: string identifier (e.g. 'country', 'dish_information')
        - `build_prompt(page)`: constructs the LLM prompt
        - `parse_output(raw)`: parses LLM response into typed Pydantic model
        - `confidence_threshold`: minimum confidence before human review

    The run() method handles:
        - Prompt construction
        - LLM invocation with retry
        - Schema validation
        - Provenance recording
        - Review queue routing
    """

    @property
    @abc.abstractmethod
    def agent_type(self) -> str:
        ...

    @property
    def confidence_threshold(self) -> float:
        return REVIEW_CONFIDENCE_THRESHOLD

    @abc.abstractmethod
    def build_prompt(self, page: ParsedPage, context: dict | None = None) -> str:
        """Build the full prompt to send to the LLM.

        Args:
            page: The parsed page containing source content.
            context: Optional upstream agent outputs (e.g. CountryOutput).

        Returns:
            Complete prompt string ready for LLM invocation.
        """
        ...

    @abc.abstractmethod
    def parse_output(self, raw: str) -> OutputT:
        """Parse and validate the LLM's raw string output into a typed model.

        Should raise ValueError or ValidationError on failure — these are
        caught by the run() method and trigger a retry.
        """
        ...

    def run(self, page: ParsedPage, context: dict | None = None) -> tuple[OutputT, AgentRun]:
        """Execute the agent with retry logic and provenance recording.

        Returns:
            Tuple of (typed output, AgentRun record)

        The AgentRun record must be persisted by the caller.
        """
        prompt = self.build_prompt(page, context)
        last_error: Exception | None = None
        retry_count = 0

        for attempt in range(1, MAX_RETRIES + 1):
            start_ms = int(time.time() * 1000)
            raw_output = ""

            try:
                raw_output, input_tokens, output_tokens, model_name = self._call_llm(prompt)
                latency_ms = int(time.time() * 1000) - start_ms

                parsed = self.parse_output(raw_output)

                run_record = AgentRun(
                    agent_type=self.agent_type,
                    model_name=model_name,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_ms=latency_ms,
                    raw_output=raw_output,
                    confidence=parsed.confidence,  # type: ignore[attr-defined]
                    validation_passed=True,
                    validation_errors=[],
                    retry_count=retry_count,
                )

                if parsed.confidence < self.confidence_threshold:  # type: ignore[attr-defined]
                    log.warning(
                        "agent.low_confidence",
                        agent=self.agent_type,
                        confidence=parsed.confidence,  # type: ignore[attr-defined]
                        threshold=self.confidence_threshold,
                    )

                log.info(
                    "agent.success",
                    agent=self.agent_type,
                    attempt=attempt,
                    confidence=parsed.confidence,  # type: ignore[attr-defined]
                    latency_ms=latency_ms,
                )
                return parsed, run_record

            except Exception as exc:
                retry_count += 1
                last_error = exc
                latency_ms = int(time.time() * 1000) - start_ms
                log.warning(
                    "agent.retry",
                    agent=self.agent_type,
                    attempt=attempt,
                    error=str(exc),
                )

        # All retries exhausted
        log.error(
            "agent.failed",
            agent=self.agent_type,
            retries=MAX_RETRIES,
            error=str(last_error),
        )
        raise RuntimeError(
            f"Agent '{self.agent_type}' failed after {MAX_RETRIES} attempts. "
            f"Last error: {last_error}"
        ) from last_error

    @abc.abstractmethod
    def _call_llm(self, prompt: str) -> tuple[str, int, int, str]:
        """Call the underlying LLM and return (raw_text, input_tokens, output_tokens, model_name).

        Concrete implementations handle routing to local Ollama or cloud LLM
        based on complexity score and cost budget.
        """
        ...
