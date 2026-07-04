from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class WeightedValue:
    value: str
    weight: float


@dataclass(frozen=True)
class LatencyProfile:
    base_ms: float
    jitter_ms: float
    tail_ms: float
    error_multiplier: float = 1.8


@dataclass(frozen=True)
class EndpointTemplate:
    method: str
    path: str
    description: str
    weight: float
    status_weights: tuple[tuple[int, float], ...]
    latency: LatencyProfile
    payload_kind: str
    service_name: str


@dataclass(frozen=True)
class ConsumerSegment:
    key: str
    name: str
    group: str
    weight: float
    user_agents: tuple[str, ...]
    base_error_rate: float = 0.0
    latency_multiplier: float = 1.0


@dataclass(frozen=True)
class AppProfile:
    slug: str
    name: str
    framework: str
    description: str
    icon: str
    weight: float
    base_urls: tuple[str, ...]


@dataclass(frozen=True)
class IncidentProfile:
    key: str
    description: str
    path_contains: tuple[str, ...]
    status_code: int
    start_ratio: float
    end_ratio: float
    extra_error_rate: float
    latency_multiplier: float
    environments: tuple[str, ...] = ("production",)


@dataclass(frozen=True)
class ScenarioProfile:
    key: str
    name: str
    industry: str
    description: str
    product_signal: str
    traffic_weight: float
    apps: tuple[AppProfile, ...]
    endpoints: tuple[EndpointTemplate, ...]
    consumers: tuple[ConsumerSegment, ...]
    environments: tuple[WeightedValue, ...]
    regions: tuple[WeightedValue, ...]
    incidents: tuple[IncidentProfile, ...] = ()


COMMON_CONSUMERS: tuple[ConsumerSegment, ...] = (
    ConsumerSegment(
        key="free_developer",
        name="Free Developer",
        group="free",
        weight=18,
        user_agents=("curl/8.6", "postman-runtime/7.39", "apilens-js-demo/1.0"),
        base_error_rate=0.015,
        latency_multiplier=1.0,
    ),
    ConsumerSegment(
        key="pro_team",
        name="Pro Team",
        group="pro",
        weight=24,
        user_agents=("api-client-node/3.4", "python-requests/2.32", "go-http-client/1.1"),
        base_error_rate=0.008,
        latency_multiplier=0.96,
    ),
    ConsumerSegment(
        key="enterprise",
        name="Enterprise Account",
        group="enterprise",
        weight=20,
        user_agents=("enterprise-gateway/5.8", "java-sdk/4.2", "apilens-enterprise-proxy/2.1"),
        base_error_rate=0.004,
        latency_multiplier=0.9,
    ),
    ConsumerSegment(
        key="partner_integration",
        name="Partner Integration",
        group="partner",
        weight=14,
        user_agents=("partner-sync/6.2", "zapier-hook/1.0", "workato-connector/3.7"),
        base_error_rate=0.012,
        latency_multiplier=1.08,
    ),
    ConsumerSegment(
        key="internal_service",
        name="Internal Service",
        group="internal",
        weight=12,
        user_agents=("billing-worker/2.3", "backoffice-job/1.9", "internal-dashboard/0.12"),
        base_error_rate=0.006,
        latency_multiplier=0.86,
    ),
    ConsumerSegment(
        key="trial_tenant",
        name="Trial Tenant",
        group="trial",
        weight=8,
        user_agents=("sandbox-client/0.9", "api-explorer/1.4", "insomnia/9.2"),
        base_error_rate=0.024,
        latency_multiplier=1.14,
    ),
    ConsumerSegment(
        key="automation_bot",
        name="Automation Bot",
        group="automation",
        weight=4,
        user_agents=("uptime-checker/1.7", "load-verifier/0.8", "synthetic-monitor/2.5"),
        base_error_rate=0.01,
        latency_multiplier=0.8,
    ),
)


COMMON_ENVIRONMENTS: tuple[WeightedValue, ...] = (
    WeightedValue("production", 72),
    WeightedValue("staging", 18),
    WeightedValue("development", 10),
)


COMMON_REGIONS: tuple[WeightedValue, ...] = (
    WeightedValue("us-east-1", 30),
    WeightedValue("us-west-2", 18),
    WeightedValue("eu-west-1", 20),
    WeightedValue("ap-south-1", 18),
    WeightedValue("ap-southeast-1", 14),
)


