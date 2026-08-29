from __future__ import annotations

from pathlib import Path

from src.loaders.text_loader import make_chunk
from src.preprocess.chunking import chunk_text, normalize_text, section_hint


def load_pdf(path: Path, metadata: dict) -> list[dict]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("pypdf is required to parse .pdf files") from exc

    reader = PdfReader(str(path))
    chunks: list[dict] = []
    for page_index, page in enumerate(reader.pages, start=1):
        text = normalize_text(page.extract_text() or "")
        if not text:
            continue
        for part_index, part in enumerate(chunk_text(text, chunk_size=900), start=1):
            chunks.append(
                make_chunk(
                    path,
                    metadata,
                    part,
                    f"{metadata.get('doc_id', path.stem)}::page::{page_index}::{part_index}",
                    page=str(page_index),
                    section=section_hint(part),
                )
            )
    return chunks
