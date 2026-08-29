from __future__ import annotations

from pathlib import Path

from src.reranker.scorer import EvidenceReranker, create_reranker_from_settings
from src.retriever.bm25 import BM25Index
from src.retriever.vector import (
    SparseVectorIndex,
    create_embedding_provider_from_settings,
    load_vector_index,
)


class HybridRetriever:
    """BM25 + local vector retrieval with deterministic reranking."""

    def __init__(
        self,
        bm25: BM25Index,
        vector: SparseVectorIndex | None = None,
        reranker: EvidenceReranker | None = None,
    ):
        self.bm25 = bm25
        self.vector = vector
        if isinstance(self.vector, SparseVectorIndex):
            self.vector.share_static_corpus(self.bm25)
        self.reranker = reranker or EvidenceReranker()

    @classmethod
    def from_index_dir(cls, index_dir: Path, settings=None) -> "HybridRetriever":
        vector_path = index_dir / "vector_index.json"
        embedding_provider = (
            create_embedding_provider_from_settings(settings) if settings is not None else None
        )
        bm25 = BM25Index.load(index_dir / "bm25_index.json")
        vector = (
            load_vector_index(vector_path, embedding_provider=embedding_provider)
            if vector_path.exists()
            else None
        )
        reranker = create_reranker_from_settings(settings) if settings is not None else None
        return cls(bm25, vector=vector, reranker=reranker)

    @staticmethod
    def _normalize_scores(items: list[dict], key: str) -> dict[str, float]:
        scores = {
            item.get("chunk_id", ""): float(item.get(key, 0.0))
            for item in items
            if item.get("chunk_id")
        }
        max_score = max(scores.values(), default=0.0)
        if max_score <= 0:
            return {chunk_id: 0.0 for chunk_id in scores}
        return {chunk_id: score / max_score for chunk_id, score in scores.items()}

    def search(
        self,
        query: str,
        top_k: int = 5,
        filters: dict[str, str] | None = None,
        profile: str = "",
    ) -> list[dict]:
        candidate_k = max(top_k * 10, 50)
        bm25_items = self.bm25.search(query, top_k=candidate_k, filters=filters)
        vector_items = (
            self.vector.search(query, top_k=candidate_k, filters=filters) if self.vector else []
        )
        bm25_norms = self._normalize_scores(bm25_items, "score")
        vector_norms = self._normalize_scores(vector_items, "vector_score")
        merged: dict[str, dict] = {}
        for item in bm25_items:
            chunk_id = item.get("chunk_id", "")
            if not chunk_id:
                continue
            merged[chunk_id] = dict(item)
            merged[chunk_id]["bm25_score"] = item.get("score", 0.0)
            merged[chunk_id]["retrieval_channels"] = ["bm25"]
        for item in vector_items:
            chunk_id = item.get("chunk_id", "")
            if not chunk_id:
                continue
            if chunk_id not in merged:
                merged[chunk_id] = dict(item)
                merged[chunk_id]["bm25_score"] = 0.0
                merged[chunk_id]["retrieval_channels"] = []
            merged[chunk_id]["vector_score"] = item.get("vector_score", 0.0)
            merged[chunk_id]["retrieval_channels"].append("vector")
        candidates = []
        for chunk_id, item in merged.items():
            item.setdefault("vector_score", 0.0)
            fused = 0.72 * bm25_norms.get(chunk_id, 0.0) + 0.28 * vector_norms.get(chunk_id, 0.0)
            item["fusion_score"] = round(fused, 6)
            item["score"] = round(fused * 100.0, 6)
            candidates.append(item)
        return self.reranker.rerank(query, candidates, profile=profile)[:top_k]
