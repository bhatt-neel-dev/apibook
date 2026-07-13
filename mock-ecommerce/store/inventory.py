"""inventory-service — stock levels + reservations. Emits 404/409."""

from __future__ import annotations

import random

from fastapi import Depends, HTTPException
from pydantic import BaseModel

from .base import identify_consumer, make_app
from .data import PRODUCTS, PRODUCTS_BY_ID

app = make_app("inventory-service")


class ReserveBody(BaseModel):
    product_id: str
    quantity: int = 1


@app.get("/stock", dependencies=[Depends(identify_consumer)])
async def all_stock():
    return {"stock": {p["id"]: p["stock"] for p in PRODUCTS}}


@app.get("/stock/{product_id}", dependencies=[Depends(identify_consumer)])
async def stock(product_id: str):
    product = PRODUCTS_BY_ID.get(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=f"product {product_id} not found")
    return {"product_id": product_id, "available": product["stock"]}


@app.post("/reserve", dependencies=[Depends(identify_consumer)])
async def reserve(body: ReserveBody):
    # The warehouse system is occasionally unreachable.
    if random.random() < 0.05:
        raise HTTPException(status_code=503, detail="warehouse system unavailable")
    product = PRODUCTS_BY_ID.get(body.product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=f"product {body.product_id} not found")
    if body.quantity <= 0:
        raise HTTPException(status_code=400, detail="quantity must be positive")
    if product["stock"] < body.quantity:
        # Out of stock — the classic 409 conflict.
        raise HTTPException(status_code=409, detail=f"only {product['stock']} of {body.product_id} in stock")
    return {"reserved": True, "product_id": body.product_id, "quantity": body.quantity}
