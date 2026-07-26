"""
Duplicate Detection Engine.

Design:
- Layer 1 — Exact match on canonical name (fastest, O(1) hash lookup)
- Layer 2 — Fuzzy match on name + aliases (Levenshtein distance, token sort ratio)
- Layer 3 — Semantic embedding match (cosine similarity in vector space)
- Layer 4 — Alias resolution (check global alias table)

A match triggers one of:
- AUTO_MERGE: High confidence duplicate → merge automatically
- REVIEW_MERGE: Medium confidence → human review queue
- NEW_ENTITY: No match → create new node

Why three layers?
- Exact match catches perfect duplicates instantly (e.g. "Biryani" == "Biryani")
- Fuzzy match handles OCR errors, transliteration variants ("Biriyani")
- Embedding match catches semantic equivalents across languages
  ("水饺" and "Boiled Dumplings" are the same dish)

Alternative considered: Using only embeddings.
Rejected because: Pure embedding matching has false positives
(e.g. "Lamb Curry" and "Chicken Curry" would score high similarity).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import structlog
from rapidfuzz import fuzz, process

log = structlog.get_logger()

# Thresholds (tunable without code changes via environment config)
EXACT_MATCH_THRESHOLD = 1.0
FUZZY_MATCH_THRESHOLD = 0.88       # 88% fuzzy similarity → review
FUZZY_AUTO_MERGE_THRESHOLD = 0.95  # 95% → auto merge
EMBEDDING_MATCH_THRESHOLD = 0.92   # Cosine similarity


class DedupDecision(str, Enum):
    AUTO_MERGE = "auto_merge"
    REVIEW_MERGE = "review_merge"
    NEW_ENTITY = "new_entity"


@dataclass
class DedupResult:
    """Result of the deduplication check for a single candidate dish."""

    decision: DedupDecision
    candidate_name: str
    matched_id: str | None = None
    matched_name: str | None = None
    match_score: float = 0.0
    match_method: str | None = None
    reasoning: str = ""


class DuplicateDetector:
    """
    Multi-layer duplicate detection for dish entities.

    The detector is initialized with an alias store — a fast lookup
    structure that maps every known name/alias to its canonical entity ID.
    """

    def __init__(self, alias_store: "AliasStore") -> None:
        self._alias_store = alias_store

    def check(self, name: str, aliases: list[str], embedding: list[float] | None = None) -> DedupResult:
        """Check if a candidate dish already exists in the knowledge graph.

        Args:
            name: Primary name of the candidate dish.
            aliases: All known aliases and alternate names.
            embedding: Optional vector embedding of the dish description.

        Returns:
            DedupResult indicating whether to auto-merge, review, or create new.
        """
        all_names = [name] + aliases

        # ── Layer 1: Exact match ───────────────────────────────────────────────
        for candidate in all_names:
            result = self._exact_match(candidate)
            if result:
                log.info("dedup.exact_match", candidate=name, matched=result["canonical_name"])
                return DedupResult(
                    decision=DedupDecision.AUTO_MERGE,
                    candidate_name=name,
                    matched_id=result["id"],
                    matched_name=result["canonical_name"],
                    match_score=1.0,
                    match_method="exact",
                    reasoning=f"Exact alias match on '{candidate}'",
                )

        # ── Layer 2: Fuzzy match ───────────────────────────────────────────────
        fuzzy_result = self._fuzzy_match(all_names)
        if fuzzy_result:
            score, matched = fuzzy_result
            if score >= FUZZY_AUTO_MERGE_THRESHOLD:
                return DedupResult(
                    decision=DedupDecision.AUTO_MERGE,
                    candidate_name=name,
                    matched_id=matched["id"],
                    matched_name=matched["canonical_name"],
                    match_score=score,
                    match_method="fuzzy",
                    reasoning=f"High-confidence fuzzy match ({score:.2%})",
                )
            elif score >= FUZZY_MATCH_THRESHOLD:
                return DedupResult(
                    decision=DedupDecision.REVIEW_MERGE,
                    candidate_name=name,
                    matched_id=matched["id"],
                    matched_name=matched["canonical_name"],
                    match_score=score,
                    match_method="fuzzy",
                    reasoning=f"Medium-confidence fuzzy match ({score:.2%}) — requires review",
                )

        # ── Layer 3: Embedding match ───────────────────────────────────────────
        if embedding:
            embed_result = self._embedding_match(embedding)
            if embed_result:
                score, matched = embed_result
                if score >= EMBEDDING_MATCH_THRESHOLD:
                    return DedupResult(
                        decision=DedupDecision.REVIEW_MERGE,
                        candidate_name=name,
                        matched_id=matched["id"],
                        matched_name=matched["canonical_name"],
                        match_score=score,
                        match_method="embedding",
                        reasoning=f"Semantic embedding similarity ({score:.2%}) — requires review",
                    )

        # ── No match found → new entity ────────────────────────────────────────
        return DedupResult(
            decision=DedupDecision.NEW_ENTITY,
            candidate_name=name,
            reasoning="No match found across all dedup layers",
        )

    def _exact_match(self, name: str) -> dict | None:
        """O(1) lookup in alias hash table."""
        normalized = name.strip().lower()
        return self._alias_store.lookup(normalized)

    def _fuzzy_match(self, names: list[str]) -> tuple[float, dict] | None:
        """Fuzzy string matching against all known dish names using token_sort_ratio.

        token_sort_ratio is chosen over simple ratio because it handles
        word-order variations (e.g. "Biryani Lamb" vs "Lamb Biryani").
        """
        all_known = self._alias_store.all_names()
        best_score = 0.0
        best_match = None

        for name in names:
            result = process.extractOne(
                name,
                all_known,
                scorer=fuzz.token_sort_ratio,
                score_cutoff=FUZZY_MATCH_THRESHOLD * 100,
            )
            if result and result[1] / 100 > best_score:
                best_score = result[1] / 100
                best_match = self._alias_store.lookup(result[0].strip().lower())

        if best_match:
            return best_score, best_match
        return None

    def _embedding_match(self, embedding: list[float]) -> tuple[float, dict] | None:
        """Vector similarity search in the vector database.

        In production, this calls pgvector or Weaviate.
        Returns the closest match if above threshold.
        """
        return self._alias_store.vector_search(embedding, top_k=1, threshold=EMBEDDING_MATCH_THRESHOLD)


class AliasStore:
    """
    In-memory + vector store abstraction for dish alias lookups.

    In production, this is backed by:
    - Redis hash map for exact/fuzzy lookups (hot cache)
    - pgvector for embedding similarity search
    - PostgreSQL entity_aliases table as the source of truth
    """

    def lookup(self, normalized_name: str) -> dict | None:
        """Look up a normalized name and return the canonical entity dict."""
        raise NotImplementedError

    def all_names(self) -> list[str]:
        """Return all known canonical names and aliases for fuzzy matching."""
        raise NotImplementedError

    def vector_search(self, embedding: list[float], top_k: int, threshold: float) -> tuple[float, dict] | None:
        """Find the most similar entity by embedding cosine similarity."""
        raise NotImplementedError