def _statuses(*items: tuple[int, float]) -> tuple[tuple[int, float], ...]:
    return tuple(items)


def _endpoint(
    method: str,
    path: str,
    description: str,
    weight: float,
    statuses: tuple[tuple[int, float], ...],
    base: float,
    jitter: float,
    tail: float,
    payload: str,
    service: str,
) -> EndpointTemplate:
    return EndpointTemplate(
        method=method,
        path=path,
        description=description,
        weight=weight,
        status_weights=statuses,
        latency=LatencyProfile(base, jitter, tail),
        payload_kind=payload,
        service_name=service,
    )


SCENARIOS: dict[str, ScenarioProfile] = {
    "api_product_growth": ScenarioProfile(
        key="api_product_growth",
        name="API Product Growth",
        industry="API product / developer platform",
        description="Developer-facing API usage with plans, quotas, SDKs, onboarding, and customer adoption analysis.",
        product_signal=(
            "Inspired by competitor-visible product analytics patterns such as API usage, customer segments, "
            "quotas, billing, and developer experience."
        ),
        traffic_weight=12,
        apps=(
            AppProfile(
                slug="developer-platform",
                name="Developer Platform API",
                framework="fastapi",
                description="Public API for developers, API keys, plans, and usage dashboards.",
                icon="API",
                weight=70,
                base_urls=("https://api.dev-platform.example", "https://sandbox.dev-platform.example"),
            ),
            AppProfile(
                slug="billing-metering",
                name="Billing Metering API",
                framework="django",
                description="Usage metering, quota checks, invoices, and prepaid credit ledgers.",
                icon="$",
                weight=30,
                base_urls=("https://billing.dev-platform.example",),
            ),
        ),
        endpoints=(
            _endpoint("GET", "/v1/apps", "List registered applications.", 9, _statuses((200, 95), (401, 2), (500, 3)), 42, 58, 260, "app", "platform-api"),
            _endpoint("POST", "/v1/api-keys", "Create scoped API keys.", 4, _statuses((201, 82), (400, 6), (409, 5), (429, 3), (500, 4)), 84, 92, 420, "api_key", "platform-api"),
            _endpoint("GET", "/v1/usage", "Fetch usage metrics by consumer.", 13, _statuses((200, 92), (400, 4), (429, 2), (503, 2)), 118, 160, 780, "usage", "analytics-api"),
            _endpoint("POST", "/v1/events", "Ingest product events.", 18, _statuses((202, 94), (400, 3), (413, 1), (503, 2)), 48, 82, 360, "event", "events-api"),
            _endpoint("GET", "/v1/plans/{plan_id}", "Read a pricing plan.", 5, _statuses((200, 91), (404, 6), (500, 3)), 34, 38, 180, "plan", "billing-api"),
            _endpoint("POST", "/v1/quotas/check", "Check quota and entitlement.", 16, _statuses((200, 90), (402, 2), (403, 2), (429, 4), (503, 2)), 52, 70, 330, "quota", "billing-api"),
            _endpoint("POST", "/v1/webhooks/test", "Send a webhook test event.", 4, _statuses((202, 84), (400, 5), (422, 5), (502, 4), (504, 2)), 180, 260, 1400, "webhook", "webhook-worker"),
        ),
        consumers=COMMON_CONSUMERS,
        environments=COMMON_ENVIRONMENTS,
        regions=COMMON_REGIONS,
        incidents=(
            IncidentProfile("quota-cache-miss", "Quota cache miss increases latency near the middle of the range.", ("quotas",), 503, 0.42, 0.50, 0.08, 2.6),
        ),
    ),
    "ecommerce_checkout": ScenarioProfile(
        key="ecommerce_checkout",
        name="Commerce Checkout",
        industry="E-commerce / retail",
        description="Cart, checkout, promotions, fulfillment, and payment API behavior for a retail platform.",
        product_signal="Captures high-cardinality consumer traffic, conversion-critical latency, and payment failures.",
        traffic_weight=14,
        apps=(
            AppProfile("storefront-api", "Storefront API", "express", "Customer-facing catalog, cart, and checkout API.", "CRT", 60, ("https://api.shop.example",)),
            AppProfile("fulfillment-api", "Fulfillment API", "django", "Inventory, shipment, and order lifecycle service.", "BOX", 25, ("https://fulfillment.shop.example",)),
            AppProfile("payment-edge", "Payment Edge API", "fastapi", "Payment orchestration and fraud checks.", "PAY", 15, ("https://payments.shop.example",)),
        ),
        endpoints=(
            _endpoint("GET", "/v1/products", "Browse catalog products.", 18, _statuses((200, 96), (400, 1), (404, 1), (500, 2)), 46, 70, 300, "catalog", "storefront"),
            _endpoint("GET", "/v1/products/{product_id}", "Read product detail.", 14, _statuses((200, 92), (404, 6), (500, 2)), 38, 54, 220, "catalog", "storefront"),
            _endpoint("POST", "/v1/carts", "Create cart.", 7, _statuses((201, 92), (400, 4), (409, 2), (500, 2)), 64, 80, 360, "cart", "cart"),
            _endpoint("PATCH", "/v1/carts/{cart_id}", "Update cart lines.", 11, _statuses((200, 86), (400, 5), (409, 5), (422, 2), (503, 2)), 78, 110, 520, "cart", "cart"),
            _endpoint("POST", "/v1/checkout", "Submit checkout.", 10, _statuses((201, 82), (400, 6), (402, 4), (409, 4), (503, 4)), 210, 280, 1650, "checkout", "checkout"),
            _endpoint("POST", "/v1/payments/authorize", "Authorize a card payment.", 8, _statuses((200, 84), (400, 4), (402, 6), (429, 2), (502, 2), (504, 2)), 260, 340, 2200, "payment", "payments"),
            _endpoint("GET", "/v1/orders/{order_id}", "Read order status.", 9, _statuses((200, 92), (404, 5), (500, 3)), 58, 90, 380, "order", "orders"),
            _endpoint("POST", "/v1/webhooks/carrier", "Receive carrier webhook.", 4, _statuses((202, 90), (400, 5), (409, 3), (500, 2)), 82, 100, 460, "shipment", "fulfillment"),
        ),
        consumers=COMMON_CONSUMERS,
        environments=COMMON_ENVIRONMENTS,
        regions=COMMON_REGIONS,
        incidents=(
            IncidentProfile("payment-provider-timeout", "External payment provider intermittently times out.", ("payments", "checkout"), 504, 0.64, 0.72, 0.14, 3.2),
            IncidentProfile("inventory-contention", "Inventory writes return conflicts during a launch window.", ("carts", "checkout"), 409, 0.30, 0.36, 0.10, 1.8),
        ),
    ),
    "fintech_payments": ScenarioProfile(
        key="fintech_payments",
        name="Fintech Payments",
        industry="Financial technology",
        description="Payment initiation, ledger, KYC, payouts, risk scoring, and webhook workloads.",
        product_signal="Covers regulated customer segments, high-value endpoints, retries, auth failures, and audit-style traces.",
        traffic_weight=12,
        apps=(
            AppProfile("payment-core", "Payment Core API", "fastapi", "Payment lifecycle and authorization service.", "FIN", 55, ("https://api.payments.example",)),
            AppProfile("risk-screening", "Risk Screening API", "django", "Fraud, sanctions, and transaction risk scoring.", "RSK", 25, ("https://risk.payments.example",)),
            AppProfile("ledger-api", "Ledger API", "django", "Immutable ledger and reconciliation API.", "LED", 20, ("https://ledger.payments.example",)),
        ),
        endpoints=(
            _endpoint("POST", "/v1/payments", "Create payment instruction.", 16, _statuses((201, 82), (400, 5), (401, 2), (402, 3), (409, 3), (422, 2), (503, 3)), 180, 240, 1400, "payment", "payments"),
            _endpoint("GET", "/v1/payments/{payment_id}", "Fetch payment status.", 14, _statuses((200, 91), (404, 5), (429, 2), (500, 2)), 70, 110, 460, "payment", "payments"),
            _endpoint("POST", "/v1/kyc/verifications", "Start KYC verification.", 5, _statuses((202, 80), (400, 6), (409, 5), (422, 5), (503, 4)), 260, 320, 1800, "kyc", "kyc"),
            _endpoint("POST", "/v1/risk/score", "Score transaction risk.", 12, _statuses((200, 88), (400, 4), (429, 3), (502, 3), (504, 2)), 190, 260, 1700, "risk", "risk"),
            _endpoint("GET", "/v1/ledger/entries", "List ledger entries.", 8, _statuses((200, 94), (400, 2), (500, 4)), 132, 180, 900, "ledger", "ledger"),
            _endpoint("POST", "/v1/payouts", "Create payout.", 6, _statuses((201, 82), (400, 5), (403, 3), (409, 5), (503, 5)), 220, 300, 1600, "payout", "payouts"),
            _endpoint("POST", "/v1/webhooks/bank-events", "Receive bank event webhook.", 9, _statuses((202, 90), (400, 5), (409, 3), (500, 2)), 86, 130, 520, "webhook", "webhooks"),
        ),
        consumers=COMMON_CONSUMERS,
        environments=COMMON_ENVIRONMENTS,
        regions=COMMON_REGIONS,
        incidents=(
            IncidentProfile("risk-provider-degradation", "Risk provider degradation increases 502s and tail latency.", ("risk",), 502, 0.54, 0.62, 0.16, 3.8),
        ),
    ),
    "healthtech_patient": ScenarioProfile(
        key="healthtech_patient",
        name="Healthtech Patient Platform",
        industry="Healthcare technology",
        description="Patient, appointment, claims, eligibility, and consent APIs using synthetic identifiers only.",
        product_signal="Models regulated traffic without real personal data by using tokenized test identifiers.",
        traffic_weight=10,
        apps=(
            AppProfile("patient-access", "Patient Access API", "django", "Patient portal and appointment APIs.", "HLT", 55, ("https://patient-api.health.example",)),
            AppProfile("claims-gateway", "Claims Gateway API", "fastapi", "Eligibility and claims integration layer.", "CLM", 45, ("https://claims.health.example",)),
        ),
        endpoints=(
            _endpoint("GET", "/v1/patients/{patient_token}", "Read synthetic patient summary.", 9, _statuses((200, 90), (401, 2), (403, 2), (404, 4), (500, 2)), 82, 120, 560, "patient", "patient-access"),
            _endpoint("GET", "/v1/appointments", "List appointments.", 11, _statuses((200, 94), (400, 2), (500, 4)), 76, 100, 420, "appointment", "patient-access"),
            _endpoint("POST", "/v1/appointments", "Create appointment request.", 6, _statuses((201, 84), (400, 5), (409, 5), (422, 3), (503, 3)), 154, 210, 960, "appointment", "scheduling"),
            _endpoint("POST", "/v1/eligibility/checks", "Run insurance eligibility check.", 10, _statuses((200, 86), (400, 5), (409, 2), (502, 4), (504, 3)), 310, 380, 2300, "eligibility", "claims"),
            _endpoint("POST", "/v1/claims", "Submit claim.", 5, _statuses((202, 82), (400, 6), (409, 4), (422, 4), (503, 4)), 260, 340, 1800, "claim", "claims"),
            _endpoint("PATCH", "/v1/consents/{consent_id}", "Update consent.", 4, _statuses((200, 88), (400, 5), (403, 3), (404, 2), (500, 2)), 92, 130, 540, "consent", "consent"),
        ),
        consumers=COMMON_CONSUMERS,
        environments=COMMON_ENVIRONMENTS,
        regions=COMMON_REGIONS,
        incidents=(
            IncidentProfile("eligibility-clearinghouse-lag", "Eligibility clearinghouse lag causes timeouts.", ("eligibility",), 504, 0.18, 0.24, 0.18, 4.0),
        ),
    ),
    "logistics_fleet": ScenarioProfile(
        key="logistics_fleet",
        name="Logistics Fleet",
        industry="Logistics / supply chain",
        description="Shipment tracking, fleet telemetry, warehouse scans, and customer delivery APIs.",
        product_signal="Models high-volume device and partner integrations with bursty geographic activity.",
        traffic_weight=12,
        apps=(
            AppProfile("tracking-api", "Tracking API", "fastapi", "Customer and partner shipment tracking API.", "TRK", 50, ("https://tracking.logistics.example",)),
            AppProfile("fleet-ingest", "Fleet Ingest API", "starlette", "Vehicle and scanner event ingestion API.", "FLT", 35, ("https://fleet.logistics.example",)),
            AppProfile("warehouse-api", "Warehouse API", "django", "Inventory, picking, and scan operations.", "WH", 15, ("https://warehouse.logistics.example",)),
        ),
        endpoints=(
            _endpoint("GET", "/v1/shipments/{shipment_id}", "Read shipment detail.", 15, _statuses((200, 92), (404, 5), (429, 1), (500, 2)), 68, 96, 420, "shipment", "tracking"),
            _endpoint("GET", "/v1/shipments/{shipment_id}/events", "Read tracking events.", 12, _statuses((200, 93), (404, 4), (500, 3)), 92, 130, 620, "shipment", "tracking"),
            _endpoint("POST", "/v1/fleet/positions", "Ingest vehicle positions.", 19, _statuses((202, 95), (400, 2), (413, 1), (503, 2)), 42, 74, 280, "position", "fleet-ingest"),
            _endpoint("POST", "/v1/scans", "Ingest warehouse scan.", 14, _statuses((202, 92), (400, 3), (409, 3), (503, 2)), 54, 82, 330, "scan", "warehouse"),
            _endpoint("PATCH", "/v1/routes/{route_id}", "Update delivery route.", 6, _statuses((200, 84), (400, 5), (409, 7), (500, 4)), 150, 230, 1000, "route", "routing"),
            _endpoint("POST", "/v1/webhooks/customer-events", "Send customer delivery webhooks.", 5, _statuses((202, 88), (400, 4), (502, 4), (504, 4)), 180, 260, 1400, "webhook", "webhooks"),
        ),
        consumers=COMMON_CONSUMERS
        + (
            ConsumerSegment("iot_device", "Fleet Device", "iot", 28, ("vehicle-agent/3.2", "handheld-scanner/4.7", "edge-gateway/2.0"), 0.018, 1.18),
        ),
        environments=COMMON_ENVIRONMENTS,
        regions=COMMON_REGIONS,
        incidents=(
            IncidentProfile("warehouse-scan-duplicates", "Scan duplicates increase conflicts.", ("scans",), 409, 0.76, 0.84, 0.12, 1.5),
        ),
    ),
    "ai_platform": ScenarioProfile(
        key="ai_platform",
        name="AI Platform",
        industry="AI / machine learning infrastructure",
        description="Model inference, embeddings, vector search, token metering, and prompt safety APIs.",
        product_signal="Reflects API and AI product monetization patterns such as token counts, traces, quota checks, and heavy payloads.",
        traffic_weight=12,
        apps=(
            AppProfile("inference-api", "Inference API", "fastapi", "LLM and model inference API.", "AI", 55, ("https://inference.ai.example",)),
            AppProfile("vector-api", "Vector API", "starlette", "Embeddings and vector search API.", "VEC", 25, ("https://vectors.ai.example",)),
            AppProfile("ai-metering", "AI Metering API", "django", "Token and credit metering service.", "TOK", 20, ("https://metering.ai.example",)),
        ),
        endpoints=(
            _endpoint("POST", "/v1/chat/completions", "Generate chat completion.", 15, _statuses((200, 86), (400, 4), (401, 1), (429, 5), (500, 2), (503, 2)), 620, 900, 5200, "completion", "inference"),
            _endpoint("POST", "/v1/embeddings", "Generate embedding vectors.", 13, _statuses((200, 90), (400, 4), (413, 2), (429, 2), (503, 2)), 220, 360, 2100, "embedding", "embedding"),
            _endpoint("POST", "/v1/vector/search", "Search vector index.", 11, _statuses((200, 90), (400, 3), (404, 2), (500, 3), (503, 2)), 150, 240, 1300, "vector_search", "vector"),
            _endpoint("POST", "/v1/safety/moderations", "Run prompt moderation.", 6, _statuses((200, 91), (400, 3), (429, 3), (503, 3)), 110, 170, 900, "moderation", "safety"),
            _endpoint("POST", "/v1/tokens/meter", "Record token usage.", 16, _statuses((202, 95), (400, 2), (409, 1), (503, 2)), 45, 64, 240, "token_meter", "metering"),
            _endpoint("GET", "/v1/models", "List available models.", 7, _statuses((200, 96), (401, 1), (500, 3)), 42, 56, 210, "model", "inference"),
        ),
        consumers=COMMON_CONSUMERS,
        environments=COMMON_ENVIRONMENTS,
        regions=COMMON_REGIONS,
        incidents=(
            IncidentProfile("model-capacity-429", "Model capacity pushes quota and rate-limit responses.", ("chat", "embeddings"), 429, 0.58, 0.68, 0.18, 2.4),
        ),
    ),
    "telco_iot": ScenarioProfile(
        key="telco_iot",
        name="Telco IoT",
        industry="Telecommunications / IoT",
        description="SIM lifecycle, device telemetry, usage counters, and network policy APIs.",
        product_signal="Models large-scale device traffic and operational dashboards for billions-style API estates.",
        traffic_weight=10,
        apps=(
            AppProfile("device-api", "Device API", "fastapi", "Device registration and lifecycle API.", "SIM", 45, ("https://devices.telco.example",)),
            AppProfile("usage-api", "Usage API", "django", "Data usage and billing counter API.", "GB", 35, ("https://usage.telco.example",)),
            AppProfile("network-policy", "Network Policy API", "starlette", "Policy and provisioning API.", "NET", 20, ("https://network.telco.example",)),
        ),
        endpoints=(
            _endpoint("POST", "/v1/devices/register", "Register device.", 8, _statuses((201, 88), (400, 5), (409, 4), (503, 3)), 96, 130, 620, "device", "device"),
            _endpoint("GET", "/v1/devices/{device_id}", "Read device.", 13, _statuses((200, 92), (404, 5), (500, 3)), 50, 72, 300, "device", "device"),
            _endpoint("POST", "/v1/telemetry", "Ingest device telemetry.", 22, _statuses((202, 96), (400, 2), (413, 1), (503, 1)), 34, 56, 210, "telemetry", "telemetry"),
            _endpoint("GET", "/v1/usage/{device_id}", "Read usage counters.", 14, _statuses((200, 92), (404, 4), (429, 2), (500, 2)), 72, 100, 440, "usage", "usage"),
            _endpoint("PATCH", "/v1/policies/{policy_id}", "Update network policy.", 5, _statuses((200, 85), (400, 5), (403, 3), (409, 4), (503, 3)), 130, 180, 900, "policy", "network-policy"),
        ),
        consumers=COMMON_CONSUMERS
        + (
            ConsumerSegment("iot_device", "IoT Device", "iot", 42, ("iot-modem/7.2", "edge-router/5.0", "sim-agent/2.4"), 0.02, 1.1),
        ),
        environments=COMMON_ENVIRONMENTS,
        regions=COMMON_REGIONS,
        incidents=(
            IncidentProfile("telemetry-burst", "Regional device reconnect burst creates ingestion pressure.", ("telemetry",), 503, 0.10, 0.16, 0.10, 2.2),
        ),
    ),
    "internal_saas": ScenarioProfile(
        key="internal_saas",
        name="Internal SaaS Operations",
        industry="B2B SaaS / internal operations",
        description="Admin, CRM, billing, notifications, support, and audit APIs for internal teams.",
        product_signal="Creates data for RBAC, support debugging, audit-oriented logs, and operational workflows.",
        traffic_weight=9,
        apps=(
            AppProfile("admin-api", "Admin API", "django", "Tenant administration and settings API.", "ADM", 45, ("https://admin.saas.example",)),
            AppProfile("notification-api", "Notification API", "fastapi", "Email, SMS, webhook, and in-app notification API.", "NTF", 30, ("https://notify.saas.example",)),
            AppProfile("support-api", "Support API", "express", "Support workflow and ticket API.", "SUP", 25, ("https://support.saas.example",)),
        ),
        endpoints=(
            _endpoint("GET", "/v1/tenants", "List tenants.", 7, _statuses((200, 95), (401, 2), (500, 3)), 58, 82, 330, "tenant", "admin"),
            _endpoint("PATCH", "/v1/tenants/{tenant_id}/settings", "Update tenant settings.", 5, _statuses((200, 84), (400, 6), (403, 4), (409, 3), (500, 3)), 110, 160, 760, "settings", "admin"),
            _endpoint("POST", "/v1/notifications/email", "Send email notification.", 12, _statuses((202, 90), (400, 4), (429, 2), (502, 2), (504, 2)), 150, 230, 1300, "notification", "notifications"),
            _endpoint("POST", "/v1/notifications/webhook", "Send webhook notification.", 10, _statuses((202, 86), (400, 4), (429, 2), (502, 5), (504, 3)), 180, 260, 1600, "webhook", "notifications"),
            _endpoint("GET", "/v1/audit/events", "Read audit events.", 9, _statuses((200, 94), (400, 2), (500, 4)), 130, 190, 900, "audit", "audit"),
            _endpoint("POST", "/v1/support/tickets", "Create support ticket.", 5, _statuses((201, 90), (400, 4), (409, 2), (500, 4)), 96, 120, 520, "ticket", "support"),
        ),
        consumers=COMMON_CONSUMERS,
        environments=COMMON_ENVIRONMENTS,
        regions=COMMON_REGIONS,
        incidents=(
            IncidentProfile("webhook-destination-errors", "Webhook destinations return transient 502/504 responses.", ("webhook",), 502, 0.70, 0.80, 0.14, 2.8),
        ),
    ),
    "enterprise_governance": ScenarioProfile(
        key="enterprise_governance",
        name="Enterprise Governance",
        industry="Enterprise API platform",
        description="API catalog, OpenAPI linting, policy checks, runtime drift, and security review workflows.",
        product_signal="Aligned to enterprise API governance and runtime security patterns observed in competitor positioning.",
        traffic_weight=9,
        apps=(
            AppProfile("catalog-api", "API Catalog API", "django", "API catalog and spec inventory API.", "CAT", 40, ("https://catalog.enterprise.example",)),
            AppProfile("governance-api", "Governance API", "fastapi", "Design-time and runtime policy API.", "GOV", 35, ("https://governance.enterprise.example",)),
            AppProfile("security-api", "Security Review API", "fastapi", "Runtime security findings and audit API.", "SEC", 25, ("https://security.enterprise.example",)),
        ),
        endpoints=(
            _endpoint("POST", "/v1/specs/lint", "Lint OpenAPI spec.", 9, _statuses((200, 86), (400, 5), (422, 6), (500, 3)), 190, 260, 1600, "spec", "governance"),
            _endpoint("GET", "/v1/apis", "List APIs.", 11, _statuses((200, 95), (401, 2), (500, 3)), 74, 96, 400, "api_catalog", "catalog"),
            _endpoint("POST", "/v1/apis/{api_id}/reviews", "Start API review.", 5, _statuses((202, 84), (400, 4), (403, 4), (409, 4), (500, 4)), 170, 230, 1100, "review", "governance"),
            _endpoint("GET", "/v1/security/findings", "List security findings.", 8, _statuses((200, 93), (400, 3), (500, 4)), 140, 190, 900, "finding", "security"),
            _endpoint("POST", "/v1/runtime/drift", "Record runtime drift.", 12, _statuses((202, 92), (400, 4), (409, 2), (503, 2)), 66, 98, 420, "drift", "runtime"),
            _endpoint("PATCH", "/v1/policies/{policy_id}", "Update policy.", 4, _statuses((200, 84), (400, 5), (403, 5), (409, 3), (500, 3)), 118, 160, 780, "policy", "governance"),
        ),
        consumers=COMMON_CONSUMERS,
        environments=COMMON_ENVIRONMENTS,
        regions=COMMON_REGIONS,
        incidents=(
            IncidentProfile("spec-linter-overload", "Large spec lint jobs overload linter workers.", ("specs",), 503, 0.34, 0.40, 0.12, 3.1),
        ),
    ),
}


def list_scenarios() -> tuple[ScenarioProfile, ...]:
    return tuple(SCENARIOS.values())


def get_scenario(key: str) -> ScenarioProfile:
    normalized = (key or "").strip().lower()
    try:
        return SCENARIOS[normalized]
    except KeyError as exc:
        choices = ", ".join(sorted(SCENARIOS))
        raise ValueError(f"Unknown synthetic scenario '{key}'. Available scenarios: {choices}") from exc


def expand_scenario_keys(keys: Iterable[str] | None) -> tuple[str, ...]:
    requested = [k.strip().lower() for k in (keys or ()) if k and k.strip()]
    if not requested or "all" in requested:
        return tuple(SCENARIOS)
    unknown = [k for k in requested if k not in SCENARIOS]
    if unknown:
        choices = ", ".join(sorted(SCENARIOS))
        raise ValueError(f"Unknown synthetic scenario(s): {', '.join(unknown)}. Available scenarios: {choices}")
    return tuple(dict.fromkeys(requested))
