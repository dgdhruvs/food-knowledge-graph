"""
Web Crawler Worker — active polling loop for crawl jobs.

Fetches queued URLs, extracts structured content from HTML tables,
Schema.org JSON-LD recipe scripts, and article headers, normalizes entities,
validates rules, and persists dishes to PostgreSQL and Neo4j.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
import aiohttp
import asyncpg
from bs4 import BeautifulSoup
import structlog
from neo4j import AsyncGraphDatabase
from fkg_normalizer.entity_normalizer import EntityNormalizer
from fkg_agents.dish_discovery_agent import DishDiscoveryAgent
from fkg_common.models.parsed_page import ParsedPage

log = structlog.get_logger()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://fkg:fkgpassword@postgres:5432/fkg")
if DATABASE_URL.startswith("postgresql+asyncpg://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://", 1)

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "fkgpassword")

USER_AGENT = "FoodKnowledgeGraphBot/1.0 (+https://fkg.example.com/bot)"

URL_METADATA_MAP = {
    "https://en.wikipedia.org/wiki/List_of_Indian_dishes": ("India", "Indian Cuisine"),
    "https://en.wikipedia.org/wiki/List_of_Italian_dishes": ("Italy", "Italian Cuisine"),
    "https://en.wikipedia.org/wiki/List_of_Japanese_dishes": ("Japan", "Japanese Cuisine"),
    "https://en.wikipedia.org/wiki/List_of_Mexican_dishes": ("Mexico", "Mexican Cuisine"),
}


def extract_dishes_from_wikipedia(soup: BeautifulSoup, url: str) -> list[dict]:
    """Dynamically parse all dish entries from Wikipedia HTML tables."""
    if url not in URL_METADATA_MAP:
        return []

    country_name, cuisine_name = URL_METADATA_MAP[url]
    extracted_dishes = []

    tables = soup.find_all("table", class_="wikitable")
    for table in tables:
        rows = table.find_all("tr")
        for row in rows[1:]:  # skip header row
            cols = row.find_all(["td", "th"])
            if not cols:
                continue

            name_col = cols[0]
            link = name_col.find("a")
            name = link.get_text().strip() if link else name_col.get_text().strip()

            # Filter out non-dish noise
            if not name or len(name) < 2 or len(name) > 60 or "List of" in name or name.isdigit():
                continue

            # Extract description from remaining columns
            desc_parts = [c.get_text().strip() for c in cols[1:] if c.get_text().strip()]
            description = " — ".join(desc_parts) if desc_parts else f"Traditional dish from {country_name}."

            extracted_dishes.append({
                "name": name,
                "native_name": None,
                "english_name": name,
                "aliases": [],
                "description": description[:600],
                "category": "traditional",
                "meal_types": ["lunch", "dinner"],
                "cuisine_name": cuisine_name,
                "country_name": country_name,
                "taste_profile": ["savory"],
                "texture": None,
                "prep_time_min": 25,
                "cook_time_min": 35,
                "serving_size_g": 250,
                "is_vegetarian": False,
                "is_vegan": False,
                "contains_meat": False,
                "contains_dairy": False,
                "ingredients": [],
                "cooking_methods": ["traditional cooking"],
                "calories_kcal": 350,
                "protein_g": 12,
                "confidence": 0.88,
            })

    return extracted_dishes


def extract_dishes_from_generic_recipe_site(soup: BeautifulSoup, url: str) -> list[dict]:
    """Extract structured dish information from Schema.org JSON-LD scripts and article titles."""
    extracted_dishes = []
    scripts = soup.find_all("script", type="application/ld+json")

    country_name = "India" if ("india" in url.lower() or "vegrecipes" in url.lower()) else "Global"
    cuisine_name = "Indian Cuisine" if ("india" in url.lower() or "vegrecipes" in url.lower()) else "Global Cuisine"

    for script in scripts:
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
            items = data if isinstance(data, list) else [data]
            if isinstance(data, dict) and "@graph" in data:
                items = data["@graph"]

            for item in items:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("@type", "")

                # Case 1: Direct Recipe Schema
                if item_type == "Recipe" or (isinstance(item_type, list) and "Recipe" in item_type):
                    name = item.get("name")
                    if name:
                        desc = item.get("description", f"Vegetarian dish from {country_name}.")
                        ingredients = item.get("recipeIngredient", [])
                        if isinstance(ingredients, str):
                            ingredients = [ingredients]

                        extracted_dishes.append({
                            "name": name.strip(),
                            "native_name": None,
                            "english_name": name.strip(),
                            "aliases": [],
                            "description": desc[:600] if desc else f"Popular dish from {country_name}.",
                            "category": "traditional",
                            "meal_types": ["lunch", "dinner"],
                            "cuisine_name": cuisine_name,
                            "country_name": country_name,
                            "taste_profile": ["savory"],
                            "texture": None,
                            "prep_time_min": 20,
                            "cook_time_min": 30,
                            "serving_size_g": 250,
                            "is_vegetarian": True,
                            "is_vegan": False,
                            "contains_meat": False,
                            "contains_dairy": False,
                            "ingredients": [i.strip()[:60] for i in ingredients[:10]],
                            "cooking_methods": ["cooking"],
                            "calories_kcal": 300,
                            "protein_g": 10,
                            "confidence": 0.92,
                        })

                # Case 2: ItemList Schema
                elif item_type == "ItemList":
                    element_list = item.get("itemListElement", [])
                    for elem in element_list:
                        if isinstance(elem, dict):
                            item_obj = elem.get("item", elem)
                            name = item_obj.get("name") if isinstance(item_obj, dict) else None
                            if name and len(name) < 60:
                                extracted_dishes.append({
                                    "name": name.strip(),
                                    "native_name": None,
                                    "english_name": name.strip(),
                                    "aliases": [],
                                    "description": f"Recipe from {url}.",
                                    "category": "traditional",
                                    "meal_types": ["lunch", "dinner"],
                                    "cuisine_name": cuisine_name,
                                    "country_name": country_name,
                                    "taste_profile": ["savory"],
                                    "texture": None,
                                    "prep_time_min": 25,
                                    "cook_time_min": 35,
                                    "serving_size_g": 250,
                                    "is_vegetarian": True,
                                    "is_vegan": False,
                                    "contains_meat": False,
                                    "contains_dairy": False,
                                    "ingredients": [],
                                    "cooking_methods": ["cooking"],
                                    "calories_kcal": 320,
                                    "protein_g": 8,
                                    "confidence": 0.85,
                                })
        except Exception:
            continue

    # Fallback: Extract recipe card headings if no JSON-LD recipe was found
    if not extracted_dishes:
        headings = soup.find_all(["h2", "h3"])
        for h in headings[:20]:
            title_text = h.get_text().strip()
            if title_text and 3 < len(title_text) < 55 and not any(kw in title_text.lower() for kw in ["comment", "leave", "reply", "search", "navigation"]):
                extracted_dishes.append({
                    "name": title_text,
                    "native_name": None,
                    "english_name": title_text,
                    "aliases": [],
                    "description": f"Popular recipe from {url}.",
                    "category": "traditional",
                    "meal_types": ["lunch", "dinner"],
                    "cuisine_name": cuisine_name,
                    "country_name": country_name,
                    "taste_profile": ["savory"],
                    "texture": None,
                    "prep_time_min": 20,
                    "cook_time_min": 30,
                    "serving_size_g": 250,
                    "is_vegetarian": True,
                    "is_vegan": False,
                    "contains_meat": False,
                    "contains_dairy": False,
                    "ingredients": [],
                    "cooking_methods": ["cooking"],
                    "calories_kcal": 300,
                    "protein_g": 9,
                    "confidence": 0.80,
                })

    return extracted_dishes


async def process_crawl_jobs():
    """Poll queued crawl jobs, parse content, and write to PostgreSQL and Neo4j."""
    log.info("crawler.worker_started", db=DATABASE_URL)

    db = await asyncpg.connect(DATABASE_URL)
    neo_driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    try:
        # Fetch pending jobs
        jobs = await db.fetch("SELECT id, source_id, url FROM crawl_jobs WHERE status = 'queued' LIMIT 10")
        if not jobs:
            log.info("crawler.no_queued_jobs")
            return

        async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}) as http_session:
            for job in jobs:
                job_id = job["id"]
                url = job["url"]
                log.info("crawler.processing_job", job_id=str(job_id), url=url)

                # Mark as fetching
                await db.execute("UPDATE crawl_jobs SET status = 'fetching', started_at = now() WHERE id = $1", job_id)

                try:
                    async with http_session.get(url, timeout=20) as response:
                        html_text = await response.text()
                        status_code = response.status

                    # Parse HTML using BeautifulSoup
                    soup = BeautifulSoup(html_text, "html.parser")
                    title = soup.title.string if soup.title else "Food List"
                    headings = [h.get_text().strip() for h in soup.find_all(["h1", "h2", "h3"])[:15]]

                    # Insert parsed page record
                    parsed_page_id = await db.fetchval(
                        """
                        INSERT INTO parsed_pages (crawl_job_id, url, title, main_text, structured_data, parse_version)
                        VALUES ($1, $2, $3, $4, $5, '1.0.0')
                        RETURNING id
                        """,
                        job_id, url, title, soup.get_text()[:4000], json.dumps({"headings": headings})
                    )

                    # Dynamic extraction of all dishes from HTML tables or JSON-LD recipe scripts
                    if url in URL_METADATA_MAP:
                        raw_dishes = extract_dishes_from_wikipedia(soup, url)
                    else:
                        raw_dishes = extract_dishes_from_generic_recipe_site(soup, url)

                    normalizer = EntityNormalizer()
                    discovery_agent = DishDiscoveryAgent()
                    parsed_page = ParsedPage(
                        url=url,
                        title=soup.title.string if soup.title else "",
                        main_text=soup.get_text()[:2000],
                        language="en"
                    )

                    dishes_to_ingest = []
                    for d in raw_dishes:
                        norm = normalizer.normalize_dish_name(d["name"])
                        if not norm:
                            log.info("crawler.dish_rejected_as_noise", raw_name=d["name"])
                            continue
                        
                        # AI Discovery Agent Verification
                        discovery = discovery_agent.validate_candidate(parsed_page, norm.normalized)
                        if not discovery.is_valid_dish:
                            log.info(
                                "crawler.dish_rejected_by_ai_discovery_agent",
                                raw_name=d["name"],
                                canonical_name=discovery.canonical_name,
                                reasoning=discovery.reasoning
                            )
                            continue

                        d["name"] = discovery.canonical_name
                        d["english_name"] = discovery.canonical_name
                        d["confidence"] = min(d.get("confidence", 0.8), discovery.confidence)
                        dishes_to_ingest.append(d)

                    log.info("crawler.dishes_extracted", url=url, count=len(dishes_to_ingest))

                    for d in dishes_to_ingest:
                        await ingest_dish(db, neo_driver, d, url, parsed_page_id)

                    # Update job status to parsed
                    await db.execute(
                        "UPDATE crawl_jobs SET status = 'parsed', http_status = $1, completed_at = now() WHERE id = $2",
                        status_code, job_id
                    )

                    log.info("crawler.job_completed", url=url, dishes_ingested=len(dishes_to_ingest))

                except Exception as exc:
                    log.error("crawler.job_failed", url=url, error=str(exc))
                    await db.execute("UPDATE crawl_jobs SET status = 'failed', error_message = $1 WHERE id = $2", str(exc), job_id)

    finally:
        await db.close()
        await neo_driver.close()


async def ingest_dish(db: asyncpg.Connection, neo_driver, dish_data: dict, source_url: str, parsed_page_id):
    """Persist extracted dish into PostgreSQL relational tables and Neo4j graph nodes/edges."""
    country_name = dish_data["country_name"]
    cuisine_name = dish_data["cuisine_name"]
    dish_name = dish_data["name"]

    # 1. Fetch or create country and cuisine IDs from Postgres
    country_id = await db.fetchval(
        """
        INSERT INTO countries (name) VALUES ($1)
        ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
        RETURNING id
        """,
        country_name
    )

    cuisine_id = await db.fetchval(
        """
        INSERT INTO cuisines (name, country_id) VALUES ($1, $2)
        ON CONFLICT (name) DO UPDATE SET country_id = EXCLUDED.country_id
        RETURNING id
        """,
        cuisine_name, country_id
    )

    # 2. Upsert Dish in Postgres
    dish_id = await db.fetchval(
        """
        INSERT INTO dishes (
            name, native_name, english_name, aliases, description,
            cuisine_id, country_id, category, meal_types, taste_profile,
            texture, prep_time_min, cook_time_min, serving_size_g,
            is_vegetarian, is_vegan, contains_meat, contains_dairy,
            review_status, confidence
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9::meal_type[], $10,
            $11, $12, $13, $14, $15, $16, $17, $18, 'auto_approved', $19
        )
        ON CONFLICT (name, cuisine_id) DO UPDATE SET
            description = EXCLUDED.description,
            confidence = EXCLUDED.confidence
        RETURNING id
        """,
        dish_name, dish_data.get("native_name"), dish_data.get("english_name"),
        dish_data.get("aliases", []), dish_data["description"], cuisine_id, country_id,
        dish_data["category"], dish_data["meal_types"], dish_data["taste_profile"],
        dish_data.get("texture"), dish_data.get("prep_time_min"), dish_data.get("cook_time_min"),
        dish_data.get("serving_size_g"), dish_data.get("is_vegetarian"), dish_data.get("is_vegan"),
        dish_data.get("contains_meat"), dish_data.get("contains_dairy"), dish_data["confidence"]
    )

    # 3. Upsert Ingredients and Junction
    for ing_name in dish_data.get("ingredients", []):
        ing_id = await db.fetchval(
            """
            INSERT INTO ingredients (name, review_status)
            VALUES ($1, 'auto_approved')
            ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
            """,
            ing_name
        )
        await db.execute(
            """
            INSERT INTO dish_ingredients (dish_id, ingredient_id)
            VALUES ($1, $2)
            ON CONFLICT (dish_id, ingredient_id) DO NOTHING
            """,
            dish_id, ing_id
        )

    # 4. Upsert Nutrition Profile
    if "calories_kcal" in dish_data:
        await db.execute(
            """
            INSERT INTO nutrition_profiles (dish_id, calories_kcal, protein_g, per_serving_g, confidence)
            VALUES ($1, $2, $3, $4, $5)
            """,
            dish_id, dish_data["calories_kcal"], dish_data.get("protein_g", 0),
            dish_data.get("serving_size_g", 100), dish_data["confidence"]
        )

    # 5. Graph Write to Neo4j
    async with neo_driver.session() as session:
        await session.run(
            """
            MERGE (c:Country {name: $country_name})
            MERGE (cu:Cuisine {name: $cuisine_name})
            MERGE (d:Dish {id: $dish_id})
            SET d.name = $dish_name,
                d.description = $description,
                d.confidence = $confidence,
                d.review_status = 'auto_approved'
            MERGE (d)-[:BELONGS_TO_CUISINE]->(cu)
            MERGE (cu)-[:BELONGS_TO_REGION]->(c)
            """,
            country_name=country_name,
            cuisine_name=cuisine_name,
            dish_id=str(dish_id),
            dish_name=dish_name,
            description=dish_data["description"],
            confidence=dish_data["confidence"],
        )

        for ing_name in dish_data.get("ingredients", []):
            await session.run(
                """
                MATCH (d:Dish {id: $dish_id})
                MERGE (i:Ingredient {name: $ing_name})
                MERGE (d)-[:CONTAINS]->(i)
                """,
                dish_id=str(dish_id),
                ing_name=ing_name
            )


async def main_loop():
    """Worker polling loop."""
    while True:
        try:
            await process_crawl_jobs()
        except Exception as exc:
            log.error("worker.loop_error", error=str(exc))
        await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main_loop())
