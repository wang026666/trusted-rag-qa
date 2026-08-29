"""Regulatory command dashboard backed only by packaged artifacts."""

from __future__ import annotations

from typing import Any, Callable

import pandas as pd
import streamlit as st
from streamlit_echarts import st_echarts

from app.chart_options import build_domain_bar_option
from app.components import kpi_card_html, render_page_header, render_section_header
from app.ui_theme import QUICK_QUESTIONS


def _number(value: object) -> str:
    return f"{value:,}" if isinstance(value, int) else "数据不可用"


def _rate(value: object) -> str:
    return f"{float(value) * 100:.0f}%" if isinstance(value, (int, float)) else "数据不可用"


def render_dashboard(
    context: dict[str, Any],
    session_question_count: int,
    on_query: Callable[[str], None],
) -> None:
    render_page_header(
        "银行可信RAG监管智能分析平台",
        "统一展示监管资料覆盖、统计报表可检索规模与可信问答运行状态。",
    )
    summary = context.get("index_summary") or {}
    evaluation = context.get("evaluation") or {}
    cards = (
        ("已索引资料", _number(summary.get("manifest_count")), "来自知识库 manifest", "文"),
        ("知识库规模", _number(summary.get("chunk_count")), "可检索知识片段", "层"),
        ("当前会话问答", f"{session_question_count:,}", "刷新或关闭页面后重置", "问"),
        (
            "引用命中快照",
            _rate(evaluation.get("citation_source_hit_rate")),
            f"{evaluation.get('scope_label', '数据不可用')} · {evaluation.get('citation_source_total', '—')} 题",
            "证",
        ),
    )
    st.markdown(
        '<div class="br-kpi-grid">' + "".join(kpi_card_html(*card) for card in cards) + "</div>",
        unsafe_allow_html=True,
    )

    chart_column, question_column = st.columns([1.6, 1], gap="medium")
    with chart_column:
        with st.container(border=True):
            render_section_header("监管制度文档数量分析", "按标题关键词启发式归类")
            domain_counts = context.get("domain_counts") or {}
            if sum(domain_counts.values()):
                st_echarts(
                    options=build_domain_bar_option(domain_counts),
                    height="300px",
                    key="dashboard_domain_chart",
                )
                st.caption(f"按文档标题关键词归类，非人工法规标注 · 共 {sum(domain_counts.values()):,} 份")
            else:
                st.info("监管制度分类数据不可用。")

    with question_column:
        with st.container(border=True):
            render_section_header("快速监管问题", "快捷入口，非访问量排名")
            for index, item in enumerate(QUICK_QUESTIONS, start=1):
                if st.button(
                    item["question"],
                    key=f"dashboard_query_{index}",
                    use_container_width=True,
                    help=item["hint"],
                ):
                    on_query(item["question"])
                    st.rerun()
            st.caption("点击问题后进入可信RAG问答，由现有引擎实时检索。")

    with st.container(border=True):
        render_section_header("收录资料概览", "展示 manifest 中的收录记录，不冒充最近更新时间")
        rows = context.get("document_rows") or []
        if rows:
            visible_columns = ["文档编号", "资料名称", "文件类型", "来源链接", "索引状态"]
            st.dataframe(
                pd.DataFrame(rows[:8])[visible_columns],
                use_container_width=True,
                hide_index=True,
                height=310,
            )
            st.caption(f"当前展示 8 条或全部可用记录 · manifest 共 {len(rows):,} 条")
        else:
            st.info("知识库 manifest 不可用，未展示替代数据。")
