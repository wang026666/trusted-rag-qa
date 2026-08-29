"""Presentation helpers for the submission runtime's Streamlit interface."""

from __future__ import annotations

from typing import Any


QUICK_QUESTIONS = (
    {
        "label": "制度解释",
        "question": "商业银行应当制定什么账簿划分政策？",
        "hint": "快速定位监管条款与制度要求",
    },
    {
        "label": "报表取数",
        "question": "2026年1月银行业总资产是多少？",
        "hint": "从统计报表中提取明确数值",
    },
    {
        "label": "指标比较",
        "question": "请比较统计报表中两个相邻月份的总负债变化。",
        "hint": "核对同源口径后给出比较结果",
    },
)


_STATUS_PRESENTATIONS = {
    "answered": ("证据充分", "success"),
    "clarification_required": ("需要补充信息", "warning"),
    "insufficient_evidence": ("证据不足", "warning"),
    "out_of_scope": ("资料库范围外", "danger"),
}


def status_presentation(status: str | None, citation_count: int) -> dict[str, str]:
    """Return reader-facing wording for an answer trust state."""
    label, tone = _STATUS_PRESENTATIONS.get(status or "", ("状态待核验", "neutral"))
    if citation_count > 0:
        detail = f"已引用 {citation_count} 条可核验证据"
    else:
        detail = "未引用可支持当前问题的资料"
    return {"label": label, "tone": tone, "detail": detail}


def coverage_presentation(value: object) -> dict[str, str]:
    """Present evidence support coverage without turning it into accuracy."""
    if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= float(value) <= 1:
        rendered = f"{float(value) * 100:.0f}%"
    else:
        rendered = "未提供"
    return {
        "label": "证据覆盖度",
        "value": rendered,
        "detail": "表示回答要点获得引用支持的比例",
    }


def confidence_presentation(value: object) -> dict[str, str]:
    """Keep backend confidence categorical and reader-facing."""
    return {
        "high": {"label": "高", "tone": "success"},
        "medium": {"label": "中", "tone": "warning"},
        "low": {"label": "低", "tone": "danger"},
    }.get(str(value or "").lower(), {"label": "待核验", "tone": "neutral"})


def citation_location(citation: dict[str, Any]) -> str:
    """Summarize available evidence coordinates without showing empty fields."""
    parts: list[str] = []
    if citation.get("page"):
        parts.append(f"第 {citation['page']} 页")
    if citation.get("section"):
        parts.append(str(citation["section"]))
    if citation.get("sheet_name"):
        parts.append(f"工作表 {citation['sheet_name']}")
    if citation.get("cell"):
        parts.append(f"单元格 {citation['cell']}")
    return " · ".join(parts) or "原数据未提供页码定位"


def format_match_score(value: object) -> str:
    """Format a raw ranking signal without implying probability."""
    try:
        score = float(value)
    except (TypeError, ValueError):
        return "未提供"
    return f"{score:.4f}"


def _mapped_label(value: object, mapping: dict[str, str]) -> str:
    text = str(value or "").strip()
    if not text:
        return "未提供"
    return mapping.get(text, f"待核验（{text}）")


def intent_label(value: object) -> str:
    return _mapped_label(
        value,
        {
            "regulation_fact": "监管制度问答",
            "multi_fact": "多事实核验",
            "table_lookup": "统计报表取数",
            "table_compare": "统计报表比较",
            "table_calculate": "统计报表计算",
            "out_of_scope": "资料库范围外",
        },
    )


def consistency_label(value: object) -> str:
    return _mapped_label(
        value,
        {
            "supported": "证据一致",
            "not_applicable": "无需事实一致性核验",
            "unsupported": "存在证据外事实",
        },
    )


def backend_label(value: object) -> str:
    return _mapped_label(
        value,
        {
            "extractive": "本地证据抽取",
            "deterministic_extractive": "本地证据抽取",
            "extractive_fallback": "本地证据抽取（安全回退）",
            "llm": "大模型证据生成",
            "llm_consistency_fallback": "证据校验后回退",
            "refusal": "证据不足拒答",
        },
    )


