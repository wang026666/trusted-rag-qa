from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config.settings import get_settings
from src.indexing.manifest import build_manifest
from src.loaders.dispatch import load_document
from src.retriever.bm25 import BM25Index
from src.retriever.vector import build_vector_index
from src.utils.io import ensure_dir, write_json, write_jsonl


def split_chunks_for_indexes(chunks: list[dict]) -> tuple[list[dict], list[dict]]:
    table_cells = [chunk for chunk in chunks if chunk.get("chunk_type") == "table_cell"]
    main_chunks = [chunk for chunk in chunks if chunk.get("chunk_type") != "table_cell"]
    return main_chunks, table_cells


def main() -> int:
    parser = argparse.ArgumentParser(description="Build fintech RAG index.")
    parser.add_argument("--attachments-dir", type=Path, default=None)
    parser.add_argument("--processed-dir", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    settings = get_settings()
    attachments_dir = args.attachments_dir or settings.attachments_dir
    if attachments_dir is None:
        parser.error("请通过 --attachments-dir 指定原始资料目录")
    processed_dir = args.processed_dir or settings.processed_dir
    ensure_dir(processed_dir)
    ensure_dir(settings.index_dir)

    manifest = build_manifest(attachments_dir)
    if args.limit:
        manifest = manifest[: args.limit]

    chunks: list[dict] = []
    failures: list[dict] = []
    for record in manifest:
        path = Path(record["local_path"])
        metadata = {**record, "source_title": record["title"]}
        try:
            chunks.extend(load_document(path, metadata))
        except Exception as exc:
            failures.append(
                {
                    "doc_id": record["doc_id"],
                    "file_path": record["local_path"],
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    main_chunks, table_cells = split_chunks_for_indexes(chunks)

    write_jsonl(processed_dir / "manifest.jsonl", manifest)
    write_jsonl(processed_dir / "chunks.jsonl", chunks)
    write_jsonl(processed_dir / "main_chunks.jsonl", main_chunks)
    write_jsonl(processed_dir / "table_cells.jsonl", table_cells)
    write_jsonl(processed_dir / "parse_failures.jsonl", failures)
    BM25Index(main_chunks).save(settings.index_dir / "bm25_index.json")
    vector_index = build_vector_index(main_chunks, settings)
    vector_index.save(settings.index_dir / "vector_index.json")
    write_json(
        settings.index_dir / "index_summary.json",
        {
            "manifest_count": len(manifest),
            "chunk_count": len(chunks),
            "main_chunk_count": len(main_chunks),
            "table_cell_count": len(table_cells),
            "failure_count": len(failures),
            "vector_backend": getattr(vector_index, "backend", "local_tfidf"),
            "embedding_provider": settings.embedding_provider,
            "embedding_model": settings.embedding_model,
        },
    )
    print(
        f"manifest={len(manifest)} chunks={len(chunks)} "
        f"main_chunks={len(main_chunks)} table_cells={len(table_cells)} "
        f"failures={len(failures)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
