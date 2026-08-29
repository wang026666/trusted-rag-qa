"""Bounded report-upload preflight and indexed-report query entry points."""

from __future__ import annotations

from html import escape
from typing import Callable

import streamlit as st

from app.components import empty_state_html, kpi_card_html, render_page_header, render_section_header
from app.data_presenter import report_preflight


REPORT_QUESTIONS = (
    "2026年1月银行业总资产是多少？",
    "请比较统计报表中两个相邻月份的总负债变化。",
    "请从已入库统计报表中查询指定机构和时期的明确数值。",
)


def _preflight_html(result: dict) -> str:
    tone = "#1E7A5B" if result.get("accepted") else "#B33A3A"
    state = "预检通过" if result.get("accepted") else "预检未通过"
    size_kib = int(result.get("size_bytes") or 0) / 1024
    return f"""
    <div class="br-boundary" style="border-left-color:{tone}">
      <strong>{escape(state)}</strong><br>
      文件：{escape(str(result.get('filename')))} · 大小：{size_kib:,.1f} KiB · 类型：{escape(str(result.get('mime_type')))}<br>
      {escape(str(result.get('reason')))} · {escape(str(result.get('persistence')))} · 指标分析：{escape(str(result.get('analysis_status')))}
    </div>
    """


def render_report_analysis(on_query: Callable[[str], None]) -> None:
    render_page_header(
        "监管统计报表分析",
        "上传文件仅进行本地预检，不写入知识库、不修改索引。",
    )
    with st.container(border=True):
        render_section_header("上传统计报表", "支持 CSV / XLSX，单文件不超过 20 MiB")
        uploaded = st.file_uploader(
            "选择待预检的报表",
            type=["csv", "xlsx"],
            accept_multiple_files=False,
            key="report_upload",
            help="当前演示版仅检查文件名、格式和大小，不执行宏或公式。",
        )
        if uploaded is not None:
            result = report_preflight(uploaded.name, uploaded.size, uploaded.type)
            st.session_state["uploaded_report_meta"] = result
            st.markdown(_preflight_html(result), unsafe_allow_html=True)

    cards = (
        ("资本充足率", "待分析", "尚无可验证结果", "资"),
        ("流动性覆盖率", "待分析", "尚无可验证结果", "流"),
        ("不良贷款率", "待分析", "尚无可验证结果", "不"),
        ("贷款集中度", "待分析", "尚无可验证结果", "集"),
    )
    st.markdown(
        '<div class="br-kpi-grid">' + "".join(kpi_card_html(*card) for card in cards) + "</div>",
        unsafe_allow_html=True,
    )

    trend_column, boundary_column = st.columns([1.15, 1], gap="medium")
    with trend_column:
        with st.container(border=True):
            render_section_header("指标趋势")
            st.markdown(
                empty_state_html(
                    "尚无可验证时序数据",
                    "当前没有经后端口径校验的趋势数据，因此不渲染示例折线。",
                    "趋",
                ),
                unsafe_allow_html=True,
            )
    with boundary_column:
        with st.container(border=True):
            render_section_header("当前能力边界")
            st.markdown(
                """
                <div class="br-process-rail">
                  <div class="br-process-step active"><span>01</span><strong>文件预检</strong><small>格式、大小与可读性</small></div>
                  <i class="br-process-line"></i>
                  <div class="br-process-step"><span>02</span><strong>口径映射</strong><small>未接入</small></div>
                  <i class="br-process-line"></i>
                  <div class="br-process-step"><span>03</span><strong>指标计算</strong><small>未接入</small></div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.warning("自动指标计算需要后端表格解析、口径映射与阈值规则支持，当前演示版不伪造结果。")

    with st.container(border=True):
        render_section_header("查询已入库报表", "使用现有可信RAG引擎进行真实取数和引用核验")
        for index, question in enumerate(REPORT_QUESTIONS, start=1):
            if st.button(question, key=f"report_query_{index}", use_container_width=True):
                on_query(question)
                st.rerun()
