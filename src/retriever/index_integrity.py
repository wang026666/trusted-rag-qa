"""Cheap structural checks for packaged retrieval indexes before they are used."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_LOCAL_TFIDF = "local_tfidf"
_DENSE_EMBEDDING = "dense_embedding"


def _load_payload(path: Path, label: str, errors: list[str]) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"缺少{label}索引文件")
        return None
    except (OSError, UnicodeError, json.JSONDecodeError):
        errors.append(f"{label}索引不是可读取的 JSON 对象")
        return None
    if not isinstance(payload, dict):
        errors.append(f"{label}索引不是 JSON 对象")
        return None
    return payload


def _validate_documents(payload: dict[str, Any] | None, label: str, errors: list[str]) -> list[dict] | None:
    if payload is None:
        return None
    documents = payload.get("documents")
    if not isinstance(documents, list) or not documents:
        errors.append(f"{label}索引缺少非空 documents 列表")
        return None
    for document in documents:
        if not isinstance(document, dict):
            errors.append(f"{label}索引包含非对象文档")
            return None
        if not isinstance(document.get("chunk_id"), str) or not document["chunk_id"].strip():
            errors.append(f"{label}索引文档缺少 chunk_id")
            return None
        if not isinstance(document.get("text"), str) or not document["text"].strip():
            errors.append(f"{label}索引文档缺少文本")
            return None
    return documents


def _validate_vector_payload(payload: dict[str, Any] | None, documents: list[dict] | None, errors: list[str]) -> bool:
    if payload is None or documents is None:
        return False
    backend = payload.get("backend", _LOCAL_TFIDF)
    if backend == _LOCAL_TFIDF:
        return True
    if backend != _DENSE_EMBEDDING:
        errors.append("向量索引使用了不支持的后端")
        return False
    vectors = payload.get("vectors")
    if not isinstance(vectors, list) or len(vectors) != len(documents):
        errors.append("稠密向量索引的 vectors 与 documents 不一致")
        return False
    if any(
        not isinstance(vector, list)
        or not vector
        or any(not isinstance(value, (int, float)) or isinstance(value, bool) for value in vector)
        for vector in vectors
    ):
        errors.append("稠密向量索引包含无效向量")
        return False
    return True


def inspect_index_directory(index_dir: Path) -> dict[str, object]:
    """Return safe readiness state without constructing the full retrieval indexes."""
    errors: list[str] = []
    bm25_payload = _load_payload(index_dir / "bm25_index.json", "BM25", errors)
    vector_payload = _load_payload(index_dir / "vector_index.json", "向量", errors)
    bm25_documents = _validate_documents(bm25_payload, "BM25", errors)
    vector_documents = _validate_documents(vector_payload, "向量", errors)

    bm25_ready = bm25_documents is not None
    vector_ready = _validate_vector_payload(vector_payload, vector_documents, errors)
    if bm25_documents is not None and vector_documents is not None:
        bm25_ids = [document["chunk_id"] for document in bm25_documents]
        vector_ids = [document["chunk_id"] for document in vector_documents]
        if bm25_ids != vector_ids:
            errors.append("BM25 与向量索引的文档顺序或标识不一致")

    return {
        "ready": bm25_ready and vector_ready and not errors,
        "bm25_ready": bm25_ready,
        "vector_ready": vector_ready,
        "document_count": len(bm25_documents) if bm25_documents is not None else 0,
        "errors": tuple(errors),
    }
