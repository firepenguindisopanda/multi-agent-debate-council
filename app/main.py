import logging
from contextlib import asynccontextmanager
from urllib.parse import quote

import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlmodel import Session
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.routers import api_router, router, static_files, templates
from app.services.debate_runner import DebateRunner
from app.services.errors import ServiceError

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.data import seed_agents
    from app.database import engine, run_migrations
    from app.repositories.debate import DebateRepository

    settings = get_settings()
    if settings.auto_migrate:
        run_migrations()
        with Session(engine) as db:
            seed_agents(db)
            interrupted = DebateRepository(db).fail_interrupted()
            if interrupted:
                logger.warning("Marked %d interrupted debate(s) as failed", interrupted)
    if not settings.llm_configured:
        logger.warning("NVIDIA_API_KEY is not set: debates cannot run until it is configured")
    if not hasattr(app.state, "runner"):
        app.state.runner = DebateRunner()
    yield
    await app.state.runner.shutdown()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Debate Council",
        lifespan=lifespan,
        docs_url="/docs" if settings.is_dev else None,
        redoc_url=None,
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        same_site="lax",
        https_only=settings.is_production,
    )
    app.include_router(router)
    app.include_router(api_router)
    app.mount("/static", static_files, name="static")
    _register_error_handlers(app)
    return app


def _wants_json(request: Request) -> bool:
    return request.url.path.startswith("/api/")


def _error_page(request: Request, code: int, title: str, message: str) -> Response:
    return templates.TemplateResponse(
        request=request,
        name="error.html",
        context={"code": code, "title": title, "message": message},
        status_code=code,
    )


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        if _wants_json(request):
            return JSONResponse(
                {"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers
            )
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            login = f"/login?next={quote(request.url.path)}"
            if request.headers.get("HX-Request") == "true":
                return Response(status_code=401, headers={"HX-Redirect": login})
            return RedirectResponse(login, status_code=status.HTTP_303_SEE_OTHER)
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            return _error_page(
                request, 404, "Page not found", "We couldn't find what you were looking for."
            )
        if exc.status_code == status.HTTP_403_FORBIDDEN:
            return _error_page(request, 403, "Access denied", str(exc.detail))
        return _error_page(request, exc.status_code, "Something went wrong", str(exc.detail))

    @app.exception_handler(ServiceError)
    async def service_error(request: Request, exc: ServiceError):
        if _wants_json(request):
            return JSONResponse({"detail": exc.message}, status_code=exc.status_code)
        if request.headers.get("HX-Request") == "true":
            return templates.TemplateResponse(
                request=request,
                name="partials/toast.html",
                context={"message": exc.message, "kind": "danger"},
                status_code=exc.status_code,
                headers={"HX-Retarget": "#toasts", "HX-Reswap": "beforeend"},
            )
        titles = {404: "Not found", 409: "Can't do that", 503: "Model provider unavailable"}
        return _error_page(
            request, exc.status_code, titles.get(exc.status_code, "Error"), exc.message
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        if _wants_json(request):
            return JSONResponse({"detail": jsonable_encoder(exc.errors())}, status_code=422)
        return _error_page(
            request, 422, "Invalid request", "Some of the submitted data was invalid."
        )


app = create_app()

if __name__ == "__main__":
    s = get_settings()
    uvicorn.run("app.main:app", host=s.app_host, port=s.app_port, reload=s.is_dev)
