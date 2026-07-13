"""Drive realistic + error traffic across the mock store.

Hits all six services with a mix of successful flows (browse → cart → checkout,
which fans out to inventory + payment) and deliberate errors (404 unknown
product, 400 bad query, 401 bad login, 403 non-admin, 402 declined, 409 out of
stock, 500 gateway). Each request carries a random shopper identity so APILens
attributes traffic to consumers.

Usage:
    python generate_traffic.py [iterations]     # default 60
"""

from __future__ import annotations

import random
import sys
import time

import httpx

BASE = {
    "catalog": "http://localhost:9101",
    "users": "http://localhost:9102",
    "cart": "http://localhost:9103",
    "orders": "http://localhost:9104",
    "payments": "http://localhost:9105",
    "inventory": "http://localhost:9106",
}

SHOPPERS = [
    {"email": "neel.bhatt@example.com", "name": "Neel Bhatt", "tier": "premium", "password": "hunter2"},
    {"email": "aarav.patel@example.com", "name": "Aarav Patel", "tier": "standard", "password": "letmein"},
    {"email": "riya.shah@example.com", "name": "Riya Shah", "tier": "premium", "password": "s3cret"},
    {"email": "ananya.desai@example.com", "name": "Ananya Desai", "tier": "admin", "password": "admin!"},
    {"email": "kabir.pandya@example.com", "name": "Kabir Pandya", "tier": "standard", "password": "qwerty"},
]

GOOD_PRODUCTS = ["p1001", "p1002", "p1003", "p1006", "p1007", "p1009", "p1010", "p1011"]
OOS_PRODUCTS = ["p1005", "p1012"]        # stock 0 -> 409 at checkout
BAD_PRODUCTS = ["p9999", "nope", "p0000"]  # -> 404


def headers(shopper: dict) -> dict:
    return {"X-User-Email": shopper["email"], "X-User-Name": shopper["name"], "X-User-Tier": shopper["tier"]}


def hit(client: httpx.Client, method: str, url: str, label: str, **kw) -> None:
    try:
        r = client.request(method, url, timeout=10.0, **kw)
        print(f"  {method:6} {label:38} -> {r.status_code}")
    except Exception as exc:  # a service being down shouldn't stop the run
        print(f"  {method:6} {label:38} -> ERR {exc}")


def scenario(client: httpx.Client) -> None:
    s = random.choice(SHOPPERS)
    h = headers(s)

    # Browse the catalog.
    hit(client, "GET", f"{BASE['catalog']}/products", "catalog /products", headers=h)
    hit(client, "GET", f"{BASE['catalog']}/categories", "catalog /categories", headers=h)
    hit(client, "GET", f"{BASE['catalog']}/products/{random.choice(GOOD_PRODUCTS)}", "catalog /products/{id}", headers=h)

    # A few deliberate errors, sometimes.
    if random.random() < 0.4:
        hit(client, "GET", f"{BASE['catalog']}/products/{random.choice(BAD_PRODUCTS)}", "catalog /products/{bad} 404", headers=h)
    if random.random() < 0.3:
        hit(client, "GET", f"{BASE['catalog']}/products/search", "catalog /search (no q) 400", headers=h)
    else:
        hit(client, "GET", f"{BASE['catalog']}/products/search", "catalog /search", headers=h, params={"q": "smart"})

    # Auth.
    if random.random() < 0.25:
        hit(client, "POST", f"{BASE['users']}/login", "users /login (bad) 401", json={"email": s["email"], "password": "wrong"})
    else:
        hit(client, "POST", f"{BASE['users']}/login", "users /login", json={"email": s["email"], "password": s["password"]})
    hit(client, "GET", f"{BASE['users']}/me", "users /me", headers=h)
    hit(client, "GET", f"{BASE['users']}/users", "users /users (admin-only)", headers=h)  # 403 unless admin

    # Add to cart (validates via catalog), sometimes a bad product -> 404.
    if random.random() < 0.3:
        hit(client, "POST", f"{BASE['cart']}/cart/items", "cart add {bad} 404", headers=h, json={"product_id": random.choice(BAD_PRODUCTS), "quantity": 1})
    for _ in range(random.randint(1, 3)):
        hit(client, "POST", f"{BASE['cart']}/cart/items", "cart add item", headers=h, json={"product_id": random.choice(GOOD_PRODUCTS), "quantity": random.randint(1, 3)})
    # Occasionally try to buy something out of stock -> 409 at checkout.
    if random.random() < 0.25:
        hit(client, "POST", f"{BASE['cart']}/cart/items", "cart add OOS item", headers=h, json={"product_id": random.choice(OOS_PRODUCTS), "quantity": 1})
    hit(client, "GET", f"{BASE['cart']}/cart", "cart /cart", headers=h)

    # Checkout -> order -> inventory + payment (cross-service trace; may 402/409/500).
    hit(client, "POST", f"{BASE['cart']}/cart/checkout", "cart /checkout (chain)", headers=h)

    # Direct pokes at the deeper services too.
    hit(client, "GET", f"{BASE['inventory']}/stock/{random.choice(GOOD_PRODUCTS)}", "inventory /stock/{id}", headers=h)
    if random.random() < 0.4:
        hit(client, "POST", f"{BASE['inventory']}/reserve", "inventory /reserve OOS 409", headers=h, json={"product_id": random.choice(OOS_PRODUCTS), "quantity": 5})

    # Long-body reads (large responses next to all the short ones).
    pid = random.choice(GOOD_PRODUCTS)
    hit(client, "GET", f"{BASE['catalog']}/products/{pid}/description", "catalog /description (long)", headers=h)
    hit(client, "GET", f"{BASE['catalog']}/products/{pid}/recommendations", "catalog /recommendations (long, 503?)", headers=h)

    # Direct payment charges — surface 500/503/402 the checkout path may not reach.
    for _ in range(random.randint(1, 2)):
        hit(client, "POST", f"{BASE['payments']}/charge", "payment /charge (direct)", headers=h,
            json={"order_id": "ord_direct", "amount": round(random.uniform(10, 300), 2)})

    # Deliberate 5xx + payload-size mix via the debug endpoint (any service).
    svc = random.choice(list(BASE))
    code = random.choice([500, 502, 503, 504])
    size = random.choice(["short", "long"])
    hit(client, "GET", f"{BASE[svc]}/debug/simulate", f"{svc} /simulate {code}/{size}", headers=h,
        params={"status": code, "size": size})
    if random.random() < 0.2:  # occasional genuine unhandled 500
        svc2 = random.choice(list(BASE))
        hit(client, "GET", f"{BASE[svc2]}/debug/boom", f"{svc2} /boom 500", headers=h)


def main() -> None:
    iterations = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    print(f"Driving {iterations} scenarios across Neel's Store microservices...\n")
    with httpx.Client() as client:
        for i in range(1, iterations + 1):
            print(f"[{i}/{iterations}] shopper scenario")
            scenario(client)
            time.sleep(random.uniform(0.05, 0.25))
    print("\nDone. Give the SDK a few seconds to flush, then check the APILens dashboard.")


if __name__ == "__main__":
    main()
