# Neel's Store — mock e-commerce microservices

A fake but realistic online store, split into six independent microservices,
each instrumented with the [APILens](https://apilens.ai) Python SDK. It exists
to generate lifelike API traffic — successes, a broad mix of errors, consumer
attribution, and **cross-service distributed traces** — against a local APILens
stack so you can exercise the dashboard end to end.

Everything is in-memory mock data. No real database, no real payments.

## Services

| Service | Port | app_id | Highlights |
|---------|------|--------|-----------|
| catalog | 9101 | `catalog-service` | product list/search/detail; 404 on unknown product, 400 on empty query |
| user | 9102 | `user-service` | login (401 on bad creds), `/me` (401), `/users` (403 unless admin) |
| cart | 9103 | `cart-service` | add item (calls catalog to validate → 404), checkout (calls order) |
| order | 9104 | `order-service` | **orchestrator** — reserves stock + charges payment |
| payment | 9105 | `payment-service` | flaky on purpose: ~13% declines (402), ~5% gateway 500, occasional slow |
| inventory | 9106 | `inventory-service` | stock + reservations; 409 when out of stock |

All six report to the **Neel's Store** project (one project-level API key,
distinct `app_id` per service).

### Cross-service traces

- `POST cart /cart/checkout` → `order /orders` → `inventory /reserve` **+** `payment /charge`
- `POST cart /cart/items` → `catalog /products/{id}`

Outbound calls use `httpx`, which the SDK auto-instruments — so these show up as
a single trace waterfall spanning multiple services, with the `traceparent`
propagated automatically.

## Run it

```bash
cd mock-ecommerce
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# .env already has a local project key (see .env.example to point elsewhere).
./run.sh                          # start all six services
.venv/bin/python generate_traffic.py   # drive traffic (default 60 scenarios)
./stop.sh                         # stop all services
```

Then open the local dashboard, pick **Neel's Store**, and watch traffic, errors,
consumers, and traces per app. Logs for each service are under `logs/`.

## Choosing / upgrading the SDK

`run.sh` asks on every boot whether to use the **published** SDK (from PyPI) or
the **local** in-repo SDK at `../packages/sdk-python` (editable — handy for
testing SDK changes before publishing):

```
Which APILens SDK? [P]ublished (PyPI) / [l]ocal (../packages/sdk-python):
```

Manage it directly with `./sdk.sh`:

```bash
./sdk.sh status      # show what's installed (published vs local, version)
./sdk.sh published   # use the released PyPI package
./sdk.sh local       # use the editable in-repo SDK (../packages/sdk-python)
./sdk.sh upgrade     # upgrade the published package to the latest on PyPI
```

The raw upgrade command, if you prefer it explicit:

```bash
.venv/bin/pip install --upgrade 'apilenss[fastapi]'
```

Skip the prompt in scripts by setting the mode up front:
`SDK_MODE=published ./run.sh` or `SDK_MODE=local ./run.sh`. A mode switch takes
effect on the next `./run.sh` (restart the services to pick up a change).

## Error catalog

The traffic generator deliberately produces: `400` (bad query / bad quantity),
`401` (bad login, missing auth), `403` (non-admin listing users), `404`
(unknown product / user / order), `402` (declined card), `409` (out of stock),
`500` (payment gateway), plus slow payment calls — a diverse spread for testing
dashboards, filters, and alerts.