def citations_for_display(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Expose citations only when the engine produced a supported answer."""
    if not isinstance(payload, dict) or payload.get("status") != "answered":
        return []
    citations = payload.get("citations")
    if not isinstance(citations, list):
        return []
    return [item for item in citations if isinstance(item, dict)]


def trust_tone_class(tone: str) -> str:
    """Keep backend state strings out of HTML class construction."""
    return tone if tone in {"success", "warning", "danger", "neutral"} else "neutral"


TRUSTED_WORKSPACE_CSS = """
<style>
:root { --fin-ink:#142721; --fin-muted:#61716a; --fin-line:#dbe5df; --fin-surface:#ffffff; --fin-ground:#f4f7f4; --fin-primary:#087a4a; --fin-primary-dark:#05633c; --fin-warning:#9d6a12; --fin-warning-soft:#fcf4df; --fin-danger:#b63d39; --fin-danger-soft:#fcebea; }
* { box-sizing: border-box; }
.stApp { background:var(--fin-ground); color:var(--fin-ink); }
.stApp, .stApp [class*="css"] { font-family:"PingFang SC", "Microsoft YaHei", "Noto Sans SC", Arial, sans-serif; }
#MainMenu, footer, header { visibility:hidden; }
[data-testid="stHeader"] { background:rgba(244,247,244,.94); }
.block-container { max-width:1220px; padding:1.35rem 1.75rem 3.5rem; }
.fin-shell-header { border-bottom:1px solid var(--fin-line); margin-bottom:1.45rem; }
.fin-shell-topline { align-items:center; display:flex; justify-content:space-between; gap:1rem; padding:.25rem 0 1rem; }
.fin-brand { align-items:center; display:flex; gap:.72rem; min-width:0; }
.fin-mark { align-items:center; background:var(--fin-primary); border-radius:4px; color:white; display:inline-flex; font-family:Georgia,serif; font-size:1.12rem; font-weight:700; height:2.2rem; justify-content:center; width:2.2rem; }
.fin-brand-name { color:var(--fin-ink); font-size:1.14rem; font-weight:700; letter-spacing:.04em; }
.fin-brand-subtitle { color:var(--fin-muted); font-size:.78rem; margin-top:.12rem; }
.fin-header-status { align-items:center; color:var(--fin-muted); display:flex; font-size:.8rem; gap:.45rem; white-space:nowrap; }
.fin-header-status::before { background:var(--fin-primary); border-radius:50%; content:""; height:.45rem; width:.45rem; }
.fin-shell-nav { color:var(--fin-muted); display:flex; font-size:.82rem; gap:1.8rem; padding:0 0 .78rem 2.92rem; }
.fin-shell-nav .active { color:var(--fin-primary); font-weight:700; position:relative; }
.fin-shell-nav .active::after { background:var(--fin-primary); bottom:-.79rem; content:""; height:2px; left:0; position:absolute; right:0; }
.fin-eyebrow { color:var(--fin-primary); font-size:.78rem; font-weight:700; letter-spacing:.13em; margin-bottom:.5rem; text-transform:uppercase; }
.fin-workspace-title { color:var(--fin-ink); font-family:Georgia,"Songti SC",serif; font-size:clamp(1.9rem,4vw,3.1rem); font-weight:700; letter-spacing:-.035em; line-height:1.14; margin:0; }
.fin-workspace-copy { color:var(--fin-muted); font-size:.98rem; line-height:1.7; margin:.7rem 0 1.35rem; max-width:42rem; }
div[data-testid="stTextArea"] textarea { background:#fbfcfb; border:1px solid #bdcbc3; border-radius:4px; color:var(--fin-ink); font-size:1rem; line-height:1.65; min-height:7rem; padding:.88rem .95rem; }
div[data-testid="stTextArea"] textarea:focus { border-color:var(--fin-primary); box-shadow:0 0 0 3px rgba(8,122,74,.12); }
div[data-testid="stTextArea"] label { color:var(--fin-ink); font-size:.84rem; font-weight:700; }
[data-testid="stForm"] { background:var(--fin-surface); border:1px solid var(--fin-line); border-radius:6px; margin-top:.85rem; padding:1rem; }
[data-testid="stFormSubmitButton"] button { background:var(--fin-primary); border:1px solid var(--fin-primary); border-radius:4px; color:#fff; font-weight:700; min-height:2.75rem; }
[data-testid="stFormSubmitButton"] button:hover { background:var(--fin-primary-dark); border-color:var(--fin-primary-dark); color:#fff; }
.fin-section-kicker { color:var(--fin-muted); font-size:.76rem; font-weight:700; letter-spacing:.08em; margin:1.35rem 0 .55rem; text-transform:uppercase; }
[data-testid="stButton"] button { background:transparent; border:1px solid var(--fin-line); border-radius:4px; color:var(--fin-ink); font-size:.86rem; min-height:2.6rem; text-align:left; }
[data-testid="stButton"] button:hover { border-color:var(--fin-primary); color:var(--fin-primary); }
.fin-result-rule { border:0; border-top:1px solid var(--fin-line); margin:2rem 0 1.25rem; }
.fin-answer-kicker { color:var(--fin-primary); font-size:.76rem; font-weight:700; letter-spacing:.1em; text-transform:uppercase; }
.fin-answer-title { color:var(--fin-ink); font-family:Georgia,"Songti SC",serif; font-size:1.48rem; font-weight:700; margin:.35rem 0 .82rem; }
.fin-answer-copy { color:#20332b; font-size:1rem; line-height:1.88; }
.fin-answer-copy p { margin:0 0 .7rem; }
.fin-trust-panel { background:#fbfcfb; border-left:3px solid var(--fin-primary); margin-top:.2rem; padding:1rem 1.05rem; }
.fin-trust-panel.warning { background:var(--fin-warning-soft); border-color:var(--fin-warning); }
.fin-trust-panel.danger { background:var(--fin-danger-soft); border-color:var(--fin-danger); }
.fin-trust-panel.neutral { border-color:#80918a; }
.fin-trust-label { color:var(--fin-ink); font-size:1rem; font-weight:700; margin:.1rem 0 .35rem; }
.fin-trust-detail { color:var(--fin-muted); font-size:.84rem; line-height:1.55; }
.fin-trust-caption { color:var(--fin-muted); font-size:.71rem; font-weight:700; letter-spacing:.09em; text-transform:uppercase; }
.fin-evidence-heading { color:var(--fin-ink); font-family:Georgia,"Songti SC",serif; font-size:1.35rem; font-weight:700; margin:1.65rem 0 .18rem; }
.fin-evidence-lead { color:var(--fin-muted); font-size:.86rem; margin-bottom:.85rem; }
.fin-evidence-item { border-top:1px solid var(--fin-line); padding:.9rem 0; }
.fin-evidence-index { color:var(--fin-primary); font-size:.78rem; font-weight:700; letter-spacing:.08em; }
.fin-evidence-title { color:var(--fin-ink); font-size:.96rem; font-weight:700; line-height:1.45; margin:.18rem 0; }
.fin-evidence-location { color:var(--fin-muted); font-size:.8rem; line-height:1.45; }
.fin-evidence-item [data-testid="stExpander"] { background:transparent; border:0; border-radius:0; margin-top:.25rem; }
.fin-evidence-item [data-testid="stExpander"] details { border:0; }
.fin-evidence-item [data-testid="stExpander"] summary { color:var(--fin-primary); font-size:.83rem; }
.fin-trace { background:var(--fin-surface); border-top:1px solid var(--fin-line); margin-top:1.7rem; padding-top:1rem; }
.fin-trace [data-testid="stCodeBlock"] { border:1px solid var(--fin-line); border-radius:4px; }
.fin-footer { border-top:1px solid var(--fin-line); color:var(--fin-muted); font-size:.76rem; line-height:1.55; margin-top:2.7rem; padding-top:1rem; }
@media (max-width:720px) { .block-container { padding:1rem 1rem 2.5rem; } .fin-shell-topline { align-items:flex-start; flex-direction:column; } .fin-shell-nav { gap:1rem; overflow-x:auto; padding-left:0; white-space:nowrap; } .fin-shell-nav .active::after { bottom:-.79rem; } .fin-workspace-title { font-size:2rem; } .fin-query-panel { padding:.82rem; } }
</style>
"""


BANK_PLATFORM_CSS = """
<style>
:root {
  --br-navy:#081B33; --br-navy-2:#102A4C; --br-blue:#173E70;
  --br-gold:#C7A35A; --br-gold-soft:#F7F1E5; --br-bg:#F4F6F9;
  --br-white:#FFFFFF; --br-ink:#14233A; --br-muted:#66758A;
  --br-line:#DCE3EC; --br-line-soft:#E9EDF3; --br-success:#1E7A5B;
  --br-warning:#B7791F; --br-danger:#B33A3A; --br-shadow:0 7px 22px rgba(8,27,51,.055);
}
* { box-sizing:border-box; }
html, body, [class*="css"] { font-family:"PingFang SC","Microsoft YaHei","Noto Sans SC",Arial,sans-serif; }
.stApp { background:var(--br-bg); color:var(--br-ink); }
[data-testid="stHeader"] { background:rgba(244,246,249,.94); backdrop-filter:blur(8px); }
[data-testid="stToolbar"], [data-testid="stDeployButton"], [data-testid="stDecoration"], #MainMenu, footer { display:none !important; }
.block-container { max-width:1580px; padding:4rem 1.5rem 2.75rem; }

/* application rail */
[data-testid="stSidebar"] { background:var(--br-navy); border-right:1px solid rgba(255,255,255,.08); min-width:15.8rem; }
[data-testid="stSidebar"] > div:first-child { padding:1.15rem .8rem 1rem; }
.br-brand { align-items:center; border-bottom:1px solid rgba(255,255,255,.14); display:flex; gap:.72rem; margin:0 .15rem 1.1rem; padding:.25rem .35rem 1.05rem; }
.br-brand-mark { align-items:center; border:1px solid var(--br-gold); border-radius:7px; color:var(--br-gold); display:flex; flex:0 0 2.5rem; font-family:"Songti SC",serif; font-size:1.2rem; font-weight:800; height:2.5rem; justify-content:center; position:relative; }
.br-brand-mark::after { border:1px solid rgba(199,163,90,.34); border-radius:4px; content:""; inset:4px; position:absolute; }
.br-brand strong { color:#fff; display:block; font-size:.96rem; letter-spacing:.02em; line-height:1.35; }
.br-brand span { color:#AEBBCB; display:block; font-size:.7rem; line-height:1.4; margin-top:.12rem; }
.br-nav-label { color:#7F91A6; font-size:.66rem; font-weight:700; letter-spacing:.14em; margin:.2rem .45rem .45rem; }
[data-testid="stSidebar"] [data-testid="stButton"] { margin:.12rem 0; }
[data-testid="stSidebar"] [data-testid="stButton"] button { background:transparent; border:0; border-radius:6px; color:#D8E0EA; font-size:.86rem; font-weight:560; justify-content:flex-start; letter-spacing:.01em; min-height:2.8rem; padding:0 .78rem; text-align:left; transition:background-color .18s ease,color .18s ease,box-shadow .18s ease; }
[data-testid="stSidebar"] [data-testid="stButton"] button:hover { background:rgba(255,255,255,.075); color:#fff; }
[data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"] { background:rgba(199,163,90,.13); box-shadow:inset 3px 0 0 var(--br-gold); color:#F1D592; }
.br-sidebar-foot { border-top:1px solid rgba(255,255,255,.14); color:#BAC6D4; font-size:.75rem; margin:1.25rem .4rem 0; padding:1rem .2rem 0; position:static; }
.br-sidebar-foot i, .br-system-state i { background:var(--br-success); border-radius:50%; display:inline-block; height:.46rem; margin-right:.45rem; width:.46rem; }
.br-sidebar-foot.fault i, .br-system-state.fault i { background:var(--br-danger); }
.br-sidebar-foot small { color:#7F91A6; display:block; font-size:.66rem; margin:.28rem 0 0 .92rem; }

/* top bar and page titles */
.br-topbar { align-items:center; background:var(--br-white); border:1px solid var(--br-line); border-radius:7px; box-shadow:0 1px 3px rgba(8,27,51,.025); display:flex; justify-content:space-between; min-height:3.55rem; padding:.65rem 1rem; }
.br-topbar-title { color:var(--br-ink); font-size:.94rem; font-weight:720; }
.br-topbar-meta { align-items:center; color:var(--br-muted); display:flex; font-size:.73rem; gap:.85rem; }
.br-system-state { align-items:center; display:flex; white-space:nowrap; }
.br-system-state.ready { color:var(--br-success); }
.br-system-state.fault { color:var(--br-danger); }
.br-meta-divider { background:var(--br-line); height:1.05rem; width:1px; }
.br-role { white-space:nowrap; }
.br-page-header { margin:1.35rem 0 1.05rem; }
.br-page-header h1 { color:var(--br-ink); font-size:clamp(1.48rem,2.1vw,2.05rem); font-weight:760; letter-spacing:-.03em; line-height:1.25; margin:0; }
.br-page-header p { color:var(--br-muted); font-size:.85rem; line-height:1.65; margin:.38rem 0 0; max-width:56rem; }
.br-section-header { align-items:flex-end; border-bottom:1px solid var(--br-line-soft); display:flex; justify-content:space-between; margin:0 0 .85rem; padding:0 0 .72rem; }
.br-section-header h2 { color:var(--br-ink); font-size:1rem; font-weight:720; margin:0; }
.br-section-header p { color:var(--br-muted); font-size:.72rem; margin:0; }

/* panels and metrics */
[data-testid="stVerticalBlock"] > [data-testid="stVerticalBlockBorderWrapper"] { background:var(--br-white); border-color:var(--br-line) !important; border-radius:8px; box-shadow:var(--br-shadow); }
.br-kpi-grid { display:grid; gap:.9rem; grid-template-columns:repeat(4,minmax(0,1fr)); margin-bottom:1rem; }
.br-kpi { align-items:center; animation:br-enter .24s ease both; background:var(--br-white); border:1px solid var(--br-line); border-radius:8px; box-shadow:var(--br-shadow); display:flex; gap:.85rem; min-height:7.15rem; overflow:hidden; padding:1rem; }
.br-kpi:nth-child(2) { animation-delay:.035s; }.br-kpi:nth-child(3) { animation-delay:.07s; }.br-kpi:nth-child(4) { animation-delay:.105s; }
.br-kpi-mark { align-items:center; background:#EEF3F9; border:1px solid #D8E2EF; border-radius:7px; color:var(--br-blue); display:flex; flex:0 0 2.75rem; font-family:"Songti SC",serif; font-size:1.02rem; font-weight:800; height:2.75rem; justify-content:center; }
.br-kpi-body { min-width:0; }
.br-kpi-label { color:var(--br-muted); font-size:.73rem; font-weight:620; line-height:1.35; }
.br-kpi-value { color:var(--br-ink); font-size:1.68rem; font-variant-numeric:tabular-nums; font-weight:780; letter-spacing:-.035em; line-height:1.2; margin:.22rem 0 .12rem; white-space:nowrap; }
.br-kpi-detail { color:var(--br-muted); font-size:.65rem; line-height:1.4; }
.br-kpi-value em { color:var(--br-gold); font-style:normal; }
.br-panel-title { color:var(--br-ink); font-size:.96rem; font-weight:720; margin-bottom:.18rem; }
.br-panel-note { color:var(--br-muted); font-size:.7rem; line-height:1.55; }

/* controls */
.stButton > button, [data-testid="stFormSubmitButton"] button, [data-testid="stDownloadButton"] button { border-radius:6px; font-size:.78rem; font-weight:650; min-height:2.65rem; transition:border-color .18s ease,background-color .18s ease,color .18s ease,box-shadow .18s ease; }
[data-testid="stButton"] button[kind="primary"], [data-testid="stFormSubmitButton"] button[kind="primary"], [data-testid="stFormSubmitButton"] button { background:var(--br-navy-2); border-color:var(--br-navy-2); color:#fff; }
[data-testid="stButton"] button[kind="primary"]:hover, [data-testid="stFormSubmitButton"] button:hover { background:var(--br-blue); border-color:var(--br-blue); }
.stButton > button:focus-visible, textarea:focus-visible, input:focus-visible, [role="combobox"]:focus-visible { box-shadow:0 0 0 3px rgba(199,163,90,.28) !important; outline:2px solid var(--br-gold) !important; outline-offset:1px; }
div[data-testid="stTextArea"] textarea, div[data-testid="stTextInput"] input, div[data-baseweb="select"] > div { background:#FBFCFE; border-color:#C9D3DF; border-radius:6px; color:var(--br-ink); font-size:.84rem; }
div[data-testid="stTextArea"] textarea:focus, div[data-testid="stTextInput"] input:focus { border-color:var(--br-blue); box-shadow:0 0 0 3px rgba(23,62,112,.1); }
[data-testid="stForm"] { background:transparent; border:0; padding:0; }
[data-testid="stFileUploader"] { background:#FBFCFE; border:1px dashed #AAB7C7; border-radius:7px; padding:.4rem; }
[data-testid="stFileUploaderDropzone"] { background:transparent; }

/* evidence and audit flow */
.br-trust-hero { background:var(--br-navy); border-radius:7px; color:#fff; margin-bottom:.75rem; padding:1rem; }
.br-trust-hero span { color:#AFC0D2; display:block; font-size:.66rem; }
.br-trust-hero strong { color:#F0D28C; display:block; font-size:1.75rem; font-weight:760; margin:.25rem 0 .15rem; }
.br-trust-hero small { color:#D3DCE7; font-size:.67rem; line-height:1.45; }
.br-trust-strip { display:grid; gap:1px; grid-template-columns:repeat(3,1fr); margin-bottom:.75rem; }
.br-trust-strip > div { background:#F8FAFC; border:1px solid var(--br-line); padding:.65rem .45rem; text-align:center; }
.br-trust-strip > div:first-child { border-radius:6px 0 0 6px; }.br-trust-strip > div:last-child { border-radius:0 6px 6px 0; }
.br-trust-strip span { color:var(--br-muted); display:block; font-size:.62rem; }.br-trust-strip strong { color:var(--br-ink); display:block; font-size:.82rem; margin-top:.2rem; }
.br-citation-head { align-items:flex-start; border-top:1px solid var(--br-line); display:flex; gap:.65rem; padding:.82rem 0 .45rem; }
.br-citation-number { align-items:center; background:var(--br-gold); border-radius:4px; color:#fff; display:flex; flex:0 0 1.55rem; font-size:.65rem; font-weight:750; height:1.55rem; justify-content:center; }
.br-citation-head strong { color:var(--br-ink); display:block; font-size:.78rem; line-height:1.45; }
.br-citation-head small { color:var(--br-muted); display:block; font-size:.65rem; line-height:1.45; margin-top:.16rem; }
.br-citation-meta { color:var(--br-muted); display:grid; font-size:.63rem; gap:.15rem; grid-template-columns:1fr; margin:0 0 .3rem 2.2rem; overflow-wrap:anywhere; }
[data-testid="stExpander"] details { background:#FBFCFE; border-color:var(--br-line); border-radius:6px; }
[data-testid="stExpander"] summary { color:var(--br-blue); font-size:.72rem; }
.br-process-rail { align-items:stretch; display:flex; margin:.25rem 0 1.05rem; overflow-x:auto; padding:.35rem 0 .5rem; }
.br-process-step { align-items:center; background:var(--br-white); border:1px solid var(--br-line); border-radius:7px; display:flex; flex:1 0 9rem; flex-direction:column; min-height:6.8rem; padding:.65rem .55rem; text-align:center; }
.br-process-step span { align-items:center; border:1px solid var(--br-line); border-radius:50%; color:var(--br-muted); display:flex; font-size:.64rem; font-weight:750; height:1.85rem; justify-content:center; width:1.85rem; }
.br-process-step.active span { background:var(--br-gold); border-color:var(--br-gold); color:#fff; }
.br-process-step strong { color:var(--br-ink); font-size:.74rem; margin:.48rem 0 .18rem; }.br-process-step small { color:var(--br-muted); font-size:.62rem; line-height:1.4; }
.br-process-line { align-self:center; background:var(--br-gold); flex:0 0 1rem; height:1px; }

/* empty states, tables and history */
.br-empty { align-items:center; border:1px dashed #CBD5E1; border-radius:7px; display:flex; flex-direction:column; justify-content:center; min-height:13rem; padding:1.5rem; text-align:center; }
.br-empty-mark { align-items:center; border:1px solid var(--br-line); border-radius:50%; color:var(--br-gold); display:flex; font-size:1.1rem; height:2.7rem; justify-content:center; width:2.7rem; }
.br-empty-title { color:var(--br-ink); font-size:.86rem; font-weight:700; margin:.65rem 0 .24rem; }.br-empty-detail { color:var(--br-muted); font-size:.69rem; line-height:1.55; max-width:25rem; }
.br-history-note { color:var(--br-muted); font-size:.69rem; line-height:1.55; margin-bottom:.7rem; }
.br-history-empty { border:1px dashed var(--br-line); border-radius:6px; color:var(--br-muted); font-size:.7rem; padding:1rem; text-align:center; }
.br-answer-copy { color:#24344A; font-size:.86rem; line-height:1.85; white-space:pre-wrap; }
.br-boundary { background:#F8FAFC; border-left:3px solid var(--br-gold); color:var(--br-muted); font-size:.72rem; line-height:1.65; margin-top:.95rem; padding:.72rem .85rem; }
[data-testid="stDataFrame"] { border:1px solid var(--br-line); border-radius:7px; overflow:hidden; }
[data-testid="stDataFrame"] * { font-size:.72rem; }
.br-domain-grid { display:grid; gap:.75rem; grid-template-columns:repeat(3,minmax(0,1fr)); }
.br-domain-card { background:var(--br-white); border:1px solid var(--br-line); border-radius:7px; padding:.9rem; }
.br-domain-card strong { color:var(--br-ink); display:block; font-size:.84rem; }.br-domain-card b { color:var(--br-gold); display:block; font-size:1.5rem; margin:.28rem 0; }.br-domain-card span { color:var(--br-muted); font-size:.66rem; }
.br-domain-card.unbuilt b { color:var(--br-danger); }
.br-footer { border-top:1px solid var(--br-line); color:var(--br-muted); font-size:.66rem; line-height:1.55; margin-top:1.75rem; padding:1rem .25rem 0; text-align:center; }

@keyframes br-enter { from { opacity:0; transform:translateY(7px); } to { opacity:1; transform:translateY(0); } }
@media (prefers-reduced-motion:reduce) { *, *::before, *::after { animation-duration:.01ms !important; animation-iteration-count:1 !important; scroll-behavior:auto !important; transition-duration:.01ms !important; } }
@media (max-width:1100px) {
  .br-kpi-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .br-topbar-meta .br-role, .br-meta-divider { display:none; }
}
@media (max-width:767px) {
  .block-container { padding:4rem .72rem 2rem; }
  .br-topbar { min-height:3rem; padding:.55rem .68rem; }
  .br-topbar-title { font-size:.82rem; max-width:12rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .br-system-state { font-size:.66rem; }
  .br-page-header { margin:1rem 0 .8rem; }.br-page-header h1 { font-size:1.45rem; }.br-page-header p { font-size:.76rem; }
  .br-kpi-grid { gap:.58rem; grid-template-columns:repeat(2,minmax(0,1fr)); }
  .br-kpi { gap:.55rem; min-height:6.25rem; padding:.72rem; }.br-kpi-mark { flex-basis:2.15rem; height:2.15rem; }.br-kpi-value { font-size:1.2rem; white-space:normal; }.br-kpi-detail { font-size:.59rem; }
  .br-domain-grid { grid-template-columns:1fr; }
  .br-process-rail { align-items:stretch; flex-direction:column; overflow:visible; }.br-process-step { flex-basis:auto; min-height:auto; }.br-process-line { flex:0 0 .65rem; height:.65rem; width:1px; }
  [data-testid="stHorizontalBlock"] { flex-direction:column !important; }
  [data-testid="stHorizontalBlock"] > [data-testid="column"] { flex:1 1 auto !important; min-width:0 !important; width:100% !important; }
  [data-testid="stDataFrame"] { max-width:100%; overflow-x:auto; }
}
</style>
"""

# Backward-compatible import for the current single-page baseline during the staged refactor.
TRUSTED_WORKSPACE_CSS = BANK_PLATFORM_CSS
