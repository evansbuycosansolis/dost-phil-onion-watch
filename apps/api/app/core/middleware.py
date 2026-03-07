from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from time import perf_counter
from uuid import uuid4

from app.services.observability_service import get_observability_store


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get("x-correlation-id") or request.headers.get("x-request-id")
        if not correlation_id:
            correlation_id = request.scope.get("trace_id") or request.state.__dict__.get("_id") or f"req-{uuid4().hex[:16]}"
        request.state.correlation_id = str(correlation_id)
        started = perf_counter()
        status_code = 500
        route_path = request.url.path
        response = None
        try:
            response = await call_next(request)
            status_code = response.status_code
        finally:
            route = request.scope.get("route")
            if route is not None and getattr(route, "path", None):
                route_path = str(route.path)
            duration_ms = (perf_counter() - started) * 1000.0
            get_observability_store().record_api_request(
                method=request.method,
                path=route_path,
                status_code=status_code,
                duration_ms=duration_ms,
                correlation_id=str(correlation_id),
            )
        if response is not None:
            response.headers["x-correlation-id"] = str(correlation_id)
            return response
        raise RuntimeError("Request pipeline did not return a response")
