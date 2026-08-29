from __future__ import annotations

import math
import heapq
from collections import Counter, defaultdict
from pathlib import Path

from src.retriever.tokenize import tokenize
from src.utils.io import read_json, write_json


def _norm_metadata(text: str) -> str:
    return "".join(ch for ch in str(text or "").lower() if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")


class BM25Index:
    def __init__(self, documents: list[dict], k1: float = 1.5, b: float = 0.75):
        self.documents = documents
        self.k1 = k1
        self.b = b
        doc_tokens = [tokenize(self._index_text(doc)) for doc in documents]
        self.doc_lengths = [len(tokens) for tokens in doc_tokens]
        self.avgdl = sum(self.doc_lengths) / len(self.doc_lengths) if self.doc_lengths else 0
        self.term_freqs = [Counter(tokens) for tokens in doc_tokens]
        self.doc_freqs: dict[str, int] = defaultdict(int)
        self.postings: dict[str, list[int]] = defaultdict(list)
        for tokens in doc_tokens:
            for token in set(tokens):
                self.doc_freqs[token] += 1
        for index, tokens in enumerate(doc_tokens):
            for token in set(tokens):
                self.postings[token].append(index)
        self.metadata_norms: list[list[str]] = [
            [
                norm
                for norm in (
                    _norm_metadata(doc.get("source_title", "")),
                    _norm_metadata(doc.get("file_label", "")),
                )
                if norm
            ]
            for doc in documents
        ]

    @staticmethod
    def _index_text(doc: dict) -> str:
        metadata = " ".join(
            str(doc.get(key, ""))
            for key in ("source_title", "file_label", "file_type", "section", "sheet_name")
        )
        # Metadata is weighted because regulatory questions often identify the
        # authoritative file before asking for a fact inside it.
        return f"{metadata} {metadata} {metadata} {doc.get('text', '')}"

    def _idf(self, term: str) -> float:
        n = len(self.documents)
        df = self.doc_freqs.get(term, 0)
        return math.log(1 + (n - df + 0.5) / (df + 0.5)) if n else 0.0

    def _score_doc(self, query_tokens: list[str], index: int) -> float:
        if not self.avgdl:
            return 0.0
        score = 0.0
        freqs = self.term_freqs[index]
        dl = self.doc_lengths[index]
        for term in query_tokens:
            tf = freqs.get(term, 0)
            if tf == 0:
                continue
            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
            score += self._idf(term) * numerator / denominator
        return score

    def _forced_metadata_candidates(self, query: str) -> set[int]:
        query_norm = _norm_metadata(query)
        if not query_norm:
            return set()
        candidates: set[int] = set()
        for idx, metadata_norms in enumerate(self.metadata_norms):
            if any(norm in query_norm for norm in metadata_norms):
                candidates.add(idx)
        return candidates

    def _metadata_bonus(self, query: str, index: int) -> float:
        query_norm = _norm_metadata(query)
        if any(norm in query_norm for norm in self.metadata_norms[index]):
            return 500.0
        return 0.0

    def search(
        self,
        query: str,
        top_k: int = 5,
        filters: dict[str, str] | None = None,
        max_candidates: int = 1200,
    ) -> list[dict]:
        query_tokens = tokenize(query)
        filters = filters or {}
        candidate_scores: dict[int, float] = defaultdict(float)
        for term in set(query_tokens):
            idf = self._idf(term)
            for idx in self.postings.get(term, []):
                candidate_scores[idx] += idf
        candidates = [
            idx
            for idx, _ in heapq.nlargest(
                max_candidates, candidate_scores.items(), key=lambda item: item[1]
            )
        ]
        forced = self._forced_metadata_candidates(query)
        if forced:
            candidates = list(dict.fromkeys(list(forced) + candidates))
        scored: list[tuple[float, dict]] = []
        for idx in candidates:
            doc = self.documents[idx]
            if any(str(doc.get(key, "")) != str(value) for key, value in filters.items() if value):
                continue
            score = self._score_doc(query_tokens, idx) + self._metadata_bonus(query, idx)
            if score > 0:
                item = dict(doc)
                item["score"] = round(score, 6)
                scored.append((score, item))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:top_k]]

    def save(self, path: Path) -> None:
        write_json(
            path,
            {
                "documents": self.documents,
                "k1": self.k1,
                "b": self.b,
            },
        )

    @classmethod
    def load(cls, path: Path) -> "BM25Index":
        data = read_json(path)
        return cls(data["documents"], k1=data.get("k1", 1.5), b=data.get("b", 0.75))
