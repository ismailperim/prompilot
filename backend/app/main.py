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
from app.api import catalog, chat, data, export, knowledge, panels, projects, system, voice
from app.api.errors import install_error_handlers
from app.config import get_settings
from app.projects.registry import ProjectRegistry
from app.voice.providers import build_voice

STATIC_DIR = Path(__file__).parent / "static"
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one line per Prometheus call is too much
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    app.state.llm = (
        OpenAICompatibleProvider.from_settings(settings) if settings.llm_enabled else None
    )
    app.state.voice = build_voice(settings)
    app.state.projects = ProjectRegistry(settings)
    await app.state.projects.start()
    log.info(
        "data dir: %s, projects: %d, llm: %s",
        settings.data_dir,
        len(await app.state.projects.list()),
        f"{settings.llm_model} @ {settings.llm_base_url}" if settings.llm_enabled else "disabled",
    )
    try:
        yield
    finally:
        await app.state.projects.stop()


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
        return {"status": "ok", "llm_enabled": settings.llm_enabled}

    install_error_handlers(app)
    app.include_router(system.router)
    app.include_router(projects.router)
    app.include_router(voice.router)
    app.include_router(panels.global_router)
    app.include_router(catalog.global_router)
    app.include_router(panels.router)
    app.include_router(data.router)
    app.include_router(export.router)
    app.include_router(catalog.router)
    app.include_router(chat.router)
    app.include_router(knowledge.router)
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
