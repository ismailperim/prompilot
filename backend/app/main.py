"""FastAPI application entry point."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings

STATIC_DIR = Path(__file__).parent / "static"


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="PromPilot",
        version="0.1.0",
        description="Chat-driven Prometheus visualization with Grafana export.",
    )

    @app.get("/healthz", tags=["system"])
    async def healthz() -> dict[str, object]:
        return {
            "status": "ok",
            "prometheus_url": settings.prometheus_url,
            "llm_enabled": settings.llm_enabled,
        }

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
