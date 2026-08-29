from __future__ import annotations

import re


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 120) -> list[str]:
    text = normalize_text(text)
    if not text:
        return []
    if chunk_size <= overlap:
        raise ValueError("chunk_size must be greater than overlap")
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(text):
            break
        start = end - overlap
    return chunks


def section_hint(text: str) -> str:
    text = normalize_text(text)
    match = re.match(r"^((第[一二三四五六七八九十百零\d]+[章节条款])|([一二三四五六七八九十]+、)|（[一二三四五六七八九十\d]+）)", text)
    return match.group(0) if match else ""
