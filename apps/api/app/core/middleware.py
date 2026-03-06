from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get("x-correlation-id") or request.headers.get("x-request-id")
        if not correlation_id:
            correlation_id = request.scope.get("trace_id") or request.state.__dict__.get("_id") or "local-request"
        request.state.correlation_id = str(correlation_id)
        response = await call_next(request)
        response.headers["x-correlation-id"] = str(correlation_id)
        return response
