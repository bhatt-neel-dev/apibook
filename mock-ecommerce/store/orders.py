"""order-service — the orchestrator. Creating an order calls inventory-service
(reserve) and payment-service (charge), so each order is a cross-service trace:
order → inventory + payment."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel

from .base import call_service, identify_consumer, make_app
from .data import PRODUCTS_BY_ID

app = make_app("order-service")

_ORDERS: dict[str, dict] = {}
_counter = {"n": 0}


class OrderItem(BaseModel):
    product_id: str
    quantity: int = 1


class CreateOrderBody(BaseModel):
    items: list[OrderItem]


@app.get("/orders", dependencies=[Depends(identify_consumer)])
async def list_orders():
    return {"count": len(_ORDERS), "orders": list(_ORDERS.values())}


@app.get("/orders/{order_id}", dependencies=[Depends(identify_consumer)])
async def get_order(order_id: str):
    order = _ORDERS.get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"order {order_id} not found")
    return order


@app.post("/orders", status_code=201, dependencies=[Depends(identify_consumer)])
async def create_order(body: CreateOrderBody, request: Request):
    if not body.items:
        raise HTTPException(status_code=400, detail="order must contain at least one item")

    total = 0.0
    for item in body.items:
        product = PRODUCTS_BY_ID.get(item.product_id)
        if product is None:
            raise HTTPException(status_code=404, detail=f"product {item.product_id} not found")
        total += product["price"] * item.quantity

    _counter["n"] += 1
    order_id = f"ord_{_counter['n']:05d}"

    # 1) Reserve stock (inventory-service may 409 if out of stock).
    for item in body.items:
        resp = await call_service(
            "inventory-service", "POST", "/reserve",
            request=request, json={"product_id": item.product_id, "quantity": item.quantity},
        )
        if resp.status_code == 409:
            raise HTTPException(status_code=409, detail=f"{item.product_id} is out of stock")
        if resp.status_code >= 400:
            raise HTTPException(status_code=502, detail="inventory service error")

    # 2) Charge (payment-service may 402 decline or 500).
    pay = await call_service(
        "payment-service", "POST", "/charge",
        request=request, json={"order_id": order_id, "amount": round(total, 2)},
    )
    if pay.status_code == 402:
        raise HTTPException(status_code=402, detail="payment declined")
    if pay.status_code >= 500:
        raise HTTPException(status_code=502, detail="payment gateway unavailable")
    if pay.status_code >= 400:
        raise HTTPException(status_code=400, detail="payment failed")

    order = {
        "id": order_id,
        "items": [i.model_dump() for i in body.items],
        "total": round(total, 2),
        "payment_id": pay.json().get("id"),
        "status": "confirmed",
    }
    _ORDERS[order_id] = order
    return order
