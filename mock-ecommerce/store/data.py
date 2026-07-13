"""In-memory mock data for the store. No database — everything is fake."""

from __future__ import annotations

PRODUCTS = [
    {"id": "p1001", "name": "Aurora Wireless Headphones", "category": "audio", "price": 129.99, "stock": 42},
    {"id": "p1002", "name": "Nimbus Mechanical Keyboard", "category": "accessories", "price": 89.50, "stock": 18},
    {"id": "p1003", "name": "Fjord Insulated Bottle", "category": "outdoors", "price": 24.00, "stock": 200},
    {"id": "p1004", "name": "Halo 4K Webcam", "category": "video", "price": 74.99, "stock": 7},
    {"id": "p1005", "name": "Ember Smart Mug", "category": "kitchen", "price": 99.95, "stock": 0},
    {"id": "p1006", "name": "Terra Running Shoes", "category": "apparel", "price": 119.00, "stock": 63},
    {"id": "p1007", "name": "Pixel Desk Lamp", "category": "home", "price": 39.99, "stock": 88},
    {"id": "p1008", "name": "Cobalt USB-C Hub", "category": "accessories", "price": 45.00, "stock": 3},
    {"id": "p1009", "name": "Solstice Sunglasses", "category": "apparel", "price": 59.00, "stock": 120},
    {"id": "p1010", "name": "Vortex Bluetooth Speaker", "category": "audio", "price": 64.99, "stock": 25},
    {"id": "p1011", "name": "Meridian Notebook", "category": "office", "price": 14.50, "stock": 500},
    {"id": "p1012", "name": "Zephyr Drone Mini", "category": "video", "price": 299.00, "stock": 0},
]
PRODUCTS_BY_ID = {p["id"]: p for p in PRODUCTS}
CATEGORIES = sorted({p["category"] for p in PRODUCTS})

# Registered shoppers. Tier drives some authorization behavior.
USERS = [
    {"id": "u1", "email": "neel.bhatt@example.com", "name": "Neel Bhatt", "tier": "premium", "password": "hunter2"},
    {"id": "u2", "email": "aarav.patel@example.com", "name": "Aarav Patel", "tier": "standard", "password": "letmein"},
    {"id": "u3", "email": "riya.shah@example.com", "name": "Riya Shah", "tier": "premium", "password": "s3cret"},
    {"id": "u4", "email": "vivaan.mehta@example.com", "name": "Vivaan Mehta", "tier": "standard", "password": "pass123"},
    {"id": "u5", "email": "ananya.desai@example.com", "name": "Ananya Desai", "tier": "admin", "password": "admin!"},
    {"id": "u6", "email": "kabir.pandya@example.com", "name": "Kabir Pandya", "tier": "standard", "password": "qwerty"},
]
USERS_BY_EMAIL = {u["email"]: u for u in USERS}
