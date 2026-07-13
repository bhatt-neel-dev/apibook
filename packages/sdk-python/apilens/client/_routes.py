"""Endpoint route-template resolution.

Raw request paths (``/product/123``, ``/product/324``) must collapse to one
logical endpoint (``/product/{id}``) or every id becomes its own endpoint and
the analytics are useless.

The accurate way — and what we do first — is to ask the web framework for the
*matched route template*. Every supported framework knows it (that's how it
dispatched the request):

  * Starlette / FastAPI → match ``scope["app"].routes`` → ``route.path``
  * Litestar           → ``scope["route_handler"]`` ownership layers
  * BlackSheep         → route pattern stashed on the scope by the adapter
  * Flask              → ``url_map.bind_to_environ(environ).match(return_rule=True)``
  * Django             → ``request.resolver_match.route``

When the framework can't give a template (an unmatched URL, a raw ASGI app, a
route we can't introspect) we fall back to a conservative heuristic that
parametrizes id-looking segments. The heuristic is *only* a safety net — the
framework template always wins.

Set ``APILENS_PARAMETRIZE_PATHS=false`` (or ``parametrize_paths=False`` on the
middleware) to disable the heuristic fallback and keep raw paths when no
template is available.
"""

from __future__ import annotations

import contextvars
import os
import re
from typing import Any, Optional


# ── Heuristic fallback ──────────────────────────────────────────────────────
# Applied per path segment, only when the framework gave us no template.

_INT_RE = re.compile(r"^\d+$")
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
# Crockford base32, 26 chars (ULID / KSUID-like).
_ULID_RE = re.compile(r"^[0-7][0-9A-HJKMNP-TV-Za-hjkmnp-tv-z]{25}$")
# Long pure-hex: Mongo ObjectId (24), SHA-1 (40), SHA-256 (64), etc.
_HEX_RE = re.compile(r"^[0-9a-fA-F]{24,}$")
# Mixed alphanumeric token that CONTAINS a digit and is long — API keys, nano
# ids, encoded ids, slug-ids. Requiring a digit keeps ordinary words
# (``settings``, ``openapi``) intact.
_MIXED_ID_RE = re.compile(r"^(?=[A-Za-z0-9._~-]*\d)[A-Za-z0-9._~-]{16,}$")


def _segment_placeholder(seg: str) -> Optional[str]:
    """Return the placeholder for an id-looking segment, else ``None``."""
    if _INT_RE.match(seg):
        return "{id}"
    if _UUID_RE.match(seg):
        return "{uuid}"
    if _ULID_RE.match(seg):
        return "{id}"
    if _HEX_RE.match(seg):
        return "{hash}"
    if _MIXED_ID_RE.match(seg):
        # Don't parametrize a segment whose "digit" is only inside a file
        # extension (e.g. ``report.p12`` stays, but ``a1b2c3…16chars`` goes).
        return "{id}"
    return None


def parametrize_path(path: str) -> str:
    """Heuristically replace id-looking path segments with placeholders.

    Conservative by design — this only runs as a fallback when the framework
    can't supply a real route template, so a few false positives are far better
    than exploding one endpoint into thousands.
    """
    if not path or path == "/":
        return path or "/"
    out: list[str] = []
    for seg in path.split("/"):
        if not seg:
            out.append(seg)
            continue
        placeholder = _segment_placeholder(seg)
        out.append(placeholder if placeholder is not None else seg)
    return "/".join(out)


def parametrize_enabled() -> bool:
    """Env kill-switch for the heuristic fallback (env wins over code)."""
    raw = os.environ.get("APILENS_PARAMETRIZE_PATHS")
    if raw is None:
        return True
    return raw.strip().lower() not in {"0", "false", "no", "off"}


# ── Starlette / FastAPI ─────────────────────────────────────────────────────


def starlette_route_template(scope: dict) -> Optional[str]:
    """Route template for a Starlette/FastAPI request, matched from the scope.

    Mirrors apitally: prefer FastAPI's resolved route context when present,
    otherwise walk ``app.routes`` (recursing Mounts) and return the template of
    the fully-matched route. ``None`` if nothing matched.
    """
    if scope.get("type") != "http":
        return None
    # FastAPI 0.138+ stashes the resolved route on the scope.
    route_context = (scope.get("fastapi") or {}).get("effective_route_context")
    ctx_path = getattr(route_context, "path", None)
    if ctx_path:
        return (scope.get("root_path", "") or "") + ctx_path

    app = scope.get("app")
    routes = getattr(app, "routes", None)
    if routes is None:
        return None
    try:
        from starlette.routing import Match
    except Exception:
        return None
    return _match_starlette_routes(routes, scope, Match.FULL)


def _match_starlette_routes(routes: Any, scope: dict, full: Any) -> Optional[str]:
    root_path = scope.get("root_path", "") or ""
    for route in routes:
        sub = getattr(route, "routes", None)
        if sub:
            inner = _match_starlette_routes(sub, scope, full)
            if inner is not None:
                return inner
        elif hasattr(route, "path"):
            try:
                match, _ = route.matches(scope)
            except Exception:
                continue
            if match == full:
                return root_path + route.path
    return None


