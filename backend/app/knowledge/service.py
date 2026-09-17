"""Keeps the knowledge index in sync with the files on disk."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

from app.knowledge.docstore import KnowledgeDocStore
from app.knowledge.loader import Knowledge, load_knowledge, signature_of
from app.knowledge.store import KnowledgeHit, KnowledgeStore
from app.models import CamelModel

log = logging.getLogger(__name__)

_ASSISTANT_NOTES_HEADER = (
    "# Assistant notes\n\nThings the assistant learned in conversation. Edit or delete freely.\n"
)


class KnowledgeDocInfo(CamelModel):
    name: str
    title: str
    headings: list[str]
    chunks: int
    size: int
    updated_at: datetime
    source: str = "file"  # file docs are read-only in the UI


class PlaybookInfo(CamelModel):
    name: str
    title: str
    description: str


class KnowledgeStatus(CamelModel):
    directory: str
    prompt_loaded: bool
    prompt_chars: int
    documents: list[KnowledgeDocInfo]
    chunks: int
    metric_notes: int
    playbooks: list[PlaybookInfo]
    prompt: str | None = None  # the editable (database) part of the prompt
    prompt_from_files: str | None = None  # prompt.md contents, read-only here


class KnowledgeService:
    def __init__(
        self,
        directories: Path | list[Path],
        store: KnowledgeStore,
        docs: KnowledgeDocStore | None = None,
    ) -> None:
        self.directories = [directories] if isinstance(directories, Path) else list(directories)
        self._store = store
        self._docs = docs
        self._knowledge: Knowledge | None = None
        self._lock = asyncio.Lock()

    async def _signature(self) -> tuple[tuple[str, float], ...]:
        files = await asyncio.to_thread(signature_of, self.directories)
        if self._docs is None:
            return files
        stored = await asyncio.to_thread(self._docs.list_sync)
        return files + tuple((f"db:{d.name}", d.updated_at) for d in stored)

    async def current(self) -> Knowledge:
        """The loaded knowledge, re-read when any file or stored document changed."""
        async with self._lock:
            signature = await self._signature()
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
        stored = await self._docs.list() if self._docs else []
        prompt = await self._docs.prompt() if self._docs else None
        knowledge = await asyncio.to_thread(load_knowledge, self.directories, stored, prompt)
        count = await self._store.replace_all(knowledge.chunks)
        self._knowledge = knowledge
        log.info(
            "knowledge loaded from %s: %d documents, %d chunks, prompt=%s",
            ", ".join(str(d) for d in self.directories),
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
            directory=", ".join(str(d) for d in self.directories),
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
                    source=d.source,
                )
                for d in knowledge.documents
            ],
            chunks=len(knowledge.chunks),
            metric_notes=len(knowledge.metric_notes),
            prompt=await self._docs.prompt() if self._docs else None,
            prompt_from_files=await asyncio.to_thread(self._file_prompt),
            playbooks=[
                PlaybookInfo(name=p.name, title=p.title, description=p.description)
                for p in knowledge.playbooks
            ],
        )

    # ---- editing (database-backed documents) ----------------------------

    @property
    def editable(self) -> bool:
        return self._docs is not None

    async def get_doc(self, name: str) -> tuple[str, str] | None:
        """Body and source of a stored document."""
        if self._docs is None:
            return None
        doc = await self._docs.get(name)
        return (doc.body, doc.source) if doc else None

    async def put_doc(self, name: str, body: str, source: str = "ui") -> None:
        assert self._docs is not None
        await self._docs.put(name, body, source)
        await self.reload()

    async def delete_doc(self, name: str) -> bool:
        assert self._docs is not None
        ok = await self._docs.delete(name)
        await self.reload()
        return ok

    async def set_prompt(self, text: str | None) -> None:
        assert self._docs is not None
        await self._docs.set_prompt(text)
        await self.reload()

    async def append_note(self, title: str, text: str) -> str:
        """Add a section to the assistant's own notes document; returns the document name."""
        assert self._docs is not None
        name = "assistant-notes"
        existing = await self._docs.get(name)
        body = existing.body if existing else _ASSISTANT_NOTES_HEADER
        stamp = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        body = body.rstrip() + f"\n\n## {title.strip()}\n\n{text.strip()}\n\n_Saved {stamp}._\n"
        await self._docs.put(name, body, source="assistant")
        await self.reload()
        return name

    def _file_prompt(self) -> str | None:
        parts = []
        for directory in self.directories:
            path = directory / "prompt.md"
            if path.is_file():
                text = path.read_text(encoding="utf-8", errors="replace").strip()
                if text:
                    parts.append(text)
        return "\n\n".join(parts) or None

    async def metric_note(self, name: str) -> str | None:
        note = (await self.current()).metric_notes.get(name)
        return note.text if note else None
