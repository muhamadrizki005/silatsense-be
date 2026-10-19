from uuid import uuid4

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse


class DomainError(HTTPException):
    def __init__(self, status_code: int, code: str, detail: str):
        super().__init__(status_code, detail)
        self.code = code


def is_domain_request(request: Request):
    path = request.url.path.rstrip("/")
    if path.startswith(("/api/v1/auth/email-link/", "/api/v1/auth/email-verification/", "/api/v1/auth/password-reset/")):
        return True
    return path.startswith("/api/v1/member/") or path.startswith("/api/v1/coach/roster") or path.startswith(
        "/api/v1/coach/sessions/") or path in {"/api/v1/coach/profile", "/api/v1/coach/password", "/api/v1/coach/overview"}


def error_response(request, status, code, detail, *, errors=None, headers=None):
    body = {"detail": detail, "code": code, "requestId": request.state.request_id}
    if errors is not None:
        body["errors"] = errors
    return JSONResponse(body, status_code=status, headers=headers)


def install_domain_errors(app):
    @app.middleware("http")
    async def domain_headers(request: Request, call_next):
        if not is_domain_request(request):
            return await call_next(request)
        request.state.request_id = getattr(request.state, "request_id", str(uuid4()))
        try:
            response = await call_next(request)
        except Exception:
            response = error_response(request, 500, "internal_error", "Terjadi kesalahan internal.")
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc):
        if not is_domain_request(request):
            return await http_exception_handler(request, exc)
        code = getattr(exc, "code", None) or {
            401: "unauthenticated", 403: "forbidden_role", 404: "not_found",
        }.get(exc.status_code, "request_error")
        if exc.status_code == 403 and exc.detail == "Origin tidak diizinkan.":
            code = "origin_not_allowed"
        return error_response(request, exc.status_code, code, str(exc.detail), headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc):
        if not is_domain_request(request):
            return await request_validation_exception_handler(request, exc)
        issues = [{"field": ".".join(map(str, issue["loc"])), "message": issue["msg"]}
                  for issue in exc.errors()]
        return error_response(request, 422, "validation_error", "Data tidak valid.", errors=issues)
