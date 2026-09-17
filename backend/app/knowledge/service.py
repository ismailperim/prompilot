"""Keeps the knowledge index in sync with the files on disk."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

from app.knowledge.loader import Knowledge, load_knowledge, signature_of
from app.knowledge.store import KnowledgeHit, KnowledgeStore
from app.models import CamelModel

log = logging.getLogger(__name__)


class KnowledgeDocInfo(CamelModel):
    name: str
    title: str
    headings: list[str]
    chunks: int
    size: int
    updated_at: datetime


class KnowledgeStatus(CamelModel):
    directory: str
    prompt_loaded: bool
    prompt_chars: int
    documents: list[KnowledgeDocInfo]
    chunks: int


class KnowledgeService:
    def __init__(self, directory: Path, store: KnowledgeStore) -> None:
        self.directory = directory
        self._store = store
        self._knowledge: Knowledge | None = None
        self._lock = asyncio.Lock()

    async def current(self) -> Knowledge:
        """The loaded knowledge, re-read when any file changed since last time."""
        async with self._lock:
            signature = await asyncio.to_thread(signature_of, self.directory)
            if self._knowledge is None or self._knowledge.signature != signature:
                await self._reload_locked()
            assert self._knowledge is not None
            return self._knowledge

    async def reload(self) -> Knowledge:
        async with self._lock:
            await self._reload_locked()
            assert self._knowledge is not None
            return self._knowledge

    async def _reload_locked(self) -> None:
        knowledge = await asyncio.to_thread(load_knowledge, self.directory)
        count = await self._store.replace_all(knowledge.chunks)
        self._knowledge = knowledge
        log.info(
            "knowledge loaded from %s: %d documents, %d chunks, prompt=%s",
            self.directory,
            len(knowledge.documents),
            count,
            "yes" if knowledge.prompt else "no",
        )

    async def search(self, query: str, *, limit: int = 5) -> list[KnowledgeHit]:
        await self.current()  # make sure the index is fresh
        return await self._store.search(query, limit=limit)

    async def status(self) -> KnowledgeStatus:
        knowledge = await self.current()
        return KnowledgeStatus(
            directory=str(self.directory),
            prompt_loaded=knowledge.prompt is not None,
            prompt_chars=len(knowledge.prompt or ""),
            documents=[
                KnowledgeDocInfo(
                    name=d.name,
                    title=d.title,
                    headings=d.headings,
                    chunks=len(d.chunks),
                    size=d.size,
                    updated_at=datetime.fromtimestamp(d.mtime, tz=UTC),
                )
                for d in knowledge.documents
            ],
            chunks=len(knowledge.chunks),
        )
