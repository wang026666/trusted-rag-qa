"""Evidence-first regulatory Q&A workspace."""

from __future__ import annotations

from html import escape
from typing import Any, Callable

import streamlit as st

from app.components import render_citation_card, render_empty_state, render_page_header, render_section_header
from app.session_state import record_answer, select_history, selected_result
from app.ui_theme import (
    backend_label,
    citations_for_display,
    confidence_presentation,
    consistency_label,
    coverage_presentation,
    intent_label,
    status_presentation,
)


def _history_panel() -> None:
    render_section_header("本次会话", "仅保留当前页面会话")
    st.markdown(
        '<div class="br-history-note">刷新、关闭页面或重启系统后，这些记录可能清空；它们不是持久化审计日志。</div>',
        unsafe_allow_html=True,
    )
    history = st.session_state.get("qa_history") or []
    if not history:
        st.markdown('<div class="br-history-empty">尚无本次会话记录</div>', unsafe_allow_html=True)
        return
    for entry in reversed(history):
        sequence = int(entry.get("sequence") or 0)
        question = str(entry.get("question") or "未命名问题")
        selected = entry.get("id") == st.session_state.get("selected_qa_id")
        label = f"{sequence:02d} · {question}"
        if st.button(
            label,
            key=f"history_{entry.get('id')}",
            type="primary" if selected else "secondary",
            use_container_width=True,
            help=f"状态：{status_presentation(entry.get('status'), 0)['label']}",
        ):
            select_history(st.session_state, str(entry.get("id")))
            st.rerun()


def _answer_panel(payload: dict[str, Any] | None) -> None:
    if not payload:
        render_empty_state(
            "尚未开始智能核验",
            "输入监管制度或统计报表问题，系统将在现有资料范围内检索并回答。",
            "问",
        )
        return
    citations = citations_for_display(payload)
    status = status_presentation(payload.get("status"), len(citations))
    st.markdown(
        f"""
        <div class="br-trust-strip">
          <div><span>问题类型</span><strong>{escape(intent_label(payload.get('intent')))}</strong></div>
          <div><span>核验状态</span><strong>{escape(status['label'])}</strong></div>
          <div><span>生成方式</span><strong>{escape(backend_label(payload.get('generation_backend')))}</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    render_section_header("核验结论")
    answer = escape(str(payload.get("answer") or "未提供回答。"))
    st.markdown(f'<div class="br-answer-copy">{answer}</div>', unsafe_allow_html=True)
    boundary = payload.get("refusal_reason") or "本回答仅在当前引用证据和已收录资料范围内成立，需结合正式制度原文审阅。"
    st.markdown(
        f'<div class="br-boundary"><strong>回答边界</strong><br>{escape(str(boundary))}</div>',
        unsafe_allow_html=True,
    )


def _evidence_panel(payload: dict[str, Any] | None, on_evidence: Callable[[], None]) -> None:
    render_section_header("可信证据链", "只展示当前回答实际采用的证据")
    if not payload:
        render_empty_state("尚无证据链", "完成一次问答后显示证据覆盖、一致性与引用来源。", "证")
        return
    citations = citations_for_display(payload)
    coverage = coverage_presentation(payload.get("support_coverage"))
    confidence = confidence_presentation(payload.get("confidence"))
    st.markdown(
        f"""
        <div class="br-trust-hero">
          <span>{escape(coverage['label'])}</span><strong>{escape(coverage['value'])}</strong>
          <small>{escape(coverage['detail'])}</small>
        </div>
        <div class="br-trust-strip">
          <div><span>可信等级</span><strong>{escape(confidence['label'])}</strong></div>
          <div><span>一致性</span><strong>{escape(consistency_label(payload.get('consistency_status')))}</strong></div>
          <div><span>实际引用</span><strong>{len(citations)} 条</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if citations:
        for index, citation in enumerate(citations, start=1):
            render_citation_card(citation, index, expanded=index == 1)
        if st.button("查看完整可信解释", key="open_evidence", use_container_width=True):
            on_evidence()
            st.rerun()
    else:
        st.info("本次回答未形成可引用证据，不展示无关检索片段。")


def render_trusted_qa(
    answer_question: Callable[[str], dict[str, Any]],
    index_ready: bool,
    on_evidence: Callable[[], None],
) -> None:
    render_page_header("可信RAG智能问答", "从监管问题、核验结论到实际引用证据的一体化工作台。")
    history_column, answer_column, evidence_column = st.columns([.78, 1.65, 1.05], gap="medium")
    with history_column:
        with st.container(border=True):
            _history_panel()
    with answer_column:
        with st.container(border=True):
            render_section_header("智能核验", "现有引擎检索与回答")
            with st.form("trusted_qa_form", clear_on_submit=False):
                question = st.text_area(
                    "请输入监管相关问题",
                    key="question_input",
                    placeholder="例如：商业银行应当制定什么账簿划分政策？",
                    height=132,
                )
                submitted = st.form_submit_button(
                    "开始核验",
                    type="primary",
                    use_container_width=True,
                    disabled=not index_ready,
                )
            if submitted:
                if not question.strip():
                    st.warning("请输入问题后再开始核验。")
                else:
                    try:
                        with st.spinner("正在理解问题、检索知识库并核验证据……"):
                            payload = answer_question(question.strip())
                        record_answer(st.session_state, question.strip(), payload)
                        st.rerun()
                    except Exception:
                        st.error("问答执行失败，请检查索引和运行环境后重试。")
            _answer_panel(selected_result(st.session_state))
    with evidence_column:
        with st.container(border=True):
            _evidence_panel(selected_result(st.session_state), on_evidence)
