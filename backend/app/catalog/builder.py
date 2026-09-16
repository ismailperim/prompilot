"""Discover metrics from Prometheus and (re)build the catalog in the background."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from datetime import timedelta

from app.catalog.categorize import categorize, exporter_prefix
from app.catalog.models import CatalogStatus, MetricEntry
from app.catalog.store import CatalogStore, now_iso
from app.prometheus import PrometheusClient, PrometheusError

log = logging.getLogger(__name__)


class CatalogBuilder:
    def __init__(
        self,
        prometheus: PrometheusClient,
        store: CatalogStore,
        *,
        label_sample_limit: int = 2000,
        concurrency: int = 6,
        rebuild_interval: timedelta = timedelta(hours=24),
    ) -> None:
        self._prometheus = prometheus
        self._store = store
        self._label_sample_limit = label_sample_limit
        self._concurrency = max(1, concurrency)
        self._rebuild_interval = rebuild_interval
        self._task: asyncio.Task[None] | None = None
        self._scheduler: asyncio.Task[None] | None = None

    # ---- lifecycle --------------------------------------------------------

    def start(self) -> None:
        """Kick off the startup build (if needed) and the periodic rebuild loop."""
        self._scheduler = asyncio.create_task(self._schedule(), name="catalog-scheduler")

    async def stop(self) -> None:
        for task in (self._scheduler, self._task):
            if task and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task

    @property
    def building(self) -> bool:
        return self._task is not None and not self._task.done()

    def trigger(self) -> bool:
        """Start a build unless one is already running. Returns whether one was started."""
        if self.building:
            return False
        self._task = asyncio.create_task(self.build(), name="catalog-build")
        return True

    async def status(self) -> CatalogStatus:
        status = await self._store.status()
        if self.building and status.state != "building":
            status.state = "building"
        return status

    async def _schedule(self) -> None:
        status = await self._store.status()
        stale = status.updated_at is None or (
            self._rebuild_interval > timedelta(0)
            and (time.time() - status.updated_at.timestamp())
            > self._rebuild_interval.total_seconds()
        )
        if stale or status.state in ("building", "error"):
            self.trigger()
        if self._rebuild_interval <= timedelta(0):
            return
        while True:
            await asyncio.sleep(self._rebuild_interval.total_seconds())
            self.trigger()

    # ---- build ------------------------------------------------------------

    async def build(self) -> CatalogStatus:
        started = time.monotonic()
        await self._store.set_meta(state="building", error=None)
        try:
            entries = await self._discover()
            count = await self._store.replace_all(entries)
            await self._sample_labels([e.name for e in entries][: self._label_sample_limit])
            await self._store.set_meta(
                state="ready",
                updated_at=now_iso(),
                duration_seconds=f"{time.monotonic() - started:.2f}",
                error=None,
            )
            log.info("catalog built: %d metrics in %.1fs", count, time.monotonic() - started)
        except asyncio.CancelledError:
            await self._store.set_meta(state="idle")
            raise
        except PrometheusError as exc:
            log.warning("catalog build failed: %s", exc)
            await self._store.set_meta(state="error", error=str(exc))
        except Exception as exc:  # noqa: BLE001 — a failed build must never crash the app
            log.exception("catalog build crashed")
            await self._store.set_meta(state="error", error=f"unexpected error: {exc}")
        return await self._store.status()

    async def _discover(self) -> list[MetricEntry]:
        names, metadata = await asyncio.gather(
            self._prometheus.label_values("__name__"),
            self._prometheus.metadata(limit_per_metric=1),
        )
        entries = []
        for name in sorted(set(names)):
            meta = metadata.get(name)
            # Histogram/summary children share the parent's metadata entry.
            if meta is None:
                for suffix in ("_bucket", "_count", "_sum"):
                    if name.endswith(suffix):
                        meta = metadata.get(name[: -len(suffix)])
                        break
            first = meta[0] if meta else None
            entries.append(
                MetricEntry(
                    name=name,
                    type=first.type if first else "unknown",
                    help=first.help if first else "",
                    unit=first.unit if first else "",
                    category=categorize(name),
                    exporter=exporter_prefix(name),
                )
            )
        return entries

    async def _sample_labels(self, names: list[str]) -> None:
        semaphore = asyncio.Semaphore(self._concurrency)

        async def one(name: str) -> None:
            async with semaphore:
                try:
                    labels = await self._prometheus.labels(match=[name])
                except PrometheusError as exc:
                    log.debug("label sampling failed for %s: %s", name, exc)
                    return
                await self._store.update_labels(name, sorted(x for x in labels if x != "__name__"))

        await asyncio.gather(*(one(n) for n in names))

    async def ensure_labels(self, entry: MetricEntry) -> MetricEntry:
        """Fetch label keys on demand for a metric that was not sampled during the build."""
        if entry.labels_sampled:
            return entry
        try:
            labels = await self._prometheus.labels(match=[entry.name])
        except PrometheusError:
            return entry
        labels = sorted(x for x in labels if x != "__name__")
        await self._store.update_labels(entry.name, labels)
        return entry.model_copy(update={"labels": labels, "labels_sampled": True})
