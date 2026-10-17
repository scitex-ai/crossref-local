"""Request middleware for CrossRef Local API."""

try:
    from fastapi import Request
    from starlette.middleware.base import BaseHTTPMiddleware
except ImportError:  # fastapi/starlette absent — imported only under SERVER_AVAILABLE
    Request = None  # type: ignore[assignment]
    BaseHTTPMiddleware = object  # type: ignore[assignment]


class UserContextMiddleware(BaseHTTPMiddleware):
    """Extract X-User-ID header for multi-tenant collection scoping.

    When requests come through scitex-cloud gateway, it passes the
    authenticated user's ID via X-User-ID header. This middleware
    extracts it and makes it available via request.state.user_id.

    Usage in endpoints:
        @app.get("/collections")
        def list_collections(request: Request):
            user_id = request.state.user_id  # None for local, set for cloud
            ...
    """

    async def dispatch(self, request: Request, call_next):
        # Extract user ID from header (passed by scitex-cloud gateway)
        request.state.user_id = request.headers.get("X-User-ID")
        response = await call_next(request)
        return response
