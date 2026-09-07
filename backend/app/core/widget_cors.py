from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


WIDGET_API_PREFIX = "/api/widget/"
WIDGET_CORS_METHODS = "GET, POST, OPTIONS"
WIDGET_CORS_HEADERS = "Accept, Content-Type"


class WidgetCORSMiddleware(BaseHTTPMiddleware):
    """Add narrow CORS support for the origin-validated widget API.

    Authorization remains in the widget routes and service layer. This
    middleware only makes successful and controlled error responses readable
    to a browser after a cross-origin request. It never uses a wildcard.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if not request.url.path.startswith(WIDGET_API_PREFIX):
            return await call_next(request)

        origin = request.headers.get("origin")
        if request.method == "OPTIONS":
            return self._preflight_response(origin)

        response = await call_next(request)
        if origin:
            self._add_cors_headers(response, origin)

        return response

    @staticmethod
    def _preflight_response(origin: str | None) -> Response:
        if not origin:
            return Response(status_code=400)

        response = Response(status_code=204)
        WidgetCORSMiddleware._add_cors_headers(response, origin)
        response.headers["Access-Control-Allow-Methods"] = WIDGET_CORS_METHODS
        response.headers["Access-Control-Allow-Headers"] = WIDGET_CORS_HEADERS
        response.headers["Access-Control-Max-Age"] = "600"
        return response

    @staticmethod
    def _add_cors_headers(response: Response, origin: str) -> None:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
