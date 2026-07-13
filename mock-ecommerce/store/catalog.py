"""catalog-service — product catalog. Read-heavy; 404s on unknown products."""

from __future__ import annotations

import random

from fastapi import Depends, HTTPException, Query

from .base import LONG_TEXT, identify_consumer, make_app
from .data import CATEGORIES, PRODUCTS, PRODUCTS_BY_ID

app = make_app("catalog-service")


@app.get("/products", dependencies=[Depends(identify_consumer)])
async def list_products(category: str | None = None):
    items = PRODUCTS
    if category:
        items = [p for p in PRODUCTS if p["category"] == category]
    return {"count": len(items), "products": items}


@app.get("/products/search", dependencies=[Depends(identify_consumer)])
async def search_products(q: str = Query(default="")):
    term = q.strip().lower()
    if not term:
        raise HTTPException(status_code=400, detail="query parameter 'q' is required")
    hits = [p for p in PRODUCTS if term in p["name"].lower() or term in p["category"]]
    return {"query": q, "count": len(hits), "products": hits}


@app.get("/categories", dependencies=[Depends(identify_consumer)])
async def list_categories():
    return {"categories": CATEGORIES}


@app.get("/products/{product_id}", dependencies=[Depends(identify_consumer)])
async def get_product(product_id: str):
    product = PRODUCTS_BY_ID.get(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=f"product {product_id} not found")
    return product


@app.get("/products/{product_id}/description", dependencies=[Depends(identify_consumer)])
async def product_description(product_id: str):
    """Deliberately long response body (rich product copy)."""
    product = PRODUCTS_BY_ID.get(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=f"product {product_id} not found")
    return {"id": product_id, "name": product["name"], "description": LONG_TEXT}


@app.get("/products/{product_id}/recommendations", dependencies=[Depends(identify_consumer)])
async def recommendations(product_id: str):
    """Heavy, long-body endpoint backed by a flaky recommendation engine (503)."""
    if product_id not in PRODUCTS_BY_ID:
        raise HTTPException(status_code=404, detail=f"product {product_id} not found")
    if random.random() < 0.15:
        raise HTTPException(status_code=503, detail="recommendation engine temporarily unavailable")
    recs = [
        {"id": p["id"], "name": p["name"], "price": p["price"], "blurb": LONG_TEXT[:400]}
        for p in PRODUCTS
    ]
    return {"product_id": product_id, "count": len(recs), "recommendations": recs}


@app.get("/products/{product_id}/reviews", dependencies=[Depends(identify_consumer)])
async def product_reviews(product_id: str):
    if product_id not in PRODUCTS_BY_ID:
        raise HTTPException(status_code=404, detail=f"product {product_id} not found")
    return {"product_id": product_id, "rating": 4.3, "reviews": [
        {"author": "verified buyer", "stars": 5, "text": "Exactly as described."},
        {"author": "verified buyer", "stars": 4, "text": "Good value."},
    ]}
