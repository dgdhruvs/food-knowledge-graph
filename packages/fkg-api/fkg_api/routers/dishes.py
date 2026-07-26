"""
Dish API router — search, detail, similar, variants, nutrition.
"""
from __future__ import annotations

import os
from typing import Optional
from uuid import UUID
import asyncpg
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://fkg:fkgpassword@postgres:5432/fkg")
if DATABASE_URL.startswith("postgresql+asyncpg://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://", 1)


async def get_db_pool():
    return await asyncpg.connect(DATABASE_URL)


@router.get("/", summary="List and search dishes")
async def list_dishes(
    q: Optional[str] = Query(None, description="Dish name or alias search term"),
    limit: int = Query(20, ge=1, le=100),
):
    """List all ingested dishes from PostgreSQL."""
    conn = await get_db_pool()
    try:
        if q:
            rows = await conn.fetch(
                """
                SELECT d.id, d.name, d.native_name, d.description, d.category, d.confidence, c.name as cuisine_name
                FROM dishes d
                LEFT JOIN cuisines c ON d.cuisine_id = c.id
                WHERE d.name ILIKE $1 OR $1 = ANY(d.aliases)
                LIMIT $2
                """,
                f"%{q}%", limit
            )
        else:
            rows = await conn.fetch(
                """
                SELECT d.id, d.name, d.native_name, d.description, d.category, d.confidence, c.name as cuisine_name
                FROM dishes d
                LEFT JOIN cuisines c ON d.cuisine_id = c.id
                ORDER BY d.created_at DESC
                LIMIT $1
                """,
                limit
            )
        return [dict(r) for r in rows]
    finally:
        await conn.close()


@router.get("/{dish_id}", summary="Get dish detail by ID")
async def get_dish(dish_id: UUID):
    """Returns details for a single dish."""
    conn = await get_db_pool()
    try:
        row = await conn.fetchrow(
            """
            SELECT d.*, c.name as cuisine_name, co.name as country_name
            FROM dishes d
            LEFT JOIN cuisines c ON d.cuisine_id = c.id
            LEFT JOIN countries co ON d.country_id = co.id
            WHERE d.id = $1
            """,
            dish_id
        )
        if not row:
            raise HTTPException(status_code=404, detail="Dish not found")
        
        ingredients = await conn.fetch(
            """
            SELECT i.name, di.is_optional, di.amount, di.unit
            FROM dish_ingredients di
            JOIN ingredients i ON di.ingredient_id = i.id
            WHERE di.dish_id = $1
            """,
            dish_id
        )

        res = dict(row)
        res["ingredients"] = [dict(ing) for ing in ingredients]
        return res
    finally:
        await conn.close()
