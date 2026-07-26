"""
Seed base reference data (countries, cuisines, ingredients, seed sources)
into PostgreSQL and Neo4j.
"""
import asyncio
import os
import uuid
import structlog
import asyncpg

log = structlog.get_logger()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://fkg:fkgpassword@localhost:5432/fkg")

SEED_COUNTRIES = [
    {"name": "India", "iso_alpha2": "IN", "iso_alpha3": "IND", "region": "Asia", "sub_region": "Southern Asia"},
    {"name": "Italy", "iso_alpha2": "IT", "iso_alpha3": "ITA", "region": "Europe", "sub_region": "Southern Europe"},
    {"name": "Japan", "iso_alpha2": "JP", "iso_alpha3": "JPN", "region": "Asia", "sub_region": "Eastern Asia"},
    {"name": "Mexico", "iso_alpha2": "MX", "iso_alpha3": "MEX", "region": "Americas", "sub_region": "Central America"},
    {"name": "France", "iso_alpha2": "FR", "iso_alpha3": "FRA", "region": "Europe", "sub_region": "Western Europe"},
    {"name": "Thailand", "iso_alpha2": "TH", "iso_alpha3": "THA", "region": "Asia", "sub_region": "South-eastern Asia"},
    {"name": "China", "iso_alpha2": "CN", "iso_alpha3": "CHN", "region": "Asia", "sub_region": "Eastern Asia"},
    {"name": "Morocco", "iso_alpha2": "MA", "iso_alpha3": "MAR", "region": "Africa", "sub_region": "Northern Africa"},
]

SEED_SOURCES = [
    {
        "url": "https://en.wikipedia.org/wiki/List_of_Indian_dishes",
        "domain": "en.wikipedia.org",
        "source_type": "wikipedia",
        "trust_score": 0.90,
        "language": "en",
        "country_iso": "IND",
        "crawl_priority": 9,
    },
    {
        "url": "https://en.wikipedia.org/wiki/List_of_Italian_dishes",
        "domain": "en.wikipedia.org",
        "source_type": "wikipedia",
        "trust_score": 0.90,
        "language": "en",
        "country_iso": "ITA",
        "crawl_priority": 9,
    },
    {
        "url": "https://en.wikipedia.org/wiki/List_of_Japanese_dishes",
        "domain": "en.wikipedia.org",
        "source_type": "wikipedia",
        "trust_score": 0.90,
        "language": "en",
        "country_iso": "JPN",
        "crawl_priority": 9,
    },
    {
        "url": "https://en.wikipedia.org/wiki/List_of_Mexican_dishes",
        "domain": "en.wikipedia.org",
        "source_type": "wikipedia",
        "trust_score": 0.90,
        "language": "en",
        "country_iso": "MEX",
        "crawl_priority": 9,
    },
]


async def seed():
    print("Connecting to PostgreSQL...")
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        # Seed Countries
        print(f"Seeding {len(SEED_COUNTRIES)} countries...")
        for c in SEED_COUNTRIES:
            await conn.execute(
                """
                INSERT INTO countries (name, iso_alpha2, iso_alpha3, region, sub_region)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (name) DO UPDATE SET
                    iso_alpha2 = EXCLUDED.iso_alpha2,
                    iso_alpha3 = EXCLUDED.iso_alpha3,
                    region = EXCLUDED.region,
                    sub_region = EXCLUDED.sub_region
                """,
                c["name"], c["iso_alpha2"], c["iso_alpha3"], c["region"], c["sub_region"]
            )

        # Seed Sources & Crawl Jobs
        print(f"Seeding {len(SEED_SOURCES)} initial food sources...")
        for s in SEED_SOURCES:
            source_id = await conn.fetchval(
                """
                INSERT INTO sources (url, domain, source_type, trust_score, language, country_iso, crawl_priority)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (url) DO UPDATE SET
                    trust_score = EXCLUDED.trust_score,
                    crawl_priority = EXCLUDED.crawl_priority
                RETURNING id
                """,
                s["url"], s["domain"], s["source_type"], s["trust_score"], s["language"], s["country_iso"], s["crawl_priority"]
            )

            # Create initial crawl job
            await conn.execute(
                """
                INSERT INTO crawl_jobs (source_id, url, status)
                VALUES ($1, $2, 'queued')
                """,
                source_id, s["url"]
            )

        print("✅ Base data and initial seed sources successfully created!")
        print("Crawl jobs queued in database table `crawl_jobs`.")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(seed())
