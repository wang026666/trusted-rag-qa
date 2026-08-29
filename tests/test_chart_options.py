from app.chart_options import build_domain_bar_option, build_format_donut_option


def test_domain_chart_uses_document_counts_not_percentages():
    """Changing counts into percentages must break the chart contract."""
    option = build_domain_bar_option(
        {"资本监管": 4, "流动性监管": 3, "风险管理": 2, "统计制度": 1, "其他": 5}
    )

    assert option["xAxis"]["name"] == "文档数量"
    assert option["xAxis"]["max"] == 5
    assert option["series"][0]["data"] == [4, 3, 2, 1, 5]
    assert option["tooltip"]["formatter"] == "{b}：{c} 份"


def test_domain_chart_order_is_stable_when_input_order_changes():
    """Dictionary insertion order must not change the regulated category order."""
    option = build_domain_bar_option({"其他": 5, "统计制度": 1, "风险管理": 2, "流动性监管": 3, "资本监管": 4})

    assert option["yAxis"]["data"] == ["资本监管", "流动性监管", "风险管理", "统计制度", "其他"]


def test_format_donut_total_reconciles_and_uses_count_labels():
    """The donut center and segments must reconcile to the supplied document count."""
    option = build_format_donut_option({"PDF": 2, "XLS/XLSX": 3, "DOC/DOCX": 1, "其他": 4})

    assert sum(item["value"] for item in option["series"][0]["data"]) == 10
    assert option["title"]["text"] == "10"
    assert option["title"]["subtext"] == "已索引资料"
    assert option["tooltip"]["formatter"] == "{b}：{c} 份"


def test_empty_chart_keeps_a_nonzero_axis_without_inventing_data():
    """An empty collection must remain empty while keeping ECharts renderable."""
    option = build_domain_bar_option({})

    assert option["series"][0]["data"] == [0, 0, 0, 0, 0]
    assert option["xAxis"]["max"] == 1
