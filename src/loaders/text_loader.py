from __future__ import annotations

from pathlib import Path

from src.preprocess.chunking import chunk_text, normalize_text, section_hint


def make_chunk(
    path: Path,
    metadata: dict,
    text: str,
    chunk_id: str,
    page: str = "",
    section: str = "",
    extra: dict | None = None,
) -> dict:
    payload = {
        "chunk_id": chunk_id,
        "doc_id": metadata.get("doc_id", path.stem),
        "source_title": metadata.get("source_title") or metadata.get("title") or path.stem,
        "file_path": metadata.get("relative_path") or metadata.get("file_label") or path.name,
        "file_label": metadata.get("file_label", path.name),
        "file_type": path.suffix.lower().lstrip("."),
        "page": page,
        "section": section,
        "sheet_name": "",
        "cell": "",
        "row": "",
        "column": "",
        "text": normalize_text(text),
    }
    if extra:
        payload.update(extra)
    return payload


def load_txt(path: Path, metadata: dict, chunk_size: int = 800) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    chunks = []
    for idx, part in enumerate(chunk_text(text, chunk_size=chunk_size), start=1):
        chunks.append(
            make_chunk(
                path,
                metadata,
                part,
                f"{metadata.get('doc_id', path.stem)}::txt::{idx}",
                section=section_hint(part),
            )
        )
    return chunks
