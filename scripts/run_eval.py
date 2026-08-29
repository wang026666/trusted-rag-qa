"""Reproduce development MCQ and separate free-form evaluation results.

The 300-question development set is constructed from the supplied contest
materials and task types. Every item is evaluated through
``engine.answer(question, top_k=5, options=options)`` and scored only by exact
A/B/C/D label equality. Free-form refusal checks are kept separately.
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.config.settings import get_settings
from src.evaluator.metrics import critical_fact_metrics, evaluate_mcq_records, summarize_mcq_rows
from src.generator.unified_engine import build_unified_engine


EVALUATION_DIR = PROJECT_ROOT / "evaluation"
CASES_PATH = EVALUATION_DIR / "qa_eval.jsonl"
METRICS_PATH = EVALUATION_DIR / "metrics.json"
MCQ_FIELDS = (
    "id",
    "question",
    "option_a",
    "option_b",
    "option_c",
    "option_d",
    "answer",
    "answer_text",
    "source_type",
    "qa_type",
    "source_title",
    "evidence",
)
REFUSAL_STATUSES = {"out_of_scope", "insufficient_evidence", "clarification_required"}
XML_NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def development_mcq_record(source: dict[str, Any]) -> dict[str, Any]:
    """Preserve the development MCQ record fields and scoring contract."""
    missing = [field for field in MCQ_FIELDS if field not in source]
    if missing:
        raise ValueError(f"development MCQ record is missing fields: {', '.join(missing)}")
    record = {field: source[field] for field in MCQ_FIELDS}
    if "file_label" in source:
        record["file_label"] = source["file_label"]
    record["record_type"] = "development_mcq"
    return record


def _column_index(cell_reference: str) -> int:
    letters = "".join(char for char in cell_reference if char.isalpha())
    index = 0
    for char in letters:
        index = index * 26 + ord(char.upper()) - ord("A") + 1
    return index - 1


def _read_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return [
        "".join(node.text or "" for node in item.findall(".//x:t", XML_NS))
        for item in root.findall("x:si", XML_NS)
    ]


def _cell_value(cell: ET.Element, shared: list[str]) -> str:
    cell_type = cell.get("t", "")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//x:t", XML_NS))
    value = cell.find("x:v", XML_NS)
    raw = "" if value is None else value.text or ""
    if cell_type == "s" and raw:
        return shared[int(raw)]
    return raw


def _load_xlsx_rows(path: Path) -> list[dict[str, Any]]:
    """Read the flat development-set XLSX worksheet without requiring pandas."""
    with zipfile.ZipFile(path) as archive:
        shared = _read_shared_strings(archive)
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    rows: list[dict[int, str]] = []
    for xml_row in sheet.findall(".//x:sheetData/x:row", XML_NS):
        values: dict[int, str] = {}
        for cell in xml_row.findall("x:c", XML_NS):
            reference = cell.get("r", "")
            values[_column_index(reference)] = _cell_value(cell, shared)
        rows.append(values)
    if not rows:
        return []
    headers = rows[0]
    return [
        {header: row.get(column, "") for column, header in headers.items() if header}
        for row in rows[1:]
    ]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _load_historical_predictions(path: Path) -> dict[str, dict[str, Any]]:
    history: dict[str, dict[str, Any]] = {}
    for row in _read_jsonl(path):
        identifier = str(row.get("id", ""))
        if identifier:
            history[identifier] = {
                "predicted": str(row.get("predicted", "")),
                "is_correct": bool(row.get("is_correct", False)),
                "source_hit": bool(row.get("source_hit", False)),
            }
    return history


def _attach_historical_reference(
    records: list[dict[str, Any]], history: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    for record in records:
        if record.get("record_type") == "development_mcq":
            reference = history.get(str(record["id"]))
            if reference is not None:
                record["historical_reference"] = reference
    return records


def free_form_records_from_source(source_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Restore only the original records explicitly marked unanswerable."""
    return [
        {
            "record_type": "free_form_eval",
            "id": str(row["id"]),
            "question": str(row["question"]),
            "expected_behavior": "refusal_or_clarification_without_citation",
        }
        for row in source_rows
        if row.get("answerable") is False
    ]


def _source_cases(
    source_xlsx: Path, history_path: Path | None, free_form_path: Path | None
) -> list[dict[str, Any]]:
    records = [development_mcq_record(row) for row in _load_xlsx_rows(source_xlsx)]
    if history_path:
        records = _attach_historical_reference(records, _load_historical_predictions(history_path))
    if free_form_path:
        records.extend(free_form_records_from_source(_read_jsonl(free_form_path)))
    return records


def _run_free_form(records: list[dict[str, Any]], engine: Any) -> list[dict[str, Any]]:
    evaluated: list[dict[str, Any]] = []
    for record in records:
        if record.get("record_type") != "free_form_eval":
            evaluated.append(record)
            continue
        result = engine.answer(str(record["question"]))
        actual = result.to_dict()
        record = dict(record)
        record["free_form_result"] = {
            "status": actual["status"],
            "citation_count": len(actual.get("citations") or []),
            "success": actual["status"] in REFUSAL_STATUSES and not actual.get("citations"),
            "answer": actual["answer"],
        }
        evaluated.append(record)
    return evaluated


