"""user-service — accounts, login, profile. Emits 401/403/404."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request
from pydantic import BaseModel

from .base import identify_consumer, make_app
from .data import USERS, USERS_BY_EMAIL

app = make_app("user-service")


class LoginBody(BaseModel):
    email: str
    password: str


@app.post("/login")
async def login(body: LoginBody):
    user = USERS_BY_EMAIL.get(body.email)
    if user is None or user["password"] != body.password:
        raise HTTPException(status_code=401, detail="invalid email or password")
    return {"token": f"tok_{user['id']}", "user": {k: user[k] for k in ("id", "email", "name", "tier")}}


@app.get("/me")
async def me(request: Request, x_user_email: str | None = Header(default=None)):
    if not x_user_email:
        raise HTTPException(status_code=401, detail="authentication required")
    identify_consumer(request)
    user = USERS_BY_EMAIL.get(x_user_email)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    return {k: user[k] for k in ("id", "email", "name", "tier")}


@app.get("/users", dependencies=[Depends(identify_consumer)])
async def list_users(x_user_tier: str | None = Header(default=None)):
    # Only admins may list everyone.
    if x_user_tier != "admin":
        raise HTTPException(status_code=403, detail="admin tier required")
    return {"count": len(USERS), "users": [{k: u[k] for k in ("id", "email", "name", "tier")} for u in USERS]}


@app.get("/users/{user_id}", dependencies=[Depends(identify_consumer)])
async def get_user(user_id: str):
    for u in USERS:
        if u["id"] == user_id:
            return {k: u[k] for k in ("id", "email", "name", "tier")}
    raise HTTPException(status_code=404, detail=f"user {user_id} not found")
