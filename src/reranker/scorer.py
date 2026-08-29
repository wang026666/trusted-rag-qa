from __future__ import annotations

from collections import OrderedDict
import re

from src.retriever.tokenize import tokenize


_MULTI_FACT_MARKERS = ("；", "分别", "两项", "均属于", "同时", "以及", "组合")


def _current_row_text(text: str) -> str:
    return re.split(r"；上文表头/相邻行：|；上文表头", text or "", maxsplit=1)[0]


def _numeric_terms(text: str) -> set[str]:
    return set(re.findall(r"-?\d+(?:\.\d+)?%?", text or ""))


class EvidenceReranker:
    """Feature-based reranker for deterministic local runs."""

    def score(self, query: str, item: dict) -> float:
        text = item.get("text", "")
        current = _current_row_text(text)
        query_tokens = [token for token in tokenize(query) if len(token) >= 2]
        if not query_tokens:
            return 0.0
        full_hits = sum(1 for token in query_tokens if token in text)
        current_hits = sum(1 for token in query_tokens if token in current)
        coverage = full_hits / len(query_tokens)
        current_coverage = current_hits / len(query_tokens)
        phrase_bonus = 0.0
        for phrase in re.findall(r"[\u4e00-\u9fffA-Za-z0-9（）()、-]{3,}", query):
            if phrase and phrase in current:
                phrase_bonus += 2.0
            elif phrase and phrase in text:
                phrase_bonus += 0.5
        numeric_bonus = 0.2 * len(_numeric_terms(query) & _numeric_terms(text))
        return round(coverage * 6.0 + current_coverage * 8.0 + phrase_bonus + numeric_bonus, 6)

    def rerank(self, query: str, evidence: list[dict], profile: str = "") -> list[dict]:
        reranked: list[dict] = []
        for item in evidence:
            copied = dict(item)
            original_score = float(copied.get("score", 0.0))
            rerank_score = self.score(query, copied)
            copied["pre_rerank_score"] = round(original_score, 6)
            copied["rerank_score"] = rerank_score
            copied["score"] = round(original_score * 0.05 + rerank_score * 10.0, 6)
            reranked.append(copied)
        reranked.sort(key=lambda item: item.get("score", 0.0), reverse=True)
        return reranked


class NeuralReranker:
    """Optional cross-encoder/FlagEmbedding reranker with local-score fallback fields."""

    def __init__(
        self,
        score_pairs=None,
        provider_name: str = "sentence_transformers",
        model_name: str = "",
        max_candidates: int = 20,
        cache_size: int = 50000,
        policy: str = "always",
    ):
        self.provider_name = provider_name
        self.model_name = model_name
        self.max_candidates = max(1, int(max_candidates))
        self.cache_size = max(0, int(cache_size))
        self.policy = policy
        self._score_cache: OrderedDict[tuple[str, str, str], float] = OrderedDict()
        self.local = EvidenceReranker()
        self.score_pairs = score_pairs or self._load_score_pairs(provider_name, model_name)

    @staticmethod
    def _load_score_pairs(provider_name: str, model_name: str):
        provider = provider_name.lower()
        if not model_name:
            raise ValueError("FINTECH_RAG_RERANKER_MODEL is required for neural reranking.")
        if provider == "sentence_transformers":
            try:
                from sentence_transformers import CrossEncoder
            except ImportError as exc:
                raise RuntimeError(
                    "sentence-transformers is not installed. Install it before setting "
                    "FINTECH_RAG_RERANKER_PROVIDER=sentence_transformers."
                ) from exc
            model = CrossEncoder(model_name)

            def score(pairs):
                values = model.predict(pairs)
                return values.tolist() if hasattr(values, "tolist") else list(values)

            return score
        if provider == "flag_embedding":
            try:
                from FlagEmbedding import FlagReranker
            except ImportError as exc:
                raise RuntimeError(
                    "FlagEmbedding is not installed. Install it before setting "
                    "FINTECH_RAG_RERANKER_PROVIDER=flag_embedding."
                ) from exc
            model = FlagReranker(model_name, use_fp16=True)

            def score(pairs):
                values = model.compute_score(pairs, normalize=True)
                if isinstance(values, (int, float)):
                    return [float(values)]
                return values.tolist() if hasattr(values, "tolist") else list(values)

            return score
        raise ValueError(f"Unsupported reranker provider: {provider_name}")

    def _preselect(self, query: str, evidence: list[dict]) -> list[dict]:
        scored = []
        for item in evidence:
            original_score = float(item.get("score", 0.0))
            local_score = self.local.score(query, item)
            scored.append((original_score * 0.05 + local_score * 10.0, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in scored[: self.max_candidates]]

    @staticmethod
    def _cache_key(query: str, item: dict) -> tuple[str, str, str]:
        return query, str(item.get("chunk_id", "")), str(item.get("text", ""))

    def _neural_scores(self, query: str, evidence: list[dict]) -> list[float]:
        keys = [self._cache_key(query, item) for item in evidence]
        scores: list[float | None] = [None] * len(evidence)
        missing_indices = []
        missing_pairs = []
        for index, (key, item) in enumerate(zip(keys, evidence)):
            if key in self._score_cache:
                scores[index] = self._score_cache[key]
                self._score_cache.move_to_end(key)
            else:
                missing_indices.append(index)
                missing_pairs.append((query, item.get("text", "")))

        if missing_pairs:
            computed = [float(score) for score in self.score_pairs(missing_pairs)]
            if len(computed) != len(missing_pairs):
                raise RuntimeError(
                    f"Reranker returned {len(computed)} scores for {len(missing_pairs)} pairs."
                )
            for index, score in zip(missing_indices, computed):
                scores[index] = score
                if self.cache_size:
                    key = keys[index]
                    self._score_cache[key] = score
                    self._score_cache.move_to_end(key)
                    while len(self._score_cache) > self.cache_size:
                        self._score_cache.popitem(last=False)
        return [float(score) for score in scores]

    def rerank(self, query: str, evidence: list[dict], profile: str = "") -> list[dict]:
        is_multi_fact = profile == "multi_fact" or any(
            marker in query for marker in _MULTI_FACT_MARKERS
        )
        if self.policy == "multi_fact" and not is_multi_fact:
            return self.local.rerank(query, evidence)
        selected = self._preselect(query, evidence)
        neural_scores = self._neural_scores(query, selected) if selected else []
        reranked: list[dict] = []
        for item, neural_score in zip(selected, neural_scores):
            copied = dict(item)
            original_score = float(copied.get("score", 0.0))
            local_score = self.local.score(query, copied)
            copied["pre_rerank_score"] = round(original_score, 6)
            copied["local_rerank_score"] = local_score
            copied["neural_rerank_score"] = round(neural_score, 6)
            copied["rerank_score"] = round(local_score + neural_score, 6)
            copied["reranker_provider"] = self.provider_name
            copied["rerank_candidate_count"] = len(selected)
            copied["score"] = round(original_score * 0.01 + local_score * 2.0 + neural_score * 100.0, 6)
            reranked.append(copied)
        reranked.sort(key=lambda item: item.get("score", 0.0), reverse=True)
        return reranked


def create_reranker_from_settings(settings):
    provider = (getattr(settings, "reranker_provider", "local") or "local").lower()
    if provider in {"", "none", "local", "feature"}:
        return EvidenceReranker()
    return NeuralReranker(
        provider_name=provider,
        model_name=getattr(settings, "reranker_model", ""),
        max_candidates=getattr(settings, "reranker_top_n", 20),
        policy=getattr(settings, "reranker_policy", "always"),
    )
