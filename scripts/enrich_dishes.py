"""
Enrich Dishes Script — runs DishIngredientEnrichmentAgent (Agent 7) across dishes
missing ingredients in PostgreSQL and Neo4j.
"""
import asyncio
import os
import structlog
import asyncpg
from neo4j import AsyncGraphDatabase

from fkg_agents.dish_ingredient_enrichment_agent import DishIngredientEnrichmentAgent

log = structlog.get_logger()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://fkg:fkgpassword@localhost:5432/fkg")
if DATABASE_URL.startswith("postgresql+asyncpg://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://", 1)

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "fkgpassword")


async def run_enrichment():
    print("Connecting to PostgreSQL & Neo4j...")
    conn = await asyncpg.connect(DATABASE_URL)
    neo_driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    agent = DishIngredientEnrichmentAgent()

    try:
        # Fetch dishes missing ingredients
        rows = await conn.fetch(
            """
            SELECT d.id, d.name, d.description, c.name as cuisine_name, co.name as country_name
            FROM dishes d
            LEFT JOIN cuisines c ON d.cuisine_id = c.id
            LEFT JOIN countries co ON d.country_id = co.id
            WHERE (SELECT count(*) FROM dish_ingredients di WHERE di.dish_id = d.id) = 0
            """
        )
        print(f"Found {len(rows)} dishes requiring ingredient enrichment.")

        enriched_count = 0
        for row in rows:
            dish_id = row["id"]
            dish_name = row["name"]
            description = row["description"] or ""
            cuisine_name = row["cuisine_name"] or "Unknown"
            country_name = row["country_name"] or "Unknown"

            print(f"Enriching: {dish_name} ({cuisine_name})...")

            # Run Agent 7 (Web Recipe Search + AI Extraction)
            result = agent.enrich_dish(
                dish_name=dish_name,
                description=description,
                cuisine_hint=cuisine_name,
                country_hint=country_name,
            )

            if result and result.ingredients:
                print(f"  -> Extracted {len(result.ingredients)} ingredients: {result.ingredients[:6]}")
                for ing_name in result.ingredients:
                    ing_id = await conn.fetchval(
                        """
                        INSERT INTO ingredients (name, review_status)
                        VALUES ($1, 'auto_approved')
                        ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
                        RETURNING id
                        """,
                        ing_name,
                    )
                    await conn.execute(
                        """
                        INSERT INTO dish_ingredients (dish_id, ingredient_id)
                        VALUES ($1, $2)
                        ON CONFLICT (dish_id, ingredient_id) DO NOTHING
                        """,
                        dish_id, ing_id,
                    )

                    # Also write to Neo4j graph
                    async with neo_driver.session() as session:
                        await session.run(
                            """
                            MERGE (d:Dish {id: $dish_id})
                            MERGE (i:Ingredient {name: $ing_name})
                            MERGE (d)-[:HAS_INGREDIENT]->(i)
                            """,
                            dish_id=str(dish_id), ing_name=ing_name
                        )

                enriched_count += 1

        print(f"\nDone! Successfully enriched {enriched_count} dishes with ingredients.")

    finally:
        await conn.close()
        await neo_driver.close()


if __name__ == "__main__":
    asyncio.run(run_enrichment())
