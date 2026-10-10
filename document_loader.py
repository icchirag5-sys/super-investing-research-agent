"""Document loading: read research-pack files, parse metadata, split into citable chunks.

Supported inputs: .md, .txt (with a metadata header) and .pdf (text layer, via pypdf).

Every document is expected to start with a metadata header, either YAML-style
front matter between `---` lines or plain `key: value` lines, containing at
least: source, url, published. Missing metadata is reported as an error, never
guessed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

SUPPORTED_EXTENSIONS = {".md", ".txt", ".pdf"}
REQUIRED_METADATA = ("source", "url", "published")


class DocumentLoadError(Exception):
    """Raised when documents are missing or unusable. Message is user-facing."""


@dataclass
class Chunk:
    chunk_id: str          # e.g. "S2.3"
    section: str           # human-readable location, e.g. "Consolidated highlights" or "p. 4"
    text: str


@dataclass
class Document:
    doc_id: str            # e.g. "S2"
    filename: str
    source: str
    url: str
    published: date
    doc_type: str          # free text from header, e.g. "official company filing"
    body: str
    chunks: list[Chunk] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)   # filled in by evidence_extractor

    def chunk_by_id(self, chunk_id: str) -> Chunk | None:
        for c in self.chunks:
            if c.chunk_id == chunk_id:
                return c
        return None


# --------------------------------------------------------------------------- parsing

_FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_KEY_VALUE = re.compile(r"^([A-Za-z_][\w \-]*):\s*(.*)$")


def parse_metadata(text: str) -> tuple[dict[str, str], str]:
    """Split a document into (metadata dict, body). Keys are lower-cased."""
    meta: dict[str, str] = {}
    m = _FRONT_MATTER.match(text)
    if m:
        header, body = m.group(1), text[m.end():]
    else:
        # fall back to leading `key: value` lines
        lines = text.splitlines()
        header_lines = []
        i = 0
        while i < len(lines) and _KEY_VALUE.match(lines[i]):
            header_lines.append(lines[i])
            i += 1
        header, body = "\n".join(header_lines), "\n".join(lines[i:])
    for line in header.splitlines():
        km = _KEY_VALUE.match(line.strip())
        if km:
            meta[km.group(1).strip().lower()] = km.group(2).strip()
    return meta, body.strip()


def parse_date(value: str) -> date:
    """Parse YYYY-MM-DD. Raises ValueError with a clear message otherwise."""
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError(f"expected publication date as YYYY-MM-DD, got {value!r}") from exc


# --------------------------------------------------------------------------- chunking

_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_SPEAKER_TURN = re.compile(r"^\*\*([^*]+?):\*\*")


def _section_label(paragraph: str, current_heading: str) -> str:
    """Label a paragraph: transcript turns get the speaker name, others the heading."""
    m = _SPEAKER_TURN.match(paragraph)
    if m:
        speaker = m.group(1).strip()
        return f"{current_heading} — {speaker}" if current_heading else speaker
    return current_heading or "main text"


def chunk_text(doc_id: str, body: str) -> list[Chunk]:
    """Split Markdown/plain text into paragraph, table and bullet chunks.

    - A chunk is a blank-line-separated block; bullet lists are split so each
      bullet is individually citable; transcript turns stay separate.
    - Headings (#) set the section label for everything beneath them.
    - A stand-alone bold line (e.g. "**Consolidated highlights**") labels only
      the block that immediately follows it.
    """
    chunks: list[Chunk] = []
    heading = ""
    pending_label = ""
    n = 0

    def add(label: str, text: str) -> None:
        nonlocal n
        n += 1
        chunks.append(Chunk(chunk_id=f"{doc_id}.{n}", section=label, text=text))

    for block in re.split(r"\n\s*\n", body):
        block = block.strip()
        if not block:
            continue
        hm = _HEADING.match(block)
        if hm and "\n" not in block:
            heading, pending_label = hm.group(2), ""
            continue
        if re.match(r"^\*\*[^*]+\*\*\s*$", block):      # stand-alone bold sub-title
            pending_label = block.strip("* ").strip()
            continue
        label = pending_label or _section_label(block, heading)
        pending_label = ""
        lines = block.splitlines()
        if all(re.match(r"^\s*[-*•]\s+", ln) for ln in lines):   # bullet list -> one chunk per bullet
            for ln in lines:
                add(label, re.sub(r"^\s*[-*•]\s+", "", ln).strip())
        else:
            add(label, block)
    return chunks


def chunk_pdf(doc_id: str, path: Path) -> tuple[str, list[Chunk]]:
    """Extract text per page and chunk by paragraph, labelling chunks with the page number."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise DocumentLoadError(
            f"{path.name} is a PDF but the 'pypdf' package is not installed. "
            "Run: pip install -r requirements.txt"
        ) from exc
    reader = PdfReader(str(path))
    chunks: list[Chunk] = []
    full_text: list[str] = []
    n = 0
    for page_no, page in enumerate(reader.pages, start=1):
        page_text = (page.extract_text() or "").strip()
        full_text.append(page_text)
        for para in re.split(r"\n\s*\n", page_text):
            para = para.strip()
            if para:
                n += 1
                chunks.append(Chunk(f"{doc_id}.{n}", f"p. {page_no}", para))
    if not any(full_text):
        raise DocumentLoadError(
            f"{path.name}: no extractable text (scanned PDF?). OCR is not supported; "
            "supply a text version of this document."
        )
    return "\n\n".join(full_text), chunks