def _historical_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for record in records:
        reference = record.get("historical_reference")
        if record.get("record_type") != "development_mcq" or not reference:
            continue
        rows.append(
            {
                "qa_type": record["qa_type"],
                "answer": record["answer"],
                "predicted": reference["predicted"],
                "source_hit": reference["source_hit"],
            }
        )
    return rows


def _observed_diff_reason(record: dict[str, Any]) -> str:
    prediction = record.get("mcq_prediction", {})
    if prediction.get("engine_status") != "answered":
        return f"engine status={prediction.get('engine_status', '')}"
    if not prediction.get("predicted"):
        return "engine output could not be mapped uniquely to an A/B/C/D option"
    return f"predicted {prediction.get('predicted')} while development-set answer is {record.get('answer')}"


def _per_case_diff(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    diffs: list[dict[str, Any]] = []
    for record in records:
        if record.get("record_type") != "development_mcq" or "historical_reference" not in record:
            continue
        historic = record["historical_reference"]
        current = record["mcq_prediction"]
        if historic["predicted"] == current["predicted"] and historic["is_correct"] == current["is_correct"]:
            change = "unchanged"
        elif historic["is_correct"] and not current["is_correct"]:
            change = "regression"
        elif not historic["is_correct"] and current["is_correct"]:
            change = "improvement"
        else:
            change = "changed_same_correctness"
        record["historical_diff"] = {
            "change": change,
            "historical_predicted": historic["predicted"],
            "historical_is_correct": historic["is_correct"],
            "current_predicted": current["predicted"],
            "current_is_correct": current["is_correct"],
            "observed_reason": _observed_diff_reason(record),
        }
        if change != "unchanged":
            diffs.append({"id": record["id"], "qa_type": record["qa_type"], **record["historical_diff"]})
    return diffs


def _free_form_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [record["free_form_result"] for record in records if record.get("record_type") == "free_form_eval"]
    successful = sum(bool(row["success"]) for row in rows)
    return {
        "total": len(rows),
        "refusal_or_clarification_without_citation": {
            "successful": successful,
            "total": len(rows),
            "rate": successful / len(rows) if rows else 0.0,
        },
    }


def build_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    development = [record for record in records if record.get("record_type") == "development_mcq"]
    current_summary = summarize_mcq_rows(development)
    historical_rows = _historical_rows(development)
    historic_summary = summarize_mcq_rows(historical_rows) if historical_rows else None
    diffs = _per_case_diff(development)
    regressions = [diff for diff in diffs if diff["change"] == "regression"]
    baseline_check = None
    if historic_summary is not None:
        baseline_check = {
            "recovered_from_per_case_predictions": {
                "overall": historic_summary["overall_accuracy"],
                "by_qa_type": historic_summary["by_qa_type"],
                "citation": historic_summary["citation_source_hit_rate"],
            },
        }
    return {
        "evaluation_protocol": {
            "development_mcq": "engine.answer(question, top_k=5, options={A, B, C, D})",
            "development_mcq_accuracy": "predicted option label equals the development-set answer label exactly",
            "free_form_eval": "evaluated separately and excluded from development MCQ accuracy",
        },
        "development_mcq": {
            **current_summary,
            "critical_fact_error_rate": critical_fact_metrics(development),
        },
        "historical_comparison": {
            "reference": baseline_check,
            "changed_cases": diffs,
            "regressions": regressions,
            "regression_count": len(regressions),
            "note": "Observed output differences are recorded per case. Causality cannot be assigned to core-code changes without a locked historical runtime and index hash.",
        },
        "free_form_eval": _free_form_metrics(records),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run development MCQ evaluation without modifying RAG logic.")
    parser.add_argument("--source-xlsx", type=Path, help="seed qa_eval.jsonl from the development-set workbook")
    parser.add_argument("--historical-predictions", type=Path, help="attach recovered historical MCQ predictions for per-case comparison")
    parser.add_argument("--free-form-cases", type=Path, help="restore original unanswerable pressure cases into the separate free_form_eval")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--verbose", action="store_true", help="print per-question MCQ progress")
    args = parser.parse_args()

    EVALUATION_DIR.mkdir(exist_ok=True)
    if args.source_xlsx:
        records = _source_cases(args.source_xlsx, args.historical_predictions, args.free_form_cases)
    elif CASES_PATH.is_file():
        records = _read_jsonl(CASES_PATH)
    else:
        parser.error("evaluation/qa_eval.jsonl is missing; use --source-xlsx to seed development MCQ records")

    engine = build_unified_engine(get_settings(), llm=None)
    records = evaluate_mcq_records(
        records,
        engine,
        top_k=args.top_k,
        progress_callback=(
            lambda count, total, identifier, phase: print(
                f"[development_mcq {count}/{total}] {identifier} {phase}", flush=True
            )
            if args.verbose
            else None
        ),
    )
    records = _run_free_form(records, engine)
    metrics = build_metrics(records)
    _write_jsonl(CASES_PATH, records)
    METRICS_PATH.write_text(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
