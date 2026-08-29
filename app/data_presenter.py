"""Read-only presentation adapters for the competition runtime artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


DOMAIN_ORDER = ("资本监管", "流动性监管", "风险管理", "统计制度", "其他")
FORMAT_ORDER = ("PDF", "XLS/XLSX", "DOC/DOCX", "其他")
SPREADSHEET_TYPES = {"xls", "xlsx", "csv"}
MAX_REPORT_BYTES = 20 * 1024 * 1024


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def load_index_summary(path: Path) -> dict[str, Any]:
    """Load an index summary without manufacturing fallback metrics."""
    return _load_json(path)


def load_evaluation_snapshot(path: Path) -> dict[str, Any]:
    """Return only the development citation metric with its scope attached."""
    payload = _load_json(path)
    citation = payload.get("development_mcq", {}).get("citation_source_hit_rate", {})
    rate = citation.get("rate")
    total = citation.get("total")
    if not isinstance(rate, (int, float)) or not isinstance(total, int):
        return {}
    return {
        "citation_source_hit_rate": float(rate),
        "citation_source_total": total,
        "scope_label": "开发集评测快照",
    }


def load_manifest(path: Path) -> list[dict[str, Any]]:
    """Load valid JSON object records from the packaged JSONL manifest."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return []
    records: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def classify_document(title: object, file_type: object) -> str:
    """Apply one deterministic, explicitly heuristic regulatory category."""
    text = str(title or "").lower()
    suffix = str(file_type or "").lower().lstrip(".")
    if any(keyword in text for keyword in ("资本", "capital")):
        return "资本监管"
    if any(keyword in text for keyword in ("流动性", "liquidity")):
        return "流动性监管"
    if any(keyword in text for keyword in ("风险", "risk", "不良贷款", "大额暴露", "集中度")):
        return "风险管理"
    if suffix in SPREADSHEET_TYPES or any(
        keyword in text for keyword in ("统计", "报表", "数据", "月度", "季度")
    ):
        return "统计制度"
    return "其他"


def build_domain_counts(records: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts = {category: 0 for category in DOMAIN_ORDER}
    for record in records:
        category = classify_document(record.get("title"), record.get("file_type"))
        counts[category] += 1
    return counts


def _format_group(file_type: object) -> str:
    suffix = str(file_type or "").lower().lstrip(".")
    if suffix == "pdf":
        return "PDF"
    if suffix in SPREADSHEET_TYPES:
        return "XLS/XLSX"
    if suffix in {"doc", "docx"}:
        return "DOC/DOCX"
    return "其他"


def build_format_counts(records: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts = {category: 0 for category in FORMAT_ORDER}
    for record in records:
        counts[_format_group(record.get("file_type"))] += 1
    return counts


def build_database_counts(records: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts = {"监管制度库": 0, "统计报表库": 0, "案例库": 0}
    for record in records:
        suffix = str(record.get("file_type") or "").lower().lstrip(".")
        target = "统计报表库" if suffix in SPREADSHEET_TYPES else "监管制度库"
        counts[target] += 1
    return counts


def build_document_rows(records: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for record in records:
        source_url = str(record.get("source_url") or record.get("attachment_url") or "").strip()
        digest = str(record.get("sha256") or "").strip()
        rows.append(
            {
                "文档编号": str(record.get("doc_id") or "未提供"),
                "资料名称": str(record.get("title") or "未命名资料"),
                "文件类型": str(record.get("file_type") or "未提供").upper(),
                "来源链接": source_url or "未提供",
                "校验摘要": digest[:12] if digest else "未提供",
                "索引状态": "已索引",
                "业务更新时间": "未提供",
            }
        )
    return rows


def report_preflight(filename: str, size: int, mime_type: str) -> dict[str, Any]:
    """Validate upload metadata only; no report content is parsed or persisted."""
    suffix = Path(filename or "").suffix.lower()
    accepted = suffix in {".csv", ".xlsx"} and 0 < int(size) <= MAX_REPORT_BYTES
    if suffix not in {".csv", ".xlsx"}:
        reason = "仅支持 CSV 或 XLSX，不接受含宏工作簿"
    elif int(size) <= 0:
        reason = "文件内容为空"
    elif int(size) > MAX_REPORT_BYTES:
        reason = "文件超过 20 MiB 预检上限"
    else:
        reason = "文件格式和大小通过本地预检"
    return {
        "accepted": accepted,
        "filename": filename or "未命名文件",
        "size_bytes": int(size),
        "mime_type": mime_type or "未提供",
        "reason": reason,
        "analysis_status": "未执行",
        "persistence": "不写入知识库",
    }


def index_health(index_dir: Path, summary: dict[str, Any]) -> dict[str, Any]:
    bm25 = index_dir / "bm25_index.json"
    vector = index_dir / "vector_index.json"
    bm25_ready = bm25.is_file() and bm25.stat().st_size > 0
    vector_ready = vector.is_file() and vector.stat().st_size > 0
    return {
        "ready": bm25_ready and vector_ready,
        "bm25_ready": bm25_ready,
        "vector_ready": vector_ready,
        "failure_count": summary.get("failure_count"),
        "table_cell_count": summary.get("table_cell_count"),
    }


def build_runtime_context(project_root: Path) -> dict[str, Any]:
    """Build one reconciled, read-only UI snapshot from packaged artifacts."""
    index_dir = project_root / "outputs" / "indexes"
    summary = load_index_summary(index_dir / "index_summary.json")
    evaluation = load_evaluation_snapshot(project_root / "evaluation" / "metrics.json")
    manifest = load_manifest(project_root / "knowledge_base" / "manifest.jsonl")
    manifest_count = summary.get("manifest_count")
    return {
        "project_root": project_root,
        "index_summary": summary,
        "evaluation": evaluation,
        "manifest": manifest,
        "domain_counts": build_domain_counts(manifest),
        "format_counts": build_format_counts(manifest),
        "database_counts": build_database_counts(manifest),
        "document_rows": build_document_rows(manifest),
        "health": index_health(index_dir, summary),
        "manifest_count_matches": isinstance(manifest_count, int) and manifest_count == len(manifest),
    }
