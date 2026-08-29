from __future__ import annotations


def classify_question(question: str) -> str:
    text = str(question or "")
    if any(key in text for key in ("变化", "计算", "相差", "增减", "占比", "同比", "环比")):
        return "指标计算类问题"
    if any(key in text for key in ("来源", "页码", "定位", "出处", "哪一条", "哪个文件")):
        return "来源定位类问题"
    if any(key in text for key in ("填报", "报送", "填列", "填制", "填表")):
        return "填报规则类问题"
    if any(key in text for key in ("口径", "指标", "数值", "报表", "工作表")):
        return "统计报表口径类问题"
    return "制度解释类问题"
