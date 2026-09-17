"""Map domain errors to HTTP responses."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.dashboard.migrations import MigrationError
from app.dashboard.service import DashboardNotFoundError, PanelNotFoundError
from app.dashboard.timerange import TimeRangeError
from app.panels import PanelValidationError


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(PanelValidationError)
    async def _validation(_: Request, exc: PanelValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": exc.errors})

    @app.exception_handler(PanelNotFoundError)
    async def _not_found(_: Request, exc: PanelNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(DashboardNotFoundError)
    async def _dashboard_not_found(_: Request, exc: DashboardNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(TimeRangeError)
    async def _time_range(_: Request, exc: TimeRangeError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(MigrationError)
    async def _migration(_: Request, exc: MigrationError) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": str(exc)})
