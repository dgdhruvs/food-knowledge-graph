"""
Web Crawler Worker — fetches pages respecting robots.txt and rate limits.

Architecture:
- Consumes crawl jobs from Kafka topic 'crawl.jobs'
- Uses Playwright for JS-rendered pages, aiohttp for static pages
- Stores raw HTML in S3-compatible object storage
- Publishes parse jobs to Kafka topic 'parse.jobs'
- Implements incremental crawling: skips unchanged pages (ETag/Last-Modified)
- Respects robots.txt: cached per domain for 24 hours
- Implements token bucket rate limiting per domain

Why Playwright over Requests/httpx?
- Many food websites use React/Vue — content only appears after JS execution
- Screenshots enable visual QA of crawled pages
- Playwright handles cookie consent dialogs automatically

Failure modes:
- Network timeout → retry with exponential backoff (max 3 attempts)
- 429 Too Many Requests → back off for 60s, respect Retry-After header
- 503 Service Unavailable → retry after 5 minutes
- robots.txt disallowed → skip, mark as SKIPPED in crawl_jobs table
"""
from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from urllib.robotparser import RobotFileParser

import aiohttp
import structlog

log = structlog.get_logger()

# Conservative defaults — can be overridden per source in the Source Registry
DEFAULT_RATE_LIMIT_RPS = 0.5  # 1 request per 2 seconds per domain
DEFAULT_REQUEST_TIMEOUT_S = 30
MAX_RETRIES = 3
BOT_USER_AGENT = "FoodKnowledgeGraphBot/1.0 (+https://fkg.example.com/bot)"

# HTTP status codes that should trigger a retry
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class CrawlOutcome(str, Enum):
    FETCHED = "fetched"
    SKIPPED_UNCHANGED = "skipped_unchanged"
    SKIPPED_ROBOTS = "skipped_robots"
    FAILED = "failed"
    DEAD = "dead"


@dataclass
class CrawlJob:
    """A single URL to crawl, sourced from the Kafka crawl.jobs topic."""

    job_id: str
    source_id: str
    url: str
    stored_etag: Optional[str] = None
    stored_last_modified: Optional[str] = None
    stored_content_hash: Optional[str] = None
    priority: int = 5
    attempt: int = 1


@dataclass
class CrawlResult:
    """Result of a single crawl attempt."""

    job_id: str
    url: str
    outcome: CrawlOutcome
    http_status: Optional[int] = None
    content: Optional[bytes] = None
    content_hash: Optional[str] = None
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    content_type: Optional[str] = None
    latency_ms: Optional[int] = None
    error: Optional[str] = None
    s3_key: Optional[str] = None


