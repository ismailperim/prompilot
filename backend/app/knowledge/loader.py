"""Read Markdown knowledge files and split them into searchable chunks.

Layout of ``KNOWLEDGE_DIR``:

- ``prompt.md`` — operator instructions, injected into the system prompt verbatim.
- any other ``*.md`` — knowledge documents, split on headings into chunks that the
  agent can search. The first ``# Title`` (or the file name) names the document.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

PROMPT_FILE = "prompt.md"
MAX_CHUNK_CHARS = 1800
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


@dataclass(slots=True)
class Chunk:
    doc: str
    heading: str
    body: str


@dataclass(slots=True)
class Document:
    name: str  # file stem
    title: str
    path: Path
    mtime: float
    headings: list[str] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)

    @property
    def size(self) -> int:
        return sum(len(c.body) for c in self.chunks)


@dataclass(slots=True)
class Knowledge:
    prompt: str | None
    documents: list[Document]
    signature: tuple[tuple[str, float], ...]  # (path, mtime) of every file seen

    @property
    def chunks(self) -> list[Chunk]:
        return [c for d in self.documents for c in d.chunks]


def signature_of(directory: Path) -> tuple[tuple[str, float], ...]:
    """Cheap change detector: file names and mtimes, sorted."""
    if not directory.is_dir():
        return ()
    return tuple(sorted((str(p), p.stat().st_mtime) for p in directory.glob("*.md") if p.is_file()))


def load_knowledge(directory: Path) -> Knowledge:
    prompt: str | None = None
    documents: list[Document] = []
    if directory.is_dir():
        for path in sorted(directory.glob("*.md")):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if path.name == PROMPT_FILE:
                prompt = text.strip() or None
                continue
            documents.append(parse_document(path, text))
    return Knowledge(prompt=prompt, documents=documents, signature=signature_of(directory))


def parse_document(path: Path, text: str) -> Document:
    lines = text.splitlines()
    title = path.stem.replace("-", " ").replace("_", " ").strip().capitalize()
    for line in lines:
        m = _HEADING.match(line)
        if m and len(m.group(1)) == 1:
            title = m.group(2)
            break

    doc = Document(name=path.stem, title=title, path=path, mtime=path.stat().st_mtime)
    heading_path: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        body = "\n".join(buffer).strip()
        buffer.clear()
        if not body:
            return
        heading = " › ".join(heading_path) if heading_path else title
        for piece in _split_long(body):
            doc.chunks.append(Chunk(doc=title, heading=heading, body=piece))

    for line in lines:
        m = _HEADING.match(line)
        if m:
            flush()
            level = len(m.group(1))
            if level == 1:
                heading_path = []
                continue
            heading_path = heading_path[: level - 2] + [m.group(2)]
            doc.headings.append(m.group(2))
            continue
        buffer.append(line)
    flush()
    return doc


def _split_long(body: str) -> list[str]:
    """Keep chunks under MAX_CHUNK_CHARS, breaking on paragraph boundaries."""
    if len(body) <= MAX_CHUNK_CHARS:
        return [body]
    pieces: list[str] = []
    current: list[str] = []
    size = 0
    for para in re.split(r"\n{2,}", body):
        if size + len(para) > MAX_CHUNK_CHARS and current:
            pieces.append("\n\n".join(current))
            current, size = [], 0
        current.append(para)
        size += len(para) + 2
    if current:
        pieces.append("\n\n".join(current))
    return pieces
