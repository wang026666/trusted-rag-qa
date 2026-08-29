"""Read-only knowledge-base observability view."""

from __future__ import annotations

from html import escape
from typing import Any

import pandas as pd
import streamlit as st
from streamlit_echarts import st_echarts

from app.chart_options import build_format_donut_option
from app.components import render_page_header, render_section_header


def _domain_cards_html(counts: dict[str, int]) -> str:
    cards = []
    for name in ("监管制度库", "统计报表库", "案例库"):
        value = int(counts.get(name, 0))
        unbuilt = name == "案例库" and value == 0
        state = "未建立" if unbuilt else "已索引"
        cards.append(
            f'<section class="br-domain-card{" unbuilt" if unbuilt else ""}">'
            f'<strong>{escape(name)}</strong><b>{value:,}</b><span>{state}</span></section>'
        )
    return '<div class="br-domain-grid">' + "".join(cards) + "</div>"


def render_knowledge_base(context: dict[str, Any]) -> None:
    render_page_header("知识库管理", "只读展示已收录资料、格式分布与索引健康状态。")
    st.markdown(_domain_cards_html(context.get("database_counts") or {}), unsafe_allow_html=True)

    health_column, format_column = st.columns([1.45, 1], gap="medium")
    with health_column:
        with st.container(border=True):
            render_section_header("索引健康状态", "根据预构建索引和 index summary 判定")
            health = context.get("health") or {}
            states = (
                ("BM25索引", "就绪" if health.get("bm25_ready") else "缺失"),
                ("向量索引", "就绪" if health.get("vector_ready") else "缺失"),
                ("解析失败", str(health.get("failure_count") if health.get("failure_count") is not None else "未提供")),
                ("表格单元", f"{health.get('table_cell_count'):,}" if isinstance(health.get("table_cell_count"), int) else "未提供"),
            )
            columns = st.columns(4)
            for column, (label, value) in zip(columns, states):
                column.metric(label, value)
            st.caption("索引状态只表示本地文件完整性，不代表外部服务可用性。")

    with format_column:
        with st.container(border=True):
            render_section_header("文件格式分布", "按 manifest.file_type 统计")
            format_counts = context.get("format_counts") or {}
            if sum(format_counts.values()):
                st_echarts(
                    options=build_format_donut_option(format_counts),
                    height="260px",
                    key="knowledge_format_chart",
                )
            else:
                st.info("文件格式数据不可用。")

    with st.container(border=True):
        render_section_header("收录文档", "业务更新时间：未提供")
        search_column, type_column, source_column = st.columns([1.8, 1, 1])
        query = search_column.text_input(
            "搜索文档",
            placeholder="输入文档编号或资料名称",
            key="knowledge_search",
        )
        rows = context.get("document_rows") or []
        types = sorted({row["文件类型"] for row in rows})
        selected_type = type_column.selectbox("文件类型", ["全部", *types], key="knowledge_type")
        selected_source = source_column.selectbox(
            "来源链接状态",
            ["全部", "已提供", "未提供"],
            key="knowledge_source",
        )
        normalized = query.strip().lower()
        filtered = []
        for row in rows:
            if normalized and normalized not in f"{row['文档编号']} {row['资料名称']}".lower():
                continue
            if selected_type != "全部" and row["文件类型"] != selected_type:
                continue
            has_source = row["来源链接"] != "未提供"
            if selected_source == "已提供" and not has_source:
                continue
            if selected_source == "未提供" and has_source:
                continue
            filtered.append(row)
        if filtered:
            visible = ["文档编号", "资料名称", "文件类型", "来源链接", "校验摘要", "索引状态"]
            st.dataframe(
                pd.DataFrame(filtered)[visible],
                use_container_width=True,
                hide_index=True,
                height=430,
            )
            st.caption(f"当前筛选 {len(filtered):,} 条 · manifest 总计 {len(rows):,} 条")
        else:
            st.info("当前条件下没有可展示的 manifest 记录。")
