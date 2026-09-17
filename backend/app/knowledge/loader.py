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
PLAYBOOK_DIR = "playbooks"
MAX_CHUNK_CHARS = 1800
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
# "- `metric_name` — what it means" (also accepts ":" or "-" as the separator)
_METRIC_NOTE = re.compile(r"^\s*[-*]\s+`([A-Za-z_:][A-Za-z0-9_:]*)`\s*(?:[—–:-]\s*)?(.+?)\s*$")


@dataclass(slots=True)
class Chunk:
    doc: str
    heading: str
    body: str


@dataclass(slots=True)
class MetricNote:
    name: str
    text: str
    doc: str


@dataclass(slots=True)
class Playbook:
    """A named procedure the agent can be asked to run."""

    name: str  # file stem, used as the id
    title: str
    description: str  # first paragraph
    body: str  # full markdown
    path: Path


@dataclass(slots=True)
class Document:
    name: str  # file stem
    title: str
    path: Path | None
    mtime: float
    source: str = "file"  # file | ui | assistant
    headings: list[str] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)
    metric_notes: list[MetricNote] = field(default_factory=list)

    @property
    def size(self) -> int:
        return sum(len(c.body) for c in self.chunks)


@dataclass(slots=True)
class Knowledge:
    prompt: str | None
    documents: list[Document]
    playbooks: list[Playbook]
    signature: tuple[tuple[str, float], ...]  # (path, mtime) of every file seen

    @property
    def chunks(self) -> list[Chunk]:
        return [c for d in self.documents for c in d.chunks]

    @property
    def metric_notes(self) -> dict[str, MetricNote]:
        """Metric name → note; a later (more specific) document wins."""
        return {n.name: n for d in self.documents for n in d.metric_notes}

    def playbook(self, name: str) -> Playbook | None:
        return next((p for p in self.playbooks if p.name == name), None)


def _md_files(directory: Path) -> list[Path]:
    files = [p for p in directory.glob("*.md") if p.is_file()]
    playbooks = directory / PLAYBOOK_DIR
    if playbooks.is_dir():
        files.extend(p for p in playbooks.glob("*.md") if p.is_file())
    return sorted(files)


def signature_of(directories: Path | list[Path]) -> tuple[tuple[str, float], ...]:
    """Cheap change detector: file names and mtimes of every directory, sorted."""
    entries: list[tuple[str, float]] = []
    for directory in _as_list(directories):
        if directory.is_dir():
            entries.extend((str(p), p.stat().st_mtime) for p in _md_files(directory))
    return tuple(sorted(entries))


@dataclass(slots=True)
class StoredDoc:
    """A document kept in the database (edited in the UI or written by the assistant)."""

    name: str
    body: str
    source: str
    updated_at: float


def load_knowledge(
    directories: Path | list[Path],
    stored: list[StoredDoc] | None = None,
    stored_prompt: str | None = None,
) -> Knowledge:
    """Load one or more directories plus database-backed documents.

    Later directories are more specific: their ``prompt.md`` is appended after
    earlier ones, and their documents come last. Stored documents come after
    the files, and the stored prompt after the file prompts.
    """
    prompts: list[str] = []
    documents: list[Document] = []
    playbooks: dict[str, Playbook] = {}
    for directory in _as_list(directories):
        if not directory.is_dir():
            continue
        for path in _md_files(directory):
            text = path.read_text(encoding="utf-8", errors="replace")
            if path.parent.name == PLAYBOOK_DIR and path.parent.parent == directory:
                playbook = parse_playbook(path, text)
                playbooks[playbook.name] = playbook  # project-level overrides shared
                continue
            if path.name == PROMPT_FILE:
                if text.strip():
                    prompts.append(text.strip())
                continue
            documents.append(parse_document(path, text))
    for doc in stored or []:
        documents.append(
            parse_document(
                Path(f"{doc.name}.md"), doc.body, mtime=doc.updated_at, source=doc.source
            )
        )
    if stored_prompt and stored_prompt.strip():
        prompts.append(stored_prompt.strip())
    prompt = "\n\n".join(prompts) or None
    signature = signature_of(directories) + tuple(
        (f"db:{d.name}", d.updated_at) for d in stored or []
    )
    return Knowledge(
        prompt=prompt,
        documents=documents,
        playbooks=sorted(playbooks.values(), key=lambda p: p.title.lower()),
        signature=signature,
    )


def parse_playbook(path: Path, text: str) -> Playbook:
    title = path.stem.replace("-", " ").replace("_", " ").strip().capitalize()
    description = ""
    body_lines: list[str] = []
    for line in text.splitlines():
        m = _HEADING.match(line)
        if (
            m
            and len(m.group(1)) == 1
            and not body_lines
            and title == path.stem.replace("-", " ").replace("_", " ").strip().capitalize()
        ):
            title = m.group(2)
            continue
        body_lines.append(line)
    body = "\n".join(body_lines).strip()
    for para in re.split(r"\n{2,}", body):
        para = para.strip()
        if para and not para.startswith("#"):
            description = " ".join(para.split())
            break
    return Playbook(name=path.stem, title=title, description=description, body=body, path=path)


def _as_list(directories: Path | list[Path]) -> list[Path]:
    return [directories] if isinstance(directories, Path) else list(directories)


def parse_document(
    path: Path, text: str, *, mtime: float | None = None, source: str = "file"
) -> Document:
    lines = text.splitlines()
    title = path.stem.replace("-", " ").replace("_", " ").strip().capitalize()
    for line in lines:
        m = _HEADING.match(line)
        if m and len(m.group(1)) == 1:
            title = m.group(2)
            break

    if mtime is None:
        mtime = path.stat().st_mtime if path.exists() else 0.0
    doc = Document(
        name=path.stem,
        title=title,
        path=path if source == "file" else None,
        mtime=mtime,
        source=source,
    )
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
        note = _METRIC_NOTE.match(line)
        if note:
            doc.metric_notes.append(MetricNote(name=note.group(1), text=note.group(2), doc=title))
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
