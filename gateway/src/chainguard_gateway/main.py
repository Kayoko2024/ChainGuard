"""Operations gateway; centralized A/B routes require an explicit service."""
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import __version__
from .config import PROJECT_ROOT, Settings, load_settings
from .integrity import check_frozen_protocol

LOGGER = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    service: Literal["chainguard-gateway"] = "chainguard-gateway"
    status: Literal["alive", "ready", "not_ready"]
    stage: Literal[1, 3] = 1
    version: str = __version__
    protocol_version: Literal["1.0.0"] = "1.0.0"
    pid: int
    uptime_seconds: float
    checks: dict[str, bool]


def create_app(settings: Settings | None = None, project_root: Path = PROJECT_ROOT, *, central_service=None) -> FastAPI:
    config = load_settings() if settings is None else settings
    started_at = time.monotonic()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        check_frozen_protocol(project_root)
        application.state.startup_complete = True
        try:
            yield
        finally:
            application.state.startup_complete = False

    application = FastAPI(
        title="ChainGuard operations only", version=__version__, lifespan=lifespan,
        docs_url=None, redoc_url=None, openapi_url="/operations/openapi.json",
    )
    application.state.settings = config
    application.state.startup_complete = False

    def payload(status, checks):
        return HealthResponse(stage=3 if central_service else 1, status=status, pid=os.getpid(), uptime_seconds=round(time.monotonic() - started_at, 6), checks=checks)

    @application.get("/health/live", response_model=HealthResponse, tags=["operations"])
    def liveness():
        return payload("alive", {"process": True})

    @application.get("/health/ready", response_model=HealthResponse, responses={503: {"model": HealthResponse}}, tags=["operations"])
    def readiness():
        checks = {"startup": application.state.startup_complete, "frozen_protocol": False}
        try:
            check_frozen_protocol(project_root)
            checks["frozen_protocol"] = True
        except (OSError, ValueError, RuntimeError):
            LOGGER.warning("Readiness failed: frozen protocol integrity check")
        ready = all(checks.values())
        result = payload("ready" if ready else "not_ready", checks)
        return result if ready else JSONResponse(status_code=503, content=result.model_dump())

    if central_service is not None:
        from .central_api import install_central_api
        install_central_api(application, central_service)
    return application


app = create_app()
