"""Explainability view for the currently selected answer."""

from __future__ import annotations

from html import escape
from typing import Callable

import streamlit as st

from app.components import process_rail_html, render_citation_card, render_empty_state, render_page_header, render_section_header
from app.session_state import selected_entry
from app.ui_theme import backend_label, citations_for_display, consistency_label, intent_label, status_presentation


def _render_trace(trace: dict) -> None:
    render_section_header("表格取数轨迹", "仅在引擎返回结构化表格证据时展示")
    columns = st.columns(2)
    columns[0].caption("工作表")
    columns[0].write(trace.get("sheet_name") or "—")
    columns[1].caption("单元格")
    columns[1].write(trace.get("cell") or "—")
    st.caption("表头路径")
    st.write(" / ".join(trace.get("header_path") or []) or "—")
    calculation = trace.get("calculation_trace") or []
    st.caption("计算过程")
    st.code("\n".join(str(item) for item in calculation) if calculation else "—", language=None)


def render_evidence(on_back: Callable[[], None]) -> None:
    render_page_header("可信解释", "展示当前回答从问题理解到证据采用的可核验链路。")
    entry = selected_entry(st.session_state)
    if not entry:
        render_empty_state("尚无可解释回答", "先在可信RAG问答页完成一次核验，再查看实际采用证据。", "证")
        if st.button("前往可信RAG问答", key="evidence_empty_back", type="primary"):
            on_back()
            st.rerun()
        return
    payload = entry.get("payload") or {}
    question = entry.get("question") or payload.get("question") or "未提供问题"
    citations = citations_for_display(payload)
    st.markdown(
        f'<div class="br-boundary"><strong>当前问题</strong><br>{escape(str(question))}</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        process_rail_html(
            intent_label(payload.get("intent")),
            bool(citations),
            answered=payload.get("status") == "answered",
        ),
        unsafe_allow_html=True,
    )
    evidence_column, audit_column = st.columns([1.62, 1], gap="medium")
    with evidence_column:
        with st.container(border=True):
            render_section_header("本次采用证据", "当前引擎未暴露完整 Top-K 候选列表")
            if citations:
                for index, citation in enumerate(citations, start=1):
                    render_citation_card(citation, index, expanded=index == 1)
            else:
                st.info("本次回答未采用引用证据。")
            st.caption("匹配分数是检索排序信号，不代表回答正确率或概率。")
    with audit_column:
        with st.container(border=True):
            render_section_header("生成与一致性")
            status = status_presentation(payload.get("status"), len(citations))
            rows = (
                ("回答状态", status["label"]),
                ("一致性状态", consistency_label(payload.get("consistency_status"))),
                ("生成后端", backend_label(payload.get("generation_backend"))),
                ("拒答原因", payload.get("refusal_reason") or "—"),
            )
            for label, value in rows:
                left, right = st.columns([.82, 1.18])
                left.caption(label)
                right.write(value)
            trace = payload.get("evidence_trace")
            if isinstance(trace, dict):
                _render_trace(trace)
            else:
                render_section_header("表格取数轨迹")
                st.caption("当前回答未返回结构化表格取数轨迹。")
    if st.button("返回可信RAG问答", key="evidence_back"):
        on_back()
        st.rerun()
