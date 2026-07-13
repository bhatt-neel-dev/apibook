"""cart-service — per-shopper carts. Adding an item validates the product with
catalog-service; checkout hands off to order-service. Both are cross-service
traces (cart → catalog, and cart → order → inventory + payment)."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request
from pydantic import BaseModel

from .base import call_service, identify_consumer, make_app

app = make_app("cart-service")

# email -> list of {product_id, quantity}
_CARTS: dict[str, list[dict]] = {}


class AddItemBody(BaseModel):
    product_id: str
    quantity: int = 1


def _cart_key(email: str | None) -> str:
    return email or "guest"


@app.get("/cart", dependencies=[Depends(identify_consumer)])
async def get_cart(x_user_email: str | None = Header(default=None)):
    return {"owner": _cart_key(x_user_email), "items": _CARTS.get(_cart_key(x_user_email), [])}


@app.post("/cart/items", status_code=201, dependencies=[Depends(identify_consumer)])
async def add_item(body: AddItemBody, request: Request, x_user_email: str | None = Header(default=None)):
    if body.quantity <= 0:
        raise HTTPException(status_code=400, detail="quantity must be positive")

    # Validate the product exists via catalog-service (cross-service call).
    resp = await call_service("catalog-service", "GET", f"/products/{body.product_id}", request=request)
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail=f"product {body.product_id} not found")
    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail="catalog service error")

    cart = _CARTS.setdefault(_cart_key(x_user_email), [])
    cart.append({"product_id": body.product_id, "quantity": body.quantity})
    return {"owner": _cart_key(x_user_email), "items": cart}


@app.delete("/cart/items/{product_id}", status_code=204, dependencies=[Depends(identify_consumer)])
async def remove_item(product_id: str, x_user_email: str | None = Header(default=None)):
    cart = _CARTS.get(_cart_key(x_user_email), [])
    new_cart = [i for i in cart if i["product_id"] != product_id]
    if len(new_cart) == len(cart):
        raise HTTPException(status_code=404, detail=f"{product_id} not in cart")
    _CARTS[_cart_key(x_user_email)] = new_cart
    return None


@app.post("/cart/checkout", status_code=201, dependencies=[Depends(identify_consumer)])
async def checkout(request: Request, x_user_email: str | None = Header(default=None)):
    cart = _CARTS.get(_cart_key(x_user_email), [])
    if not cart:
        raise HTTPException(status_code=400, detail="cart is empty")

    # Hand off to order-service, which fans out to inventory + payment.
    resp = await call_service("order-service", "POST", "/orders", request=request, json={"items": cart})
    if resp.status_code >= 400:
        # Bubble up the order-service status (402/409/etc.) to the shopper.
        raise HTTPException(status_code=resp.status_code, detail=resp.json().get("detail", "checkout failed"))

    _CARTS[_cart_key(x_user_email)] = []
    return resp.json()
