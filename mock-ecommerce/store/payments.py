"""payment-service — charges. Deliberately flaky: declines (402), gateway
errors (500), and the occasional slow call, so the dashboard shows a realistic
error + latency mix."""

from __future__ import annotations

import asyncio
import random

from fastapi import Depends, HTTPException
from pydantic import BaseModel

import apilens

from .base import identify_consumer, make_app

app = make_app("payment-service")

_PAYMENTS: dict[str, dict] = {}
_counter = {"n": 0}


class ChargeBody(BaseModel):
    order_id: str
    amount: float
    currency: str = "USD"


@app.post("/charge", dependencies=[Depends(identify_consumer)])
async def charge(body: ChargeBody):
    if body.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")

    # Simulate talking to an external gateway (shows up as its own span).
    with apilens.span("gateway.authorize", kind="http", attributes={"amount": body.amount}):
        await asyncio.sleep(random.uniform(0.02, 0.12))
        if random.random() < 0.08:  # ~8% slow calls
            await asyncio.sleep(random.uniform(0.3, 0.9))

    roll = random.random()
    if roll < 0.06:  # ~6% gateway blows up
        raise HTTPException(status_code=500, detail="payment gateway error")
    if roll < 0.10:  # ~4% provider unreachable
        raise HTTPException(status_code=503, detail="payment provider temporarily unavailable")
    if roll < 0.22:  # ~12% card declined
        raise HTTPException(status_code=402, detail="card declined")

    _counter["n"] += 1
    pid = f"pay_{_counter['n']:05d}"
    _PAYMENTS[pid] = {"id": pid, "order_id": body.order_id, "amount": body.amount, "status": "captured"}
    return _PAYMENTS[pid]


@app.get("/payments/{payment_id}", dependencies=[Depends(identify_consumer)])
async def get_payment(payment_id: str):
    payment = _PAYMENTS.get(payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail=f"payment {payment_id} not found")
    return payment


@app.post("/payments/{payment_id}/refund", dependencies=[Depends(identify_consumer)])
async def refund(payment_id: str):
    payment = _PAYMENTS.get(payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail=f"payment {payment_id} not found")
    if payment["status"] == "refunded":
        raise HTTPException(status_code=422, detail="payment already refunded")
    payment["status"] = "refunded"
    return payment
