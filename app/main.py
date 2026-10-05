from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.router import api_router
from app.config.settings import get_settings
from app.db.database import init_db
from app.scheduler.scheduler import shutdown_scheduler, start_scheduler
from app.shared.exceptions import AppException
from app.shared.limiter import limiter

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    start_scheduler()
    yield
    shutdown_scheduler()


_is_prod = settings.app_env == "production"

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=not _is_prod,
    lifespan=lifespan,
    docs_url=None if _is_prod else "/docs",
    redoc_url=None if _is_prod else "/redoc",
    openapi_url=None if _is_prod else "/openapi.json",
)

app.add_middleware(GZipMiddleware, minimum_size=1000)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, settings.frontend_url_alt],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(api_router, prefix=settings.api_v1_prefix)


_SECURITY_HEADERS = {
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}
_HSTS_HEADER = "max-age=31536000; includeSubDomains"


@app.middleware("http")
async def add_security_headers(request: Request, call_next: object) -> Response:
    response: Response = await call_next(request)  # type: ignore[operator]
    for header, value in _SECURITY_HEADERS.items():
        response.headers[header] = value
    if _is_prod:
        response.headers["Strict-Transport-Security"] = _HSTS_HEADER
    return response


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": {"code": exc.code, "message": exc.message}},
    )


def _serialize_validation_errors(errors: list) -> list:
    result = []
    for err in errors:
        if "ctx" in err and "error" in err["ctx"]:
            err = {**err, "ctx": {**err["ctx"], "error": str(err["ctx"]["error"])}}
        result.append(jsonable_encoder(err))
    return result


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": _serialize_validation_errors(exc.errors())[0],
            },
        },
    )
