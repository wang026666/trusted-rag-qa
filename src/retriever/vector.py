from __future__ import annotations

import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Protocol

from src.retriever.tokenize import tokenize
from src.utils.io import read_json, write_json


class EmbeddingProvider(Protocol):
    provider_name: str
    model_name: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        ...

    def embed_query(self, text: str) -> list[float]:
        ...


class SentenceTransformersEmbeddingProvider:
    """Optional neural embedding provider loaded only when explicitly enabled."""

    provider_name = "sentence_transformers"

    def __init__(self, model_name: str, batch_size: int = 32, device: str = ""):
        if not model_name:
            raise ValueError("FINTECH_RAG_EMBEDDING_MODEL is required for sentence_transformers.")
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers is not installed. Install it before setting "
                "FINTECH_RAG_EMBEDDING_PROVIDER=sentence_transformers."
            ) from exc
        self.model_name = model_name
        self.batch_size = batch_size
        kwargs = {"device": device} if device else {}
        self.model = SentenceTransformer(model_name, **kwargs)

    @staticmethod
    def _as_list(vectors) -> list[list[float]]:
        if hasattr(vectors, "tolist"):
            return vectors.tolist()
        return [list(vector) for vector in vectors]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = self.model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return self._as_list(vectors)

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def create_embedding_provider_from_settings(settings) -> EmbeddingProvider | None:
    provider = (getattr(settings, "embedding_provider", "local_tfidf") or "local_tfidf").lower()
    if provider in {"", "none", "local", "local_tfidf", "tfidf"}:
        return None
    if provider == "sentence_transformers":
        return SentenceTransformersEmbeddingProvider(
            getattr(settings, "embedding_model", ""),
            batch_size=getattr(settings, "embedding_batch_size", 32),
            device=getattr(settings, "embedding_device", ""),
        )
    raise ValueError(f"Unsupported embedding provider: {provider}")


class SparseVectorIndex:
    """Local vector fallback based on TF-IDF cosine similarity.

    This is not a neural embedding model. It provides a deterministic vector
    retrieval path that works without network access or model downloads, while
    keeping the same save/load boundary needed for a later embedding backend.
    """

    def __init__(self, documents: list[dict]):
        self.documents = documents
        doc_tokens = [tokenize(self._index_text(doc)) for doc in documents]
        self.doc_freqs: dict[str, int] = defaultdict(int)
        self.postings: dict[str, list[int]] = defaultdict(list)
        for index, tokens in enumerate(doc_tokens):
            for token in set(tokens):
                self.doc_freqs[token] += 1
                self.postings[token].append(index)
        self.doc_vectors = [self._build_vector(tokens) for tokens in doc_tokens]
        self.doc_norms = [self._norm(vector) for vector in self.doc_vectors]

    def share_static_corpus(self, bm25) -> None:
        """Reuse immutable document and vocabulary structures from BM25.

        The local TF-IDF and BM25 index texts differ only in metadata term
        repetition, so their document-frequency and postings sets are equal.
        Sharing them retains ranking semantics while releasing duplicate
        document metadata and vocabulary structures.
        """
        if len(self.documents) != len(bm25.documents):
            return
        if any(
            left.get("chunk_id") != right.get("chunk_id")
            for left, right in zip(self.documents, bm25.documents)
        ):
            return
        if self.doc_freqs != bm25.doc_freqs or self.postings != bm25.postings:
            return
        self.documents = bm25.documents
        self.doc_freqs = bm25.doc_freqs
        self.postings = bm25.postings

    @staticmethod
    def _index_text(doc: dict) -> str:
        metadata = " ".join(
            str(doc.get(key, ""))
            for key in ("source_title", "file_label", "file_type", "section", "sheet_name")
        )
        return f"{metadata} {metadata} {doc.get('text', '')}"

    def _idf(self, token: str) -> float:
        total = len(self.documents)
        df = self.doc_freqs.get(token, 0)
        return math.log((total + 1) / (df + 1)) + 1.0 if total else 0.0

    def _build_vector(self, tokens: list[str]) -> dict[str, float]:
        counts = Counter(tokens)
        if not counts:
            return {}
        max_tf = max(counts.values())
        return {
            token: (0.5 + 0.5 * count / max_tf) * self._idf(token)
            for token, count in counts.items()
        }

    @staticmethod
    def _norm(vector: dict[str, float]) -> float:
        return math.sqrt(sum(value * value for value in vector.values()))

    @staticmethod
    def _dot(left: dict[str, float], right: dict[str, float]) -> float:
        if len(left) > len(right):
            left, right = right, left
        return sum(value * right.get(token, 0.0) for token, value in left.items())

    def search(
        self,
        query: str,
        top_k: int = 5,
        filters: dict[str, str] | None = None,
    ) -> list[dict]:
        query_tokens = tokenize(query)
        query_vector = self._build_vector(query_tokens)
        query_norm = self._norm(query_vector)
        if not query_vector or not query_norm:
            return []
        filters = filters or {}
        candidate_ids: set[int] = set()
        for token in set(query_tokens):
            candidate_ids.update(self.postings.get(token, []))
        scored: list[tuple[float, int, dict]] = []
        for index in candidate_ids:
            doc = self.documents[index]
            if any(str(doc.get(key, "")) != str(value) for key, value in filters.items() if value):
                continue
            doc_norm = self.doc_norms[index]
            if not doc_norm:
                continue
            score = self._dot(query_vector, self.doc_vectors[index]) / (query_norm * doc_norm)
            if score > 0:
                item = dict(doc)
                item["vector_score"] = round(score, 6)
                scored.append((score, index, item))
        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        return [item for _, _, item in scored[:top_k]]

    def save(self, path: Path) -> None:
        write_json(path, {"documents": self.documents, "backend": "local_tfidf"})

    @classmethod
    def load(cls, path: Path) -> "SparseVectorIndex":
        data = read_json(path)
        return cls(data["documents"])


