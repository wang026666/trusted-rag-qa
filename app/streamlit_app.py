"""Banking regulatory intelligence platform built on the trusted RAG engine."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.components import NAV_ITEMS, render_footer, render_sidebar, render_topbar
from app.data_presenter import build_runtime_context
from app.session_state import initialize_session, navigate
from app.ui_theme import BANK_PLATFORM_CSS
from app.views.dashboard import render_dashboard
from app.views.evidence import render_evidence
from app.views.knowledge_base import render_knowledge_base
from app.views.report_analysis import render_report_analysis
from app.views.trusted_qa import render_trusted_qa
from src.config.settings import get_settings
from src.generator.llm import create_llm_from_settings
from src.generator.unified_engine import build_unified_engine


PAGE_TITLES = dict(NAV_ITEMS)


@st.cache_resource(show_spinner=False)
def _load_engine():
    settings = get_settings()
    return build_unified_engine(settings, llm=create_llm_from_settings(settings))


@st.cache_data(show_spinner=False)
def _load_runtime_context() -> dict[str, Any]:
    return build_runtime_context(PROJECT_ROOT)


def _answer_question(question: str) -> dict[str, Any]:
    return _load_engine().answer(question).to_dict()


def _navigate(page: str, prefill: str | None = None) -> None:
    navigate(st.session_state, page, prefill=prefill)


def _render_active_page(context: dict[str, Any]) -> None:
    active_page = st.session_state["active_page"]
    index_ready = bool(context.get("health", {}).get("ready"))
    if active_page == "dashboard":
        render_dashboard(
            context,
            session_question_count=int(st.session_state.get("session_question_count", 0)),
            on_query=lambda question: _navigate("trusted_qa", prefill=question),
        )
    elif active_page == "trusted_qa":
        render_trusted_qa(
            answer_question=_answer_question,
            index_ready=index_ready,
            on_evidence=lambda: _navigate("evidence"),
        )
    elif active_page == "report_analysis":
        render_report_analysis(on_query=lambda question: _navigate("trusted_qa", prefill=question))
    elif active_page == "evidence":
        render_evidence(on_back=lambda: _navigate("trusted_qa"))
    elif active_page == "knowledge_base":
        render_knowledge_base(context)


def main() -> None:
    st.set_page_config(
        page_title="银行可信RAG监管智能分析平台",
        page_icon="规",
        layout="wide",
        initial_sidebar_state="auto",
    )
    st.markdown(BANK_PLATFORM_CSS, unsafe_allow_html=True)
    initialize_session(st.session_state)
    context = _load_runtime_context()
    index_ready = bool(context.get("health", {}).get("ready"))
    active_page = st.session_state["active_page"]
    render_sidebar(active_page, index_ready, on_navigate=_navigate)
    render_topbar(PAGE_TITLES[active_page], index_ready)
    if not index_ready:
        st.warning("预构建索引不完整：可继续查看只读页面，问答功能已禁用。请检查 outputs/indexes/ 中的 BM25 和向量索引。")
    _render_active_page(context)
    render_footer()


if __name__ == "__main__":
    main()