# ── Litestar ────────────────────────────────────────────────────────────────


def litestar_route_template(scope: dict) -> Optional[str]:
    """Route template for a Litestar request from ``scope["route_handler"]``."""
    handler = scope.get("route_handler")
    if handler is None:
        return None
    # Fast path: Litestar records the matched template on the scope.
    tmpl = scope.get("path_template")
    if tmpl:
        return tmpl
    paths = getattr(handler, "paths", None)
    if not paths:
        return None
    try:
        from litestar.handlers import HTTPRouteHandler
    except Exception:
        HTTPRouteHandler = None  # type: ignore[assignment]

    layers = getattr(handler, "ownership_layers", None)
    if not layers:
        first = next(iter(paths), None)
        return first if first else None

    parts: list[str] = []
    for layer in layers:
        layer_paths = getattr(layer, "paths", None)
        if HTTPRouteHandler is not None and isinstance(layer, HTTPRouteHandler):
            if not layer_paths:
                return None
            parts.append(next(iter(layer_paths)).lstrip("/"))
        elif layer_paths:
            parts.append(next(iter(layer_paths)).lstrip("/"))
        else:
            parts.append(str(getattr(layer, "path", "")).lstrip("/"))
    return "/" + "/".join(p for p in parts if p)


# ── BlackSheep ──────────────────────────────────────────────────────────────
#
# BlackSheep only reveals the matched pattern inside ``router.get_match``, which
# receives a Request — not the ASGI scope our middleware holds. We bridge the
# two with a contextvar: the adapter's wrapped get_match records the pattern
# during handling (same task/context as the middleware), and the resolver reads
# it back in the middleware's finally. Per-request tasks keep contexts isolated.

_blacksheep_pattern: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "apilens_blacksheep_route", default=None
)


def blacksheep_set_route_pattern(pattern: Optional[str]) -> None:
    # "*" is BlackSheep's unmatched sentinel (since v2.4.4).
    _blacksheep_pattern.set(pattern if pattern and pattern != "*" else None)


def blacksheep_route_template(scope: dict) -> Optional[str]:
    return _blacksheep_pattern.get()


# ── Flask (WSGI) ────────────────────────────────────────────────────────────

_FLASK_RULE_RE = re.compile(r"<(?:[^:<>]+:)?([^<>]+)>")


def _transform_flask_rule(rule: str) -> str:
    """``/product/<int:id>`` → ``/product/{id}`` (drop the converter prefix)."""
    return _FLASK_RULE_RE.sub(lambda m: "{" + m.group(1) + "}", rule)


def flask_route_template(flask_app: Any, environ: dict) -> Optional[str]:
    """Route template for a Flask/Werkzeug request via the app's url_map."""
    url_map = getattr(flask_app, "url_map", None)
    if url_map is None:
        return None
    try:
        adapter = url_map.bind_to_environ(environ)
        rule, _args = adapter.match(return_rule=True)
    except Exception:
        # NotFound / MethodNotAllowed / RequestRedirect → no stable template.
        return None
    rule_str = getattr(rule, "rule", None)
    if not rule_str:
        return None
    return _transform_flask_rule(rule_str)


# ── Django ──────────────────────────────────────────────────────────────────

# path()-style converters: <int:pk> / <pk> / <slug:name>  →  {pk} / {name}
_DJANGO_CONVERTER_RE = re.compile(r"<(?:[^:<>]+:)?([^<>]+)>")
# re_path()-style named groups: (?P<pk>\d+)  →  {pk}
_DJANGO_NAMED_GROUP_RE = re.compile(r"\(\?P<([^>]+)>[^)]*\)")


def _transform_django_route(route: str) -> str:
    # re_path named groups first — their `<name>` would otherwise be eaten by
    # the path()-converter rule below.
    path = _DJANGO_NAMED_GROUP_RE.sub(lambda m: "{" + m.group(1) + "}", route)
    path = _DJANGO_CONVERTER_RE.sub(lambda m: "{" + m.group(1) + "}", path)
    # Strip leftover regex anchors so a re_path template reads cleanly.
    path = path.replace("^", "").replace("$", "")
    if not path.startswith("/"):
        path = "/" + path
    return path


def django_route_template(request: Any) -> Optional[str]:
    """Route template from Django's URL resolver (covers django-ninja too)."""
    match = getattr(request, "resolver_match", None)
    if match is None:
        return None
    route = getattr(match, "route", None)
    if not route:
        return None
    return _transform_django_route(route)


def resolve_endpoint_path(
    template: Optional[str],
    raw_path: str,
    parametrize: bool = True,
) -> str:
    """Pick the endpoint (grouping) path: template → heuristic → raw.

    ``raw_path`` is always kept separately by callers for request logs; this
    only decides the value endpoints are aggregated under.
    """
    if template:
        return template
    if parametrize and parametrize_enabled():
        return parametrize_path(raw_path)
    return raw_path