def _cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


class DenseVectorIndex:
    """Dense embedding index for optional local neural embedding backends."""

    backend = "dense_embedding"

    def __init__(
        self,
        documents: list[dict],
        vectors: list[list[float]],
        embedding_provider: EmbeddingProvider,
        provider_name: str = "",
        model_name: str = "",
    ):
        if len(documents) != len(vectors):
            raise ValueError("documents and vectors must have the same length.")
        self.documents = documents
        self.vectors = [[float(value) for value in vector] for vector in vectors]
        self.embedding_provider = embedding_provider
        self.provider_name = provider_name or getattr(embedding_provider, "provider_name", "unknown")
        self.model_name = model_name or getattr(embedding_provider, "model_name", "")
        self._query_cache: dict[str, list[float]] = {}
        self._np = None
        self._matrix = None
        self._matrix_norms = None
        try:
            import numpy as np

            self._np = np
            self._matrix = np.asarray(self.vectors, dtype="float32")
            self._matrix_norms = np.linalg.norm(self._matrix, axis=1)
        except Exception:
            self._np = None

    @classmethod
    def build(cls, documents: list[dict], embedding_provider: EmbeddingProvider) -> "DenseVectorIndex":
        texts = [SparseVectorIndex._index_text(doc) for doc in documents]
        vectors = embedding_provider.embed_documents(texts)
        return cls(documents, vectors, embedding_provider)

    def search(
        self,
        query: str,
        top_k: int = 5,
        filters: dict[str, str] | None = None,
        max_candidates: int = 0,
    ) -> list[dict]:
        del max_candidates
        filters = filters or {}
        query_vector = self._query_cache.get(query)
        if query_vector is None:
            query_vector = [float(value) for value in self.embedding_provider.embed_query(query)]
            self._query_cache[query] = query_vector
        scored: list[tuple[float, int, dict]] = []
        for index, score in self._dense_scores(query_vector):
            doc = self.documents[index]
            if any(str(doc.get(key, "")) != str(value) for key, value in filters.items() if value):
                continue
            if score > 0:
                item = dict(doc)
                item["vector_score"] = round(score, 6)
                item["vector_backend"] = self.provider_name
                item["retrieval_channels"] = ["vector"]
                scored.append((score, index, item))
                if len(scored) >= top_k and not filters:
                    break
        if filters:
            scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, _, item in scored[:top_k]]

    def _dense_scores(self, query_vector: list[float]) -> list[tuple[int, float]]:
        if self._np is not None and self._matrix is not None and self._matrix_norms is not None:
            np = self._np
            query = np.asarray(query_vector, dtype="float32")
            query_norm = float(np.linalg.norm(query))
            if query_norm <= 0:
                return []
            denom = self._matrix_norms * query_norm
            scores = np.divide(
                self._matrix @ query,
                denom,
                out=np.zeros_like(self._matrix_norms, dtype="float32"),
                where=denom > 0,
            )
            order = np.argsort(scores)[::-1]
            return [(int(index), float(scores[index])) for index in order if scores[index] > 0]
        scored = [
            (index, _cosine(query_vector, vector))
            for index, vector in enumerate(self.vectors)
        ]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return [(index, score) for index, score in scored if score > 0]

    def save(self, path: Path) -> None:
        write_json(
            path,
            {
                "backend": self.backend,
                "provider_name": self.provider_name,
                "model_name": self.model_name,
                "documents": self.documents,
                "vectors": self.vectors,
            },
        )

    @classmethod
    def load(cls, path: Path, embedding_provider: EmbeddingProvider | None) -> "DenseVectorIndex":
        if embedding_provider is None:
            raise RuntimeError(
                "Dense vector index requires an embedding provider to encode query text."
            )
        data = read_json(path)
        return cls(
            data["documents"],
            data["vectors"],
            embedding_provider,
            provider_name=data.get("provider_name", ""),
            model_name=data.get("model_name", ""),
        )


def build_vector_index(documents: list[dict], settings) -> SparseVectorIndex | DenseVectorIndex:
    provider = create_embedding_provider_from_settings(settings)
    if provider is None:
        return SparseVectorIndex(documents)
    return DenseVectorIndex.build(documents, provider)


def load_vector_index(
    path: Path,
    embedding_provider: EmbeddingProvider | None = None,
) -> SparseVectorIndex | DenseVectorIndex:
    data = read_json(path)
    backend = data.get("backend", "local_tfidf")
    if backend == "local_tfidf":
        return SparseVectorIndex(data["documents"])
    if backend == DenseVectorIndex.backend:
        return DenseVectorIndex.load(path, embedding_provider)
    raise ValueError(f"Unsupported vector index backend: {backend}")
