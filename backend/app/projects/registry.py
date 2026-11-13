"""Per-project runtime: the Prometheus client, dashboard, catalog and knowledge for one project.

Runtimes are created lazily and cached; editing or deleting a project tears
its runtime down so the next request builds a fresh one.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from app.auth.secrets import Cipher, SecretKeyMismatchError
from app.catalog.builder import CatalogBuilder
from app.catalog.store import CatalogStore
from app.chat.store import ChatStore
from app.config import Settings
from app.dashboard.service import DashboardService
from app.dashboard.store import DashboardStore
from app.knowledge.docstore import KnowledgeDocStore
from app.knowledge.service import KnowledgeService
from app.knowledge.store import KnowledgeStore
from app.metrics import PROJECTS
from app.projects.models import (
    Project,
    ProjectCreate,
    ProjectUpdate,
    check_source_fields,
    slugify,
)
from app.projects.provisioning import ProvisionedProject, load_projects_file
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


class ProjectManagedError(ValueError):
    """The project is declared in PROJECTS_FILE; change it there."""

    def __init__(self, slug: str) -> None:
        super().__init__(
            f"project {slug!r} is managed by the projects file; change it there and restart"
        )


class ProjectInvalidError(ValueError):
    """An update would leave the project without what its source needs."""


@dataclass(slots=True)
class ProjectRuntime:
    project: Project
    prometheus: PrometheusClient
    dashboard: DashboardService
    catalog_store: CatalogStore
    catalog_builder: CatalogBuilder
    knowledge: KnowledgeService
    chat: ChatStore

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
        """Apply PROJECTS_FILE, create the default project from env on first run, warm runtimes."""
        await self._provision()
        records = await self._store.list()
        settings = self._settings
        if not records and settings.use_grafana:
            assert settings.grafana_url is not None
            record = await asyncio.to_thread(
                self._store.insert_sync,
                slug=DEFAULT_SLUG,
                name="Default",
                prometheus_url="",
                prometheus_username=settings.grafana_username,
                prometheus_password=self._cipher.encrypt(settings.grafana_password),
                tls_verify=settings.prometheus_tls_verify,
                source="grafana",
                grafana_url=settings.grafana_url.rstrip("/"),
                grafana_datasource_uid=settings.grafana_datasource_uid,
            )
            log.info(
                "created default project for Grafana %s, datasource %s",
                record.grafana_url,
                record.grafana_datasource_uid,
            )
            records = [record]
        elif not records and settings.prometheus_url:
            record = await asyncio.to_thread(
                self._store.insert_sync,
                slug=DEFAULT_SLUG,
                name="Default",
                prometheus_url=settings.prometheus_url.rstrip("/"),
                prometheus_username=settings.prometheus_username,
                prometheus_password=self._cipher.encrypt(settings.prometheus_password),
                tls_verify=settings.prometheus_tls_verify,
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

    async def _provision(self) -> None:
        path = self._settings.projects_file
        declared = await asyncio.to_thread(load_projects_file, path) if path is not None else None
        wanted = {p.slug: p for p in declared.projects} if declared else {}
        for record in await self._store.list():
            if record.managed and record.slug not in wanted:
                record.managed = False
                await asyncio.to_thread(self._store.update_sync, record)
                log.info("project %s is no longer in the projects file; now editable", record.slug)
        for spec in wanted.values():
            await self._apply(spec)
        if path is not None:
            log.info("applied %d project(s) from %s", len(wanted), path)

    async def _apply(self, spec: ProvisionedProject) -> None:
        via_grafana = spec.source == "grafana"
        fields = {
            "source": spec.source,
            "prometheus_url": spec.prometheus_url or "",
            "grafana_url": spec.grafana_url if via_grafana else None,
            "grafana_datasource_uid": spec.grafana_datasource_uid if via_grafana else None,
            "prometheus_username": spec.username,
            "tls_verify": (
                spec.tls_verify
                if spec.tls_verify is not None
                else self._settings.prometheus_tls_verify
            ),
        }
        record = await self._store.get(spec.slug)
        if record is None:
            await asyncio.to_thread(
                self._store.insert_sync,
                slug=spec.slug,
                name=spec.name or spec.slug,
                prometheus_password=self._cipher.encrypt(spec.password),
                managed=True,
                **fields,
            )
            log.info("created project %s from the projects file", spec.slug)
            return
        changed = not record.managed
        record.managed = True
        if spec.name and record.name != spec.name:
            record.name, changed = spec.name, True
        for key, value in fields.items():
            if getattr(record, key) != value:
                setattr(record, key, value)
                changed = True
        try:
            stored = self._cipher.decrypt(record.prometheus_password)
        except SecretKeyMismatchError:
            stored = object()  # unreadable: the file's value replaces it
        if stored != spec.password:
            record.prometheus_password = self._cipher.encrypt(spec.password)
            changed = True
        if changed:
            await asyncio.to_thread(self._store.update_sync, record)
            log.info("updated project %s from the projects file", spec.slug)

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
        via_grafana = record.source == "grafana" and record.grafana_url
        prometheus = PrometheusClient(
            (record.grafana_url or "") if via_grafana else record.prometheus_url,
            grafana_datasource_uid=record.grafana_datasource_uid if via_grafana else None,
            username=record.prometheus_username,
            password=self._cipher.decrypt(record.prometheus_password),
            timeout=settings.prometheus_query_timeout,
            tls_verify=record.tls_verify,
            ca_file=settings.prometheus_ca_file,
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
            chat=ChatStore(db),
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
            prometheus_url=data.prometheus_url or "",
            prometheus_username=data.prometheus_username or None,
            prometheus_password=self._cipher.encrypt(data.prometheus_password or None),
            tls_verify=(
                data.tls_verify
                if data.tls_verify is not None
                else self._settings.prometheus_tls_verify
            ),
            source=data.source,
            grafana_url=data.grafana_url if data.source == "grafana" else None,
            grafana_datasource_uid=(
                data.grafana_datasource_uid.strip()
                if data.source == "grafana" and data.grafana_datasource_uid
                else None
            ),
        )
        await self.runtime(slug)
        PROJECTS.set(len(await self._store.list()))
        return record.public()

    async def update(self, slug: str, data: ProjectUpdate) -> Project:
        record = await self._store.get(slug)
        if record is None:
            raise ProjectNotFoundError(slug)
        if record.managed and data.model_fields_set:
            raise ProjectManagedError(slug)
        if data.name is not None:
            record.name = data.name.strip()
        if data.source is not None:
            record.source = data.source
        if data.prometheus_url is not None:
            record.prometheus_url = data.prometheus_url
        if data.grafana_url is not None:
            record.grafana_url = data.grafana_url
        if data.grafana_datasource_uid is not None:
            record.grafana_datasource_uid = data.grafana_datasource_uid.strip() or None
        try:
            check_source_fields(
                record.source,  # type: ignore[arg-type]
                record.prometheus_url,
                record.grafana_url,
                record.grafana_datasource_uid,
            )
        except ValueError as exc:
            raise ProjectInvalidError(str(exc)) from exc
        if data.prometheus_username is not None:
            record.prometheus_username = data.prometheus_username or None
        if data.clear_password:
            record.prometheus_password = None
        elif data.prometheus_password:
            record.prometheus_password = self._cipher.encrypt(data.prometheus_password)
        if data.tls_verify is not None:
            record.tls_verify = data.tls_verify
        record = await asyncio.to_thread(self._store.update_sync, record)
        await self._evict(slug)
        await self.runtime(slug)
        return record.public()

    async def delete(self, slug: str) -> None:
        record = await self._store.get(slug)
        if record is None:
            raise ProjectNotFoundError(slug)
        if record.managed:
            raise ProjectManagedError(slug)
        await self._evict(slug)
        await asyncio.to_thread(self._store.delete_sync, slug)
        PROJECTS.set(len(await self._store.list()))
        # The project's own database goes with it; the default project shares the main file.
        if slug != DEFAULT_SLUG:
            for suffix in ("", "-wal", "-shm"):
                path = Path(str(self.db_path(slug)) + suffix)
                if path.exists():
                    path.unlink()

    async def stored_password(self, slug: str) -> str | None:
        """The decrypted password, for connection tests that leave the field blank."""
        record = await self._store.get(slug)
        if record is None:
            raise ProjectNotFoundError(slug)
        return self._cipher.decrypt(record.prometheus_password)

    async def _evict(self, slug: str) -> None:
        async with self._lock:
            runtime = self._runtimes.pop(slug, None)
        if runtime is not None:
            await runtime.close()
