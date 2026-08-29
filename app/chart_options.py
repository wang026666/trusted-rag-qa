"""ECharts option builders with count-only, artifact-backed semantics."""

from __future__ import annotations

from typing import Mapping


DOMAIN_ORDER = ("资本监管", "流动性监管", "风险管理", "统计制度", "其他")
FORMAT_ORDER = ("PDF", "XLS/XLSX", "DOC/DOCX", "其他")
CHART_COLORS = ("#173E70", "#2E5C94", "#1E7A5B", "#C7A35A", "#A6B0BF")


def build_domain_bar_option(counts: Mapping[str, int]) -> dict:
    values = [max(0, int(counts.get(category, 0))) for category in DOMAIN_ORDER]
    return {
        "animationDuration": 520,
        "animationEasing": "cubicOut",
        "grid": {"left": 12, "right": 24, "top": 12, "bottom": 28, "containLabel": True},
        "tooltip": {
            "trigger": "axis",
            "axisPointer": {"type": "shadow"},
            "formatter": "{b}：{c} 份",
            "backgroundColor": "#081B33",
            "borderWidth": 0,
            "textStyle": {"color": "#FFFFFF", "fontSize": 12},
        },
        "xAxis": {
            "type": "value",
            "name": "文档数量",
            "max": max(max(values, default=0), 1),
            "minInterval": 1,
            "axisLine": {"show": False},
            "axisTick": {"show": False},
            "axisLabel": {"color": "#66758A"},
            "splitLine": {"lineStyle": {"color": "#E8EDF3"}},
            "nameTextStyle": {"color": "#66758A", "padding": [16, 0, 0, 0]},
        },
        "yAxis": {
            "type": "category",
            "inverse": True,
            "data": list(DOMAIN_ORDER),
            "axisLine": {"show": False},
            "axisTick": {"show": False},
            "axisLabel": {"color": "#14233A", "fontSize": 12, "margin": 14},
        },
        "series": [
            {
                "type": "bar",
                "data": values,
                "barWidth": 18,
                "showBackground": True,
                "backgroundStyle": {"color": "#EDF1F6", "borderRadius": 2},
                "itemStyle": {"color": "#173E70", "borderRadius": [0, 3, 3, 0]},
                "label": {"show": True, "position": "right", "color": "#14233A", "fontWeight": 600},
            }
        ],
    }


def build_format_donut_option(counts: Mapping[str, int]) -> dict:
    data = [
        {"name": category, "value": max(0, int(counts.get(category, 0)))}
        for category in FORMAT_ORDER
    ]
    total = sum(item["value"] for item in data)
    return {
        "animationDuration": 520,
        "color": ["#173E70", "#1E7A5B", "#C7A35A", "#A6B0BF"],
        "title": {
            "text": str(total),
            "subtext": "已索引资料",
            "left": "center",
            "top": "39%",
            "textStyle": {"color": "#14233A", "fontSize": 24, "fontWeight": 700},
            "subtextStyle": {"color": "#66758A", "fontSize": 11, "lineHeight": 18},
        },
        "tooltip": {
            "trigger": "item",
            "formatter": "{b}：{c} 份",
            "backgroundColor": "#081B33",
            "borderWidth": 0,
            "textStyle": {"color": "#FFFFFF", "fontSize": 12},
        },
        "legend": {
            "orient": "horizontal",
            "bottom": 0,
            "left": "center",
            "itemWidth": 10,
            "itemHeight": 10,
            "textStyle": {"color": "#66758A", "fontSize": 11},
        },
        "series": [
            {
                "name": "文件格式",
                "type": "pie",
                "radius": ["52%", "72%"],
                "center": ["50%", "43%"],
                "avoidLabelOverlap": True,
                "label": {"show": False},
                "emphasis": {"scaleSize": 5},
                "itemStyle": {"borderColor": "#FFFFFF", "borderWidth": 3},
                "data": data,
            }
        ],
    }
