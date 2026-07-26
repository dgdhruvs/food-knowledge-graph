"""
Pydantic models for the parsed page output produced by the Parser stage.
This is the contract between the Parser and the Normalizer.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, HttpUrl


class TableData(BaseModel):
    """A single HTML table extracted from a page."""

    caption: Optional[str] = None
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)


class ImageRef(BaseModel):
    """An image reference extracted from a page."""

    src: str
    alt: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None


class ParsedPage(BaseModel):
    """Structured output of the Parser stage.

    Represents all deterministically extracted information from a
    single crawled web page. No AI is involved in producing this model.

    Design decision: ALL extraction is deterministic here. AI begins
    only at the Normalizer → Agent pipeline that follows.
    """

    # ── Source provenance ─────────────────────────────────────────────────────
    crawl_job_id: str = Field(..., description="UUID of the crawl job that fetched this page")
    source_id: str = Field(..., description="UUID of the source that owns this URL")
    url: str = Field(..., description="URL that was crawled")
    canonical_url: Optional[str] = Field(None, description="Canonical URL if different (from <link rel=canonical>)")
    s3_raw_key: str = Field(..., description="Object storage key for the raw HTML content")

    # ── Content ───────────────────────────────────────────────────────────────
    title: Optional[str] = Field(None, description="Page <title> tag content")
    headings: list[str] = Field(default_factory=list, description="All H1–H6 headings in document order")
    main_text: Optional[str] = Field(None, description="Main body text after boilerplate removal (trafilatura)")
    tables: list[TableData] = Field(default_factory=list, description="Extracted HTML tables")
    lists: list[list[str]] = Field(default_factory=list, description="Extracted HTML lists (ul/ol)")
    images: list[ImageRef] = Field(default_factory=list)

    # ── Structured data ────────────────────────────────────────────────────────
    schema_org: Optional[dict[str, Any]] = Field(
        None,
        description="Schema.org structured data extracted by extruct",
    )
    json_ld: Optional[dict[str, Any]] = Field(
        None,
        description="JSON-LD data from <script type='application/ld+json'>",
    )
    open_graph: Optional[dict[str, str]] = Field(
        None,
        description="OpenGraph meta tags",
    )

    # ── Metadata ──────────────────────────────────────────────────────────────
    language: Optional[str] = Field(None, description="Detected language (BCP-47, e.g. 'en', 'hi', 'ar')")
    author: Optional[str] = Field(None, description="Author from meta tags or byline")
    published_date: Optional[datetime] = Field(None, description="Publication date if available")
    description_meta: Optional[str] = Field(None, description="<meta name='description'> content")

    # ── Quality ───────────────────────────────────────────────────────────────
    source_trust_score: float = Field(..., ge=0.0, le=1.0, description="Trust score of the source")
    parse_version: str = Field(..., description="Version of the parser that produced this output")
    parsed_at: datetime = Field(..., description="Timestamp of when parsing was completed")
    has_recipe_schema: bool = Field(False, description="True if Schema.org Recipe type was found")
    word_count: Optional[int] = Field(None, ge=0)