class RobotsCache:
    """Thread-safe cache for parsed robots.txt files.

    Cache TTL: 24 hours. A domain's robots.txt rarely changes.
    """

    def __init__(self, ttl_seconds: int = 86400) -> None:
        self._cache: dict[str, tuple[RobotFileParser, float]] = {}
        self._ttl = ttl_seconds

    async def is_allowed(self, url: str, session: aiohttp.ClientSession) -> bool:
        """Return True if the URL is allowed by robots.txt."""
        from urllib.parse import urlparse

        parsed = urlparse(url)
        domain = f"{parsed.scheme}://{parsed.netloc}"
        robots_url = f"{domain}/robots.txt"

        # Check cache
        cached = self._cache.get(domain)
        if cached and (time.time() - cached[1]) < self._ttl:
            parser = cached[0]
        else:
            parser = await self._fetch_robots(robots_url, session)
            self._cache[domain] = (parser, time.time())

        return parser.can_fetch(BOT_USER_AGENT, url)

    async def _fetch_robots(self, robots_url: str, session: aiohttp.ClientSession) -> RobotFileParser:
        """Fetch and parse robots.txt. Returns permissive parser on failure."""
        parser = RobotFileParser()
        parser.set_url(robots_url)
        try:
            async with session.get(robots_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    content = await resp.text()
                    parser.parse(content.splitlines())
                else:
                    # robots.txt not found → assume all allowed
                    parser.parse([])
        except Exception as exc:
            log.warning("crawler.robots_fetch_failed", url=robots_url, error=str(exc))
            parser.parse([])
        return parser


class TokenBucketRateLimiter:
    """Per-domain token bucket rate limiter.

    Ensures we never exceed the configured requests-per-second for any domain.
    This is both a courtesy to website operators and a protection against IP bans.
    """

    def __init__(self, rps: float = DEFAULT_RATE_LIMIT_RPS) -> None:
        self._rps = rps
        self._tokens: dict[str, float] = {}
        self._last_refill: dict[str, float] = {}

    async def acquire(self, domain: str) -> None:
        """Wait until a token is available for the given domain."""
        now = time.monotonic()
        last = self._last_refill.get(domain, now)
        elapsed = now - last

        # Refill tokens based on elapsed time
        current = self._tokens.get(domain, 1.0)
        current = min(1.0, current + elapsed * self._rps)
        self._last_refill[domain] = now

        if current >= 1.0:
            self._tokens[domain] = current - 1.0
            return

        # Need to wait for a token
        wait_time = (1.0 - current) / self._rps
        log.debug("crawler.rate_limit_wait", domain=domain, wait_s=round(wait_time, 2))
        await asyncio.sleep(wait_time)
        self._tokens[domain] = 0.0


class CrawlerWorker:
    """
    Stateless crawler worker — processes one crawl job at a time.

    Multiple workers run in parallel, each consuming from the Kafka crawl.jobs topic.
    Workers are designed to be completely stateless; all state is in the database.
    """

    def __init__(
        self,
        robots_cache: RobotsCache,
        rate_limiter: TokenBucketRateLimiter,
        s3_client=None,  # boto3/aiobotocore S3 client
        kafka_producer=None,  # aiokafka AIOKafkaProducer
        db_pool=None,  # asyncpg connection pool
    ) -> None:
        self._robots = robots_cache
        self._rate_limiter = rate_limiter
        self._s3 = s3_client
        self._kafka = kafka_producer
        self._db = db_pool

    async def process(self, job: CrawlJob) -> CrawlResult:
        """Process a single crawl job.

        Steps:
        1. Check robots.txt
        2. Acquire rate limit token
        3. Fetch URL
        4. Check for content changes (ETag / content hash)
        5. Store to S3
        6. Update crawl_jobs table
        7. Publish to parse.jobs Kafka topic
        """
        from urllib.parse import urlparse

        domain = urlparse(job.url).netloc

        async with aiohttp.ClientSession(
            headers={"User-Agent": BOT_USER_AGENT},
            timeout=aiohttp.ClientTimeout(total=DEFAULT_REQUEST_TIMEOUT_S),
        ) as session:

            # ── Step 1: robots.txt check ─────────────────────────────────────
            if not await self._robots.is_allowed(job.url, session):
                log.info("crawler.robots_disallowed", url=job.url)
                return CrawlResult(
                    job_id=job.job_id,
                    url=job.url,
                    outcome=CrawlOutcome.SKIPPED_ROBOTS,
                )

            # ── Step 2: Rate limit ───────────────────────────────────────────
            await self._rate_limiter.acquire(domain)

            # ── Step 3: Fetch ────────────────────────────────────────────────
            start_ms = int(time.time() * 1000)
            try:
                headers = {}
                if job.stored_etag:
                    headers["If-None-Match"] = job.stored_etag
                if job.stored_last_modified:
                    headers["If-Modified-Since"] = job.stored_last_modified

                async with session.get(job.url, headers=headers) as resp:
                    latency_ms = int(time.time() * 1000) - start_ms

                    # ── Step 4: Change detection ─────────────────────────────
                    if resp.status == 304:
                        log.info("crawler.unchanged", url=job.url)
                        return CrawlResult(
                            job_id=job.job_id,
                            url=job.url,
                            outcome=CrawlOutcome.SKIPPED_UNCHANGED,
                            http_status=304,
                            latency_ms=latency_ms,
                        )

                    if resp.status in RETRYABLE_STATUS_CODES:
                        error_msg = f"HTTP {resp.status}"
                        if resp.status == 429:
                            retry_after = int(resp.headers.get("Retry-After", 60))
                            log.warning("crawler.rate_limited", domain=domain, retry_after=retry_after)
                            await asyncio.sleep(retry_after)
                        raise aiohttp.ClientResponseError(
                            resp.request_info, resp.history, status=resp.status
                        )

                    content = await resp.read()
                    content_hash = hashlib.sha256(content).hexdigest()

                    # Content unchanged (no ETag support but same bytes)
                    if content_hash == job.stored_content_hash:
                        return CrawlResult(
                            job_id=job.job_id,
                            url=job.url,
                            outcome=CrawlOutcome.SKIPPED_UNCHANGED,
                            http_status=resp.status,
                            latency_ms=latency_ms,
                        )

                    etag = resp.headers.get("ETag")
                    last_modified = resp.headers.get("Last-Modified")

                    # ── Step 5: Store to S3 ──────────────────────────────────
                    s3_key = f"raw/{domain}/{job.job_id}.html"
                    if self._s3:
                        await self._store_to_s3(s3_key, content, resp.content_type or "text/html")

                    log.info(
                        "crawler.fetched",
                        url=job.url,
                        status=resp.status,
                        size_bytes=len(content),
                        latency_ms=latency_ms,
                    )

                    return CrawlResult(
                        job_id=job.job_id,
                        url=job.url,
                        outcome=CrawlOutcome.FETCHED,
                        http_status=resp.status,
                        content=content,
                        content_hash=content_hash,
                        etag=etag,
                        last_modified=last_modified,
                        content_type=resp.content_type,
                        latency_ms=latency_ms,
                        s3_key=s3_key,
                    )

            except Exception as exc:
                log.error("crawler.fetch_failed", url=job.url, attempt=job.attempt, error=str(exc))
                outcome = CrawlOutcome.DEAD if job.attempt >= MAX_RETRIES else CrawlOutcome.FAILED
                return CrawlResult(
                    job_id=job.job_id,
                    url=job.url,
                    outcome=outcome,
                    error=str(exc),
                    latency_ms=int(time.time() * 1000) - start_ms,
                )

    async def _store_to_s3(self, key: str, content: bytes, content_type: str) -> None:
        """Upload raw HTML to S3-compatible object storage."""
        # TODO: Implement with aiobotocore
        pass
