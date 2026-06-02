from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/meta", tags=["meta"])


@router.get("/openapi", include_in_schema=False)
def get_openapi_schema(request: Request) -> dict:
    """Expose the live OpenAPI schema under ``/api`` for the in-app API reference.

    FastAPI already serves the schema at ``/openapi.json``, but the Vite dev
    server only proxies ``/api`` to the backend, so that path is unreachable from
    the frontend during development. Re-exposing the same schema under ``/api``
    lets the API Docs page fetch it identically in dev and production. The route
    itself is hidden from the schema (``include_in_schema=False``) so it does not
    add a stray "meta" entry to the documented surface.
    """
    return request.app.openapi()
