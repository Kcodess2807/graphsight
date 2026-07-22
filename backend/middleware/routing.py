"""API Gateway simulation — enforce Org -> Pod routing in-process.

In production a stateless gateway maps org_id -> Pod_IP from the PodAssignment
table and forwards the request to the right pod. Here we simulate that decision
*inside* the pod: before a tenant-scoped request runs, verify THIS pod (config.POD_ID)
is the one assigned to serve the request's org and that its graph is loaded
(load_status == 'ready'). The four outcomes mirror how the real gateway behaves:

  ready-here   -> pass through (this pod owns the org)
  pulling-here -> 503, still warming (gateway would hold / retry)
  ready-elsewhere -> 421 Misdirected Request (gateway would forward to that pod)
  unassigned   -> 409 (no pod owns this org yet — scheduler hasn't placed it)

No-op entirely when MULTI_TENANCY_ENABLED is off, so single-tenant/dev is untouched.
Anomalies are logged and forwarded to Sentry via the shared auth reporter.
"""

import logging

from sqlmodel import Session, select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

import auth
from models.control_plane import LoadStatus, PodAssignment, get_control_plane_engine
from tracerag import config

logger = logging.getLogger("tracerag.routing")

# Endpoints that read/serve a tenant's graph. Others (health, graph list, the
# open /mcp demo surface, docs) are not gated.
TENANT_SCOPED_PREFIXES = ("/api/trace", "/api/subgraph", "/api/suggestions")

# assignment verdicts
_READY_HERE = "ready_here"
_PULLING_HERE = "pulling_here"
_READY_ELSEWHERE = "ready_elsewhere"
_UNASSIGNED = "unassigned"


def assignment_status(
    org_id: str, *, pod_id: str | None = None, engine=None
) -> tuple[str, dict]:
    """Classify how ``org_id`` is placed relative to this pod. Pure lookup — used
    by the middleware and directly unit-testable."""
    pod_id = pod_id or config.POD_ID
    engine = engine or get_control_plane_engine()
    with Session(engine) as db:
        rows = db.exec(
            select(PodAssignment).where(PodAssignment.org_id == org_id)
        ).all()

    mine = next((r for r in rows if r.pod_id == pod_id), None)
    if mine is not None:
        if mine.load_status == LoadStatus.READY:
            return _READY_HERE, {"pod_id": pod_id}
        return _PULLING_HERE, {"pod_id": pod_id, "load_status": mine.load_status}

    ready_other = next((r for r in rows if r.load_status == LoadStatus.READY), None)
    target = ready_other or (rows[0] if rows else None)
    if target is not None:
        return _READY_ELSEWHERE, {"pod_id": target.pod_id,
                                  "load_status": target.load_status}
    return _UNASSIGNED, {}


class TenantRoutingMiddleware(BaseHTTPMiddleware):
    """Gate tenant-scoped routes on this pod's PodAssignment, simulating the
    gateway's Org -> Pod decision."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # single-tenant / dev, non-tenant routes, and CORS preflight all pass.
        if not config.MULTI_TENANCY_ENABLED:
            return await call_next(request)
        if request.method == "OPTIONS":
            return await call_next(request)
        if not request.url.path.startswith(TENANT_SCOPED_PREFIXES):
            return await call_next(request)

        # 1) authenticate -> org
        token = _bearer(request.headers.get("authorization"))
        org_id = auth.resolve_org_from_token(token)
        if not org_id:
            return JSONResponse({"detail": "Invalid or revoked API key."},
                                status_code=401,
                                headers={"WWW-Authenticate": "Bearer"})

        # 2) is THIS pod assigned + ready to serve that org?
        try:
            verdict, detail = assignment_status(org_id)
        except Exception as exc:  # noqa: BLE001 — control-plane unreachable
            auth._report_anomaly("assignment_lookup_failed", org_id=org_id, error=str(exc))
            return JSONResponse({"detail": "Routing unavailable."}, status_code=503)

        if verdict == _READY_HERE:
            # stash so downstream deps (get_current_tenant_org, MCP) skip re-auth
            request.state.org_id = org_id
            auth.set_current_org(org_id)
            return await call_next(request)

        if verdict == _PULLING_HERE:
            auth._report_anomaly("tenant_not_ready", org_id=org_id, **detail)
            return JSONResponse(
                {"detail": "Tenant graph is still loading on this pod; retry shortly.",
                 "org_id": org_id},
                status_code=503, headers={"Retry-After": "5"},
            )

        if verdict == _READY_ELSEWHERE:
            # The real gateway would forward to detail['pod_id']. We surface a 421
            # Misdirected Request — the honest "you reached the wrong pod" signal —
            # and advertise the correct pod so a client/gateway can re-route.
            auth._report_anomaly("misdirected_request", org_id=org_id,
                                 this_pod=config.POD_ID, assigned_pod=detail.get("pod_id"))
            return JSONResponse(
                {"detail": "This org is served by a different pod.",
                 "org_id": org_id, "assigned_pod": detail.get("pod_id")},
                status_code=421,
                headers={"X-TraceRAG-Assigned-Pod": str(detail.get("pod_id"))},
            )

        # unassigned: no pod owns this org yet
        auth._report_anomaly("tenant_unassigned", org_id=org_id)
        return JSONResponse(
            {"detail": "No pod is serving this org yet.", "org_id": org_id},
            status_code=409,
        )


def _bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    return token if scheme.lower() == "bearer" and token else None