# --------------------------------------------------------------------------- loading

def load_document(path: Path, doc_id: str) -> Document:
    ext = path.suffix.lower()
    if ext == ".pdf":
        # PDFs have no text header; metadata must come from a sidecar <name>.meta.txt
        sidecar = path.with_suffix(".meta.txt")
        if not sidecar.exists():
            raise DocumentLoadError(
                f"{path.name}: PDFs need a sidecar metadata file named {sidecar.name} "
                "with lines: source:, url:, published: (YYYY-MM-DD)."
            )
        meta, _ = parse_metadata(sidecar.read_text(encoding="utf-8"))
        body, chunks = chunk_pdf(doc_id, path)
    else:
        text = path.read_text(encoding="utf-8", errors="replace")
        meta, body = parse_metadata(text)
        chunks = chunk_text(doc_id, body)

    missing = [k for k in REQUIRED_METADATA if not meta.get(k)]
    if missing:
        raise DocumentLoadError(
            f"{path.name}: missing required metadata field(s): {', '.join(missing)}. "
            "Each document must start with source:, url: and published: (YYYY-MM-DD)."
        )
    try:
        published = parse_date(meta["published"])
    except ValueError as exc:
        raise DocumentLoadError(f"{path.name}: {exc}") from exc

    if not chunks:
        raise DocumentLoadError(f"{path.name}: document body is empty.")

    return Document(
        doc_id=doc_id,
        filename=path.name,
        source=meta["source"],
        url=meta["url"],
        published=published,
        doc_type=meta.get("type", "unspecified"),
        body=body,
        chunks=chunks,
    )


def load_research_pack(directory: str | Path) -> list[Document]:
    """Load every supported file in `directory`, assigning stable IDs S1, S2, ...

    IDs are assigned in sorted-filename order so they are reproducible between runs.
    """
    directory = Path(directory)
    if not directory.is_dir():
        raise DocumentLoadError(
            f"Research-pack directory not found: {directory}. "
            "Create it and place the source documents inside (see research_pack/README.md)."
        )
    files = sorted(
        p for p in directory.iterdir()
        if p.is_file()
        and p.suffix.lower() in SUPPORTED_EXTENSIONS
        and p.name.lower() != "readme.md"
        and not p.name.lower().endswith(".meta.txt")
        and not p.name.startswith(".")
    )
    if not files:
        raise DocumentLoadError(
            f"No supported documents (.md, .txt, .pdf) found in {directory}. "
            "Place the research-pack files there (see research_pack/README.md)."
        )
    return [load_document(p, f"S{i}") for i, p in enumerate(files, start=1)]
