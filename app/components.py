"""Reusable Streamlit presentation components for the banking platform."""

from __future__ import annotations

from html import escape
from typing import Any, Callable

import streamlit as st

from app.ui_theme import citation_location, format_match_score


NAV_ITEMS = (
    ("dashboard", "监管驾驶舱"),
    ("trusted_qa", "可信RAG问答"),
    ("report_analysis", "监管报表分析"),
    ("evidence", "可信解释"),
    ("knowledge_base", "知识库管理"),
)


def kpi_card_html(label: object, value: object, detail: object, mark: object) -> str:
    return (
        '<section class="br-kpi">'
        f'<div class="br-kpi-mark" aria-hidden="true">{escape(str(mark))}</div>'
        '<div class="br-kpi-body">'
        f'<div class="br-kpi-label">{escape(str(label))}</div>'
        f'<div class="br-kpi-value">{escape(str(value))}</div>'
        f'<div class="br-kpi-detail">{escape(str(detail))}</div>'
        "</div>"
        "</section>"
    )


def topbar_html(page_title: object, index_ready: bool) -> str:
    state_class = "ready" if index_ready else "fault"
    state_label = "索引就绪" if index_ready else "索引异常"
    return f"""
    <header class="br-topbar">
      <div class="br-topbar-title">{escape(str(page_title))}</div>
      <div class="br-topbar-meta">
        <span class="br-system-state {state_class}"><i></i>{state_label}</span>
        <span class="br-meta-divider"></span>
        <span class="br-role">竞赛演示环境 / 监管分析角色</span>
      </div>
    </header>
    """


def empty_state_html(title: object, detail: object, mark: object = "—") -> str:
    return f"""
    <div class="br-empty">
      <div class="br-empty-mark" aria-hidden="true">{escape(str(mark))}</div>
      <div class="br-empty-title">{escape(str(title))}</div>
      <div class="br-empty-detail">{escape(str(detail))}</div>
    </div>
    """


def process_rail_html(intent: object, has_citations: bool, answered: bool) -> str:
    stages = (
        ("问题", "已接收"),
        ("Query理解", str(intent or "未返回")),
        ("知识库检索", "已执行" if answered else "待执行"),
        ("证据采用", "已采用" if has_citations else "无采用证据"),
        ("答案生成", "已完成" if answered else "待执行"),
    )
    items = []
    for index, (label, detail) in enumerate(stages, start=1):
        active = " active" if answered and index <= 5 else ""
        items.append(
            f'<div class="br-process-step{active}"><span>{index:02d}</span>'
            f'<strong>{escape(label)}</strong><small>{escape(detail)}</small></div>'
        )
    return '<div class="br-process-rail">' + '<i class="br-process-line"></i>'.join(items) + "</div>"


def render_sidebar(active_page: str, index_ready: bool, on_navigate: Callable[[str], None]) -> None:
    with st.sidebar:
        st.markdown(
            """
            <div class="br-brand">
              <div class="br-brand-mark">规</div>
              <div><strong>银行可信RAG</strong><span>监管智能分析平台</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown('<div class="br-nav-label">业务导航</div>', unsafe_allow_html=True)
        for key, label in NAV_ITEMS:
            if st.button(
                label,
                key=f"nav_{key}",
                type="primary" if key == active_page else "secondary",
                use_container_width=True,
            ):
                on_navigate(key)
                st.rerun()
        state = "安全合规 · 索引就绪" if index_ready else "运行受限 · 索引异常"
        tone = "ready" if index_ready else "fault"
        st.markdown(
            f'<div class="br-sidebar-foot {tone}"><i></i>{escape(state)}<small>本地证据检索</small></div>',
            unsafe_allow_html=True,
        )


def render_topbar(page_title: str, index_ready: bool) -> None:
    st.markdown(topbar_html(page_title, index_ready), unsafe_allow_html=True)


def render_page_header(title: str, description: str) -> None:
    st.markdown(
        f'<div class="br-page-header"><h1>{escape(title)}</h1><p>{escape(description)}</p></div>',
        unsafe_allow_html=True,
    )


def render_kpi_card(label: object, value: object, detail: object, mark: object) -> None:
    st.markdown(kpi_card_html(label, value, detail, mark), unsafe_allow_html=True)


def render_empty_state(title: object, detail: object, mark: object = "—") -> None:
    st.markdown(empty_state_html(title, detail, mark), unsafe_allow_html=True)


def render_section_header(title: str, description: str | None = None) -> None:
    detail = f"<p>{escape(description)}</p>" if description else ""
    st.markdown(
        f'<div class="br-section-header"><h2>{escape(title)}</h2>{detail}</div>',
        unsafe_allow_html=True,
    )


def render_citation_card(citation: dict[str, Any], index: int, expanded: bool = False) -> None:
    source = citation.get("source_title") or citation.get("doc_id") or "未命名来源"
    score = format_match_score(citation.get("score"))
    location = citation_location(citation)
    path = citation.get("relative_path") or citation.get("file_path") or "未提供"
    st.markdown(
        f"""
        <div class="br-citation-head">
          <span class="br-citation-number">{index:02d}</span>
          <div><strong>{escape(str(source))}</strong><small>{escape(location)}</small></div>
        </div>
        <div class="br-citation-meta"><span>匹配分数 {escape(score)}</span><span>来源路径 {escape(str(path))}</span></div>
        """,
        unsafe_allow_html=True,
    )
    with st.expander("查看证据原文", expanded=expanded):
        st.write(citation.get("evidence") or "未提供证据原文。")


def render_footer() -> None:
    st.markdown(
        '<footer class="br-footer">回答仅在现有资料与引用证据范围内有效，不替代正式监管解释、审计意见或专业判断。</footer>',
        unsafe_allow_html=True,
    )
