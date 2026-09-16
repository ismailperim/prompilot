"""FastAPI application entry point."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.agent.llm import OpenAICompatibleProvider
from app.api import catalog, chat, data, export, panels, system
from app.api.errors import install_error_handlers
from app.catalog.builder import CatalogBuilder
from app.catalog.store import CatalogStore
from app.config import get_settings
from app.dashboard.service import DashboardService
from app.dashboard.store import DashboardStore
from app.prometheus import PrometheusClient

STATIC_DIR = Path(__file__).parent / "static"
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one line per Prometheus call is too much
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    db_path = settings.data_dir / "prompilot.sqlite"
    app.state.prometheus = PrometheusClient.from_settings(settings)
    app.state.dashboard = DashboardService(DashboardStore(db_path))
    app.state.catalog_store = CatalogStore(db_path)
    app.state.catalog_builder = CatalogBuilder(
        app.state.prometheus,
        app.state.catalog_store,
        label_sample_limit=settings.catalog_label_sample_limit,
        concurrency=settings.catalog_concurrency,
        rebuild_interval=settings.catalog_rebuild_interval,
    )
    app.state.llm = (
        OpenAICompatibleProvider.from_settings(settings) if settings.llm_enabled else None
    )
    log.info(
        "data dir: %s, prometheus: %s, llm: %s",
        settings.data_dir,
        settings.prometheus_url,
        f"{settings.llm_model} @ {settings.llm_base_url}" if settings.llm_enabled else "disabled",
    )
    if settings.catalog_autostart:
        app.state.catalog_builder.start()
    try:
        yield
    finally:
        await app.state.catalog_builder.stop()
        await app.state.prometheus.aclose()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="PromPilot",
        version="0.1.0",
        description="Chat-driven Prometheus visualization with Grafana export.",
        lifespan=lifespan,
    )

    @app.get("/healthz", tags=["system"])
    async def healthz() -> dict[str, object]:
        return {
            "status": "ok",
            "prometheus_url": settings.prometheus_url,
            "llm_enabled": settings.llm_enabled,
        }

    install_error_handlers(app)
    app.include_router(system.router)
    app.include_router(panels.router)
    app.include_router(data.router)
    app.include_router(export.router)
    app.include_router(catalog.router)
    app.include_router(chat.router)
    _mount_frontend(app)
    return app


def _mount_frontend(app: FastAPI) -> None:
    """Serve the built frontend if present (production image); no-op in dev."""
    if not STATIC_DIR.is_dir():
        return

    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        candidate = STATIC_DIR / path
        if path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(STATIC_DIR / "index.html")


app = create_app()
