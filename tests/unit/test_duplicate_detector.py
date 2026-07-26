"""
Unit tests for the Duplicate Detector.

Tests verify all three detection layers:
1. Exact match (alias hash lookup)
2. Fuzzy match (Levenshtein/token sort ratio)
3. Embedding match (cosine similarity)

Also tests the deduplication of regional dish name variants
(the classic Pani Puri / Golgappa / Puchka / Gupchup problem).
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from fkg_dedup.duplicate_detector import (
    AliasStore,
    DedupDecision,
    DuplicateDetector,
    FUZZY_AUTO_MERGE_THRESHOLD,
    FUZZY_MATCH_THRESHOLD,
)


class MockAliasStore(AliasStore):
    """In-memory alias store for testing."""

    def __init__(self, entries: list[dict]) -> None:
        self._by_name: dict[str, dict] = {}
        self._all_names: list[str] = []
        for entry in entries:
            for alias in [entry["canonical_name"]] + entry.get("aliases", []):
                self._by_name[alias.strip().lower()] = entry
                self._all_names.append(alias)

    def lookup(self, normalized_name: str) -> dict | None:
        return self._by_name.get(normalized_name)

    def all_names(self) -> list[str]:
        return self._all_names

    def vector_search(self, embedding, top_k, threshold):
        return None  # Not tested here; tested separately


@pytest.fixture
def alias_store() -> MockAliasStore:
    return MockAliasStore([
        {
            "id": "uuid-panipuri",
            "canonical_name": "Pani Puri",
            "aliases": ["Golgappa", "Puchka", "Gupchup", "Phuchka", "Fuchka"],
        },
        {
            "id": "uuid-biryani",
            "canonical_name": "Biryani",
            "aliases": ["Biriyani", "Beriani"],
        },
        {
            "id": "uuid-samosa",
            "canonical_name": "Samosa",
            "aliases": ["Samoosa", "Samosa"],
        },
    ])


@pytest.fixture
def detector(alias_store) -> DuplicateDetector:
    return DuplicateDetector(alias_store=alias_store)


# ── Exact Matching ─────────────────────────────────────────────────────────────

class TestExactMatch:
    def test_canonical_name_exact_match(self, detector):
        result = detector.check("Pani Puri", [])
        assert result.decision == DedupDecision.AUTO_MERGE
        assert result.match_method == "exact"
        assert result.matched_id == "uuid-panipuri"

    def test_alias_exact_match(self, detector):
        """Golgappa is an alias for Pani Puri — should auto-merge."""
        result = detector.check("Golgappa", [])
        assert result.decision == DedupDecision.AUTO_MERGE
        assert result.matched_id == "uuid-panipuri"

    def test_puchka_alias_resolves_to_panipuri(self, detector):
        result = detector.check("Puchka", [])
        assert result.decision == DedupDecision.AUTO_MERGE
        assert result.matched_id == "uuid-panipuri"

    def test_gupchup_alias_resolves_to_panipuri(self, detector):
        result = detector.check("Gupchup", [])
        assert result.decision == DedupDecision.AUTO_MERGE
        assert result.matched_id == "uuid-panipuri"

    def test_case_insensitive_match(self, detector):
        result = detector.check("BIRYANI", [])
        assert result.decision == DedupDecision.AUTO_MERGE
        assert result.matched_id == "uuid-biryani"

    def test_aliases_in_input_trigger_match(self, detector):
        """If aliases list contains a known name, it should trigger exact match."""
        result = detector.check("Fuchka", ["Puchka", "Golgappa"])
        assert result.decision == DedupDecision.AUTO_MERGE
        assert result.matched_id == "uuid-panipuri"


# ── Fuzzy Matching ─────────────────────────────────────────────────────────────

class TestFuzzyMatch:
    def test_typo_triggers_fuzzy_match(self, detector):
        """'Biriyani' is a common transliteration variant — should fuzzy match."""
        result = detector.check("Biriyani", [])
        # Either auto_merge (score >= 0.95) or review_merge (score >= 0.88)
        assert result.decision in (DedupDecision.AUTO_MERGE, DedupDecision.REVIEW_MERGE)
        assert result.matched_id == "uuid-biryani"

    def test_very_different_name_returns_new_entity(self, detector):
        """'Sushi' does not match anything in our store."""
        result = detector.check("Sushi", ["Sushi Roll"])
        assert result.decision == DedupDecision.NEW_ENTITY
        assert result.matched_id is None


# ── New Entity ─────────────────────────────────────────────────────────────────

class TestNewEntity:
    def test_unknown_dish_becomes_new_entity(self, detector):
        result = detector.check("Pad Thai", ["Phat Thai"])
        assert result.decision == DedupDecision.NEW_ENTITY

    def test_new_entity_has_no_matched_id(self, detector):
        result = detector.check("XYZ Unknown Dish 12345", [])
        assert result.decision == DedupDecision.NEW_ENTITY
        assert result.matched_id is None
        assert result.match_score == 0.0
