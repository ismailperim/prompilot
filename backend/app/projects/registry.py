"""Per-project runtime: the Prometheus client, dashboard, catalog and knowledge for one project.

Runtimes are created lazily and cached; editing or deleting a project tears
its runtime down so the next request builds a fresh one.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from app.auth.secrets import Cipher
from app.catalog.builder import CatalogBuilder
from app.catalog.store import CatalogStore
from app.config import Settings
from app.dashboard.service import DashboardService
from app.dashboard.store import DashboardStore
from app.knowledge.docstore import KnowledgeDocStore
from app.knowledge.service import KnowledgeService
from app.knowledge.store import KnowledgeStore
from app.metrics import PROJECTS
from app.projects.models import Project, ProjectCreate, ProjectUpdate, slugify
from app.projects.store import ProjectRecord, ProjectStore
from app.prometheus import PrometheusClient

log = logging.getLogger(__name__)

DEFAULT_SLUG = "default"


class ProjectNotFoundError(KeyError):
    def __init__(self, slug: str) -> None:
        super().__init__(slug)
        self.slug = slug

    def __str__(self) -> str:
        return f"project {self.slug!r} not found"


class ProjectExistsError(ValueError):
    pass


@dataclass(slots=True)
class ProjectRuntime:
    project: Project
    prometheus: PrometheusClient
    dashboard: DashboardService
    catalog_store: CatalogStore
    catalog_builder: CatalogBuilder
    knowledge: KnowledgeService

    async def close(self) -> None:
        await self.catalog_builder.stop()
        await self.prometheus.aclose()


class ProjectRegistry:
    def __init__(self, settings: Settings, cipher: Cipher) -> None:
        self._settings = settings
        self._cipher = cipher
        self._store = ProjectStore(settings.data_dir / "prompilot.sqlite")
        self._runtimes: dict[str, ProjectRuntime] = {}
        self._lock = asyncio.Lock()

    # ---- paths ------------------------------------------------------------

    def db_path(self, slug: str) -> Path:
        # The default project keeps using the main database so existing data carries over.
        if slug == DEFAULT_SLUG:
            return self._settings.data_dir / "prompilot.sqlite"
        return self._settings.data_dir / "projects" / f"{slug}.sqlite"

    def knowledge_dirs(self, slug: str) -> list[Path]:
        root = self._settings.knowledge_path
        return [root, root / slug]

    # ---- lifecycle --------------------------------------------------------

    async def start(self) -> None:
        """Create the default project from PROMETHEUS_URL on first run, then warm every runtime."""
        records = await self._store.list()
        if not records and self._settings.prometheus_url:
            record = await asyncio.to_thread(
                self._store.insert_sync,
                slug=DEFAULT_SLUG,
                name="Default",
                prometheus_url=self._settings.prometheus_url.rstrip("/"),
                prometheus_username=self._settings.prometheus_username,
                prometheus_password=self._cipher.encrypt(self._settings.prometheus_password),
            )
            log.info("created default project for %s", record.prometheus_url)
            records = [record]
        for record in records:
            # Rows written before encryption existed are upgraded in place.
            if record.prometheus_password and not Cipher.is_encrypted(record.prometheus_password):
                record.prometheus_password = self._cipher.encrypt(record.prometheus_password)
                await asyncio.to_thread(self._store.update_sync, record)
                log.info("encrypted the stored password of project %s", record.slug)
            await self.runtime(record.slug)

    async def stop(self) -> None:
        for runtime in list(self._runtimes.values()):
            await runtime.close()
        self._runtimes.clear()

    # ---- queries ----------------------------------------------------------

    async def list(self) -> list[Project]:
        return [r.public() for r in await self._store.list()]

    async def get(self, slug: str) -> Project:
        record = await self._store.get(slug)
        if record is None:
            raise ProjectNotFoundError(slug)
        return record.public()

    async def runtime(self, slug: str) -> ProjectRuntime:
        runtime = self._runtimes.get(slug)
        if runtime is not None:
            return runtime
        async with self._lock:
            runtime = self._runtimes.get(slug)
            if runtime is not None:
                return runtime
            record = await self._store.get(slug)
            if record is None:
                raise ProjectNotFoundError(slug)
            runtime = self._build(record)
            self._runtimes[slug] = runtime
            await runtime.knowledge.reload()
            if self._settings.catalog_autostart:
                runtime.catalog_builder.start()
            return runtime

    def _build(self, record: ProjectRecord) -> ProjectRuntime:
        settings = self._settings
        db = self.db_path(record.slug)
        prometheus = PrometheusClient(
            record.prometheus_url,
            username=record.prometheus_username,
            password=self._cipher.decrypt(record.prometheus_password),
            timeout=settings.prometheus_query_timeout,
        )
        catalog_store = CatalogStore(db)
        return ProjectRuntime(
            project=record.public(),
            prometheus=prometheus,
            dashboard=DashboardService(DashboardStore(db)),
            catalog_store=catalog_store,
            catalog_builder=CatalogBuilder(
                prometheus,
                catalog_store,
                label_sample_limit=settings.catalog_label_sample_limit,
                concurrency=settings.catalog_concurrency,
                rebuild_interval=settings.catalog_rebuild_interval,
                project=record.slug,
            ),
            knowledge=KnowledgeService(
                self.knowledge_dirs(record.slug), KnowledgeStore(db), KnowledgeDocStore(db)
            ),
        )

    # ---- mutations --------------------------------------------------------

    async def create(self, data: ProjectCreate) -> Project:
        slug = data.slug or slugify(data.name)
        if await self._store.get(slug) is not None:
            raise ProjectExistsError(f"a project with slug {slug!r} already exists")
        record = await asyncio.to_thread(
            self._store.insert_sync,
            slug=slug,
            name=data.name.strip(),
            prometheus_url=data.prometheus_url,
            prometheus_username=data.prometheus_username or None,
            prometheus_password=self._cipher.encrypt(data.prometheus_password or None),
        )
        await self.runtime(slug)
        PROJECTS.set(len(await self._store.list()))
        return record.public()

    async def update(self, slug: str, data: ProjectUpdate) -> Project:
        record = await self._store.get(slug)
        if record is None:
            raise ProjectNotFoundError(slug)
        if data.name is not None:
            record.name = data.name.strip()
        if data.prometheus_url is not None:
            record.prometheus_url = data.prometheus_url
        if data.prometheus_username is not None:
            record.prometheus_username = data.prometheus_username or None
        if data.clear_password:
            record.prometheus_password = None
        elif data.prometheus_password:
            record.prometheus_password = self._cipher.encrypt(data.prometheus_password)
        record = await asyncio.to_thread(self._store.update_sync, record)
        await self._evict(slug)
        await self.runtime(slug)
        return record.public()

    async def delete(self, slug: str) -> None:
        if await self._store.get(slug) is None:
            raise ProjectNotFoundError(slug)
        await self._evict(slug)
        await asyncio.to_thread(self._store.delete_sync, slug)
        PROJECTS.set(len(await self._store.list()))
        # The project's own database goes with it; the default project shares the main file.
        if slug != DEFAULT_SLUG:
            for suffix in ("", "-wal", "-shm"):
                path = Path(str(self.db_path(slug)) + suffix)
                if path.exists():
                    path.unlink()

    async def _evict(self, slug: str) -> None:
        async with self._lock:
            runtime = self._runtimes.pop(slug, None)
        if runtime is not None:
            await runtime.close()
