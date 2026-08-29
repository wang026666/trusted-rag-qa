"""Protocol-preserving metrics for the 300-question development MCQ set.

The development-set accuracy denominator is the option label only: a
prediction is correct exactly when the selected A/B/C/D label equals the
development-set answer.
This module deliberately does not use free-text similarity for MCQ scoring.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from src.generator.models import TrustStatus, UnifiedAnswerResult


MCQ_QA_TYPES = (
    "单事实检索",
    "多事实检索",
    "表格取数",
    "表格比较",
    "表格计算",
)
REGULATION_QA_TYPES = ("单事实检索", "多事实检索")
TABLE_QA_TYPES = ("表格取数", "表格比较", "表格计算")


def normalize_for_match(text: object) -> str:
    normalized = unicodedata.normalize("NFKC", str(text or "")).lower()
    return re.sub(r"[^a-z0-9%\u4e00-\u9fff]+", "", normalized)


def _to_float(value: object) -> float | None:
    try:
        return float(str(value).strip().replace(",", "").replace("%", ""))
    except (TypeError, ValueError):
        return None


def closest_numeric_option(value: float, options: dict[str, str]) -> str:
    """Return the uniquely closest numeric MCQ option, as in the legacy adapter."""
    best_keys: list[str] = []
    best_delta: float | None = None
    for key, option in options.items():
        option_value = _to_float(option)
        if option_value is None:
            continue
        delta = abs(option_value - value)
        if best_delta is None or delta < best_delta:
            best_delta = delta
            best_keys = [key]
        elif delta == best_delta:
            best_keys.append(key)
    return best_keys[0] if len(best_keys) == 1 else ""


def map_fact_to_option(result: UnifiedAnswerResult, options: dict[str, str]) -> str:
    """Map one production result to exactly one development-set A/B/C/D option.

    No retrieval is performed here. Numeric table facts use the legacy unique
    nearest-option mapping; non-numeric facts require one option text to occur
    in the engine answer. Ambiguous or refused outputs intentionally map to no
    option and are therefore incorrect under the development MCQ protocol.
    """
    if result.status is not TrustStatus.ANSWERED:
        return ""
    if result.fact_value is not None:
        value = _to_float(result.fact_value)
        if value is not None:
            numeric_match = closest_numeric_option(value, options)
            if numeric_match:
                return numeric_match
    answer = normalize_for_match(result.answer)
    matches = [
        key
        for key, option in options.items()
        if (normalized_option := normalize_for_match(option)) and normalized_option in answer
    ]
    return matches[0] if len(matches) == 1 else ""


def _norm_source(text: object) -> str:
    return re.sub(r"[\s_（）()：:，,。、《》.\-]+", "", str(text or "")).lower()


def is_source_hit(record: dict[str, Any], citations: list[dict[str, Any]]) -> bool:
    expected = {_norm_source(record.get("source_title", "")), _norm_source(record.get("file_label", ""))}
    expected.discard("")
    for citation in citations:
        actual = _norm_source(
            " ".join(
                str(citation.get(key, ""))
                for key in ("source_title", "relative_path", "file_path", "file_label")
            )
        )
        if actual and any(label in actual or actual in label for label in expected):
            return True
    return False


def _citation_dicts(result: UnifiedAnswerResult) -> list[dict[str, Any]]:
    return [citation.to_dict() for citation in result.citations]


def _extract_critical_facts(text: object) -> dict[str, list[str]]:
    value = unicodedata.normalize("NFKC", str(text or ""))
    dates = set(re.findall(r"\d{4}年(?:\d{1,2}月)?(?:\d{1,2}日)?", value))
    numbers = set(re.findall(r"(?<![\d.])\d+(?:\.\d+)?%?", value))
    document_numbers = set(
        re.findall(r"[\u4e00-\u9fffA-Za-z]{1,16}(?:〔|\[)\d{4}(?:〕|\])\d{1,5}号", value)
    )
    institution_pattern = (
        r"中国人民银行|国家金融监督管理总局|中国银行保险监督管理委员会|"
        r"中国银保监会|银保监会|银行业监督管理委员会|商业银行|保险公司|"
        r"财务公司|消费金融公司|金融资产投资公司|理财公司"
    )
    institutions = set(re.findall(institution_pattern, value))
    return {
        "number": sorted(numbers),
        "date": sorted(dates),
        "institution": sorted(institutions),
        "document_number": sorted(document_numbers),
    }


def audit_critical_facts(answer_text: object, predicted_option_text: object) -> dict[str, Any]:
    """Audit factual fields separately from MCQ correctness.

    Only explicit numbers, dates, institutions and document numbers occurring
    in the development-set correct-option text are checked. A semantic MCQ error that
    does not alter one of those explicit field values is not counted as a
    critical-fact error.
    """
    expected = _extract_critical_facts(answer_text)
    observed = _extract_critical_facts(predicted_option_text)
    mismatches = {
        kind: sorted(set(expected_values) - set(observed[kind]))
        for kind, expected_values in expected.items()
        if expected_values
    }
    mismatches = {kind: values for kind, values in mismatches.items() if values}
    checked = [kind for kind, values in expected.items() if values]
    return {
        "checked_fields": checked,
        "expected": expected,
        "predicted": observed,
        "mismatches": mismatches,
        "is_critical_fact_error": bool(mismatches),
    }


def evaluate_mcq_records(
    records: list[dict[str, Any]], engine: Any, top_k: int = 5, progress_callback: Any = None
) -> list[dict[str, Any]]:
    """Run the unmodified RAG engine under the development MCQ call contract."""
    evaluated: list[dict[str, Any]] = []
    development_total = sum(record.get("record_type") == "development_mcq" for record in records)
    completed = 0
    for record in records:
        if record.get("record_type") != "development_mcq":
            evaluated.append(record)
            continue
        if progress_callback:
            progress_callback(completed, development_total, str(record.get("id", "")), "started")
        options = {
            "A": str(record["option_a"]),
            "B": str(record["option_b"]),
            "C": str(record["option_c"]),
            "D": str(record["option_d"]),
        }
        result = engine.answer(str(record["question"]), top_k=top_k, options=options)
        predicted = map_fact_to_option(result, options)
        citations = _citation_dicts(result)
        predicted_option_text = options.get(predicted, "")
        audit = audit_critical_facts(record.get("answer_text", ""), predicted_option_text)
        actual = result.to_dict()
        record = dict(record)
        record["mcq_prediction"] = {
            "predicted": predicted,
            "is_correct": predicted == str(record["answer"]),
            "source_hit": is_source_hit(record, citations),
            "engine_status": actual["status"],
            "engine_answer": actual["answer"],
            "engine_fact_value": actual.get("fact_value"),
            "citations": citations,
            "generation_backend": actual.get("generation_backend", ""),
        }
        record["critical_fact_audit"] = audit
        evaluated.append(record)
        completed += 1
        if progress_callback:
            progress_callback(completed, development_total, str(record.get("id", "")), "finished")
    return evaluated


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _accuracy(rows: list[dict[str, Any]]) -> dict[str, Any]:
    correct = sum(str(row.get("predicted", "")) == str(row.get("answer", "")) for row in rows)
    return {"correct": correct, "total": len(rows), "rate": _rate(correct, len(rows))}


def summarize_mcq_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize development MCQ rows strictly by exact option-label equality."""
    summary_rows = []
    for row in rows:
        prediction = row.get("mcq_prediction", row)
        summary_rows.append(
            {
                "qa_type": str(row.get("qa_type", "")),
                "answer": str(row.get("answer", "")),
                "predicted": str(prediction.get("predicted", row.get("predicted", ""))),
                "source_hit": bool(prediction.get("source_hit", row.get("source_hit", False))),
            }
        )
    by_type = {
        qa_type: _accuracy([row for row in summary_rows if row["qa_type"] == qa_type])
        for qa_type in MCQ_QA_TYPES
    }
    regulation = [row for row in summary_rows if row["qa_type"] in REGULATION_QA_TYPES]
    table = [row for row in summary_rows if row["qa_type"] in TABLE_QA_TYPES]
    source_hits = sum(row["source_hit"] for row in summary_rows)
    return {
        "overall_accuracy": _accuracy(summary_rows),
        "by_qa_type": by_type,
        "regulation_combined_accuracy": _accuracy(regulation),
        "table_combined_accuracy": _accuracy(table),
        "citation_source_hit_rate": {
            "hit": source_hits,
            "total": len(summary_rows),
            "rate": _rate(source_hits, len(summary_rows)),
        },
    }


def critical_fact_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    audited = [record.get("critical_fact_audit", {}) for record in records]
    applicable = [audit for audit in audited if audit.get("checked_fields")]
    errors = sum(bool(audit.get("is_critical_fact_error")) for audit in applicable)
    by_field = {}
    for field in ("number", "date", "institution", "document_number"):
        field_rows = [audit for audit in applicable if field in audit.get("checked_fields", [])]
        field_errors = sum(field in audit.get("mismatches", {}) for audit in field_rows)
        by_field[field] = {
            "errors": field_errors,
            "total": len(field_rows),
            "rate": _rate(field_errors, len(field_rows)),
        }
    return {
        "errors": errors,
        "total": len(applicable),
        "rate": _rate(errors, len(applicable)),
        "definition": "explicit factual-field mismatch in the selected option, audited separately for numbers, dates, institutions and document numbers",
        "by_field": by_field,
    }
