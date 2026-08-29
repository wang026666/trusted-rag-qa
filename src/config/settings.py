"""Runtime configuration for the standalone competition release."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    project_root: Path
    attachments_dir: Path | None
    processed_dir: Path
    index_dir: Path
    top_k: int
    min_score: float
    embedding_provider: str
    embedding_model: str
    embedding_device: str
    embedding_batch_size: int
    reranker_provider: str
    reranker_model: str
    reranker_top_n: int
    reranker_policy: str
    llm_provider: str
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_timeout: float


def _value(name: str, default: str) -> str:
    return os.getenv(name, default).strip()


def get_settings() -> Settings:
    """Return local-only defaults, with optional runtime environment overrides."""
    attachments_value = _value("FINTECH_RAG_ATTACHMENTS_DIR", "")
    return Settings(
        project_root=PROJECT_ROOT,
        attachments_dir=Path(attachments_value).expanduser() if attachments_value else None,
        processed_dir=PROJECT_ROOT / "data" / "processed",
        index_dir=PROJECT_ROOT / "outputs" / "indexes",
        top_k=int(_value("FINTECH_RAG_TOP_K", "5")),
        min_score=float(_value("FINTECH_RAG_MIN_SCORE", "0.05")),
        embedding_provider=_value("FINTECH_RAG_EMBEDDING_PROVIDER", "local_tfidf"),
        embedding_model=_value("FINTECH_RAG_EMBEDDING_MODEL", ""),
        embedding_device=_value("FINTECH_RAG_EMBEDDING_DEVICE", ""),
        embedding_batch_size=int(_value("FINTECH_RAG_EMBEDDING_BATCH_SIZE", "32")),
        reranker_provider=_value("FINTECH_RAG_RERANKER_PROVIDER", "local"),
        reranker_model=_value("FINTECH_RAG_RERANKER_MODEL", ""),
        reranker_top_n=int(_value("FINTECH_RAG_RERANKER_TOP_N", "20")),
        reranker_policy=_value("FINTECH_RAG_RERANKER_POLICY", "always"),
        llm_provider=_value("FINTECH_RAG_LLM_PROVIDER", "none"),
        llm_base_url=_value("FINTECH_RAG_LLM_BASE_URL", ""),
        llm_api_key=_value("FINTECH_RAG_LLM_API_KEY", ""),
        llm_model=_value("FINTECH_RAG_LLM_MODEL", ""),
        llm_timeout=float(_value("FINTECH_RAG_LLM_TIMEOUT", "30")),
    )
