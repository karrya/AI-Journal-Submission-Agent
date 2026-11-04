import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1 import auth, authorizations, authors, readiness
from app.api.v1.deps import first_password_gate
from app.core.config import get_settings
from app.core.errors import AppError
from app.services.auth import LoginRateLimiter

logger = logging.getLogger(__name__)

app = FastAPI(title="Academic Submission Agent")
app.state.login_rate_limiter = LoginRateLimiter()
app.include_router(readiness.router)
app.include_router(auth.router)
app.include_router(authors.router)
app.include_router(authorizations.router)
app.middleware("http")(first_password_gate)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = str(uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.message,
            "request_id": request.state.request_id,
            "details": exc.details,
        },
    )


@app.get("/api/v1/health")
def health():
    return {"status": "ok"}


@app.exception_handler(404)
async def not_found(request: Request, exc):
    return JSONResponse(
        status_code=404,
        content={
            "code": "RESOURCE_NOT_FOUND",
            "message": "资源不存在",
            "request_id": request.state.request_id,
            "details": None,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    details = [
        {"loc": list(error["loc"]), "message": error["msg"]} for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "code": "VALIDATION_ERROR",
            "message": "请求参数校验失败",
            "request_id": request.state.request_id,
            "details": details,
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException):
    code = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "PERMISSION_DENIED",
        405: "METHOD_NOT_ALLOWED",
        409: "CONFLICT",
        413: "FILE_TOO_LARGE",
        415: "UNSUPPORTED_FILE_TYPE",
        422: "VALIDATION_ERROR",
        429: "TOO_MANY_ATTEMPTS",
        503: "DATABASE_UNAVAILABLE",
    }.get(exc.status_code, "HTTP_ERROR")
    return JSONResponse(
        status_code=exc.status_code,
        headers=exc.headers,
        content={
            "code": code,
            "message": str(exc.detail),
            "request_id": request.state.request_id,
            "details": None,
        },
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logger.error(
        "Unhandled request exception",
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(
        status_code=500,
        headers={"X-Request-ID": request.state.request_id},
        content={
            "code": "INTERNAL_SERVER_ERROR",
            "message": "服务器内部错误",
            "request_id": request.state.request_id,
            "details": None,
        },
    )
