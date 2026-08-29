"""Resolve structured facts from retrieved spreadsheet rows.

The resolver is deliberately conservative: it only returns a value when the
requested source, period, row and measure can be traced to a retrieved cell.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from src.generator.models import (
    QuestionConstraints,
    QuestionIntent,
    TableOperand,
    TableResolution,
)
NOTE_MARKERS = ("注:", "注：", "说明:", "说明：", "数据来源", "备注")
_GENERIC_TITLES = ("表", "报表", "表格", "该表", "此表")
_NUMERIC_RE = re.compile(r"^-?(?:\d{1,3}(?:,\d{3})*|\d+)(?:\.\d+)?%?$")
_CELL_REF_RE = re.compile(r"^[A-Z]+[1-9]\d*$")


def _norm(text: object) -> str:
    return re.sub(r"\s+", "", str(text or "")).replace("：", ":")


def _source_norm(text: object) -> str:
    return re.sub(r"[\s_（）()：:，,。、《》.\-]+", "", str(text or "")).lower()


def _source_matches(expected: str, actual: str) -> bool:
    expected_norm = _source_norm(expected)
    actual_norm = _source_norm(actual)
    return bool(
        expected_norm
        and actual_norm
        and (expected_norm == actual_norm or expected_norm in actual_norm or actual_norm in expected_norm)
    )


def _col_order(col: str) -> int:
    value = 0
    for char in col:
        value = value * 26 + ord(char) - 64
    return value


def _parse_pairs(segment: str) -> list[tuple[str, str]]:
    return [(col, value.strip()) for col, value in re.findall(r"([A-Z]+)列=([^；]+)", segment)]


def _segment_rows(segment: str, current: bool) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    current_pairs: list[tuple[str, str]] = []
    last_order = -1
    for col, value in _parse_pairs(segment):
        order = _col_order(col)
        if current_pairs and order <= last_order:
            rows.append({"values": dict(current_pairs), "current": current})
            current_pairs = []
        current_pairs.append((col, value))
        last_order = order
    if current_pairs:
        rows.append({"values": dict(current_pairs), "current": current})
    return rows


def extract_rows(text: str) -> list[dict[str, object]]:
    """Extract current and neighbouring table rows from existing indexed text."""
    text = str(text or "")
    main, _, context = text.partition("；上文表头/相邻行：")
    if "第" in main and "行：" in main:
        main = main.split("行：", 1)[1]
    rows = _segment_rows(main, current=True)
    if context:
        rows.extend(_segment_rows(context, current=False))
    return rows


def _to_float(value: object) -> float | None:
    text = str(value or "").strip()
    if not _NUMERIC_RE.fullmatch(text):
        return None
    try:
        return float(text.replace(",", "").replace("%", ""))
    except ValueError:
        return None


def closest_numeric_option(value: float, options: dict[str, str]) -> str:
    best_key = ""
    best_delta = float("inf")
    for key, option in options.items():
        option_value = _to_float(option)
        if option_value is None:
            continue
        delta = abs(option_value - value)
        if delta < best_delta:
            best_key, best_delta = key, delta
    return best_key


def _row_number(text: str) -> int:
    matched = re.search(r"第(\d+)行", text)
    return int(matched.group(1)) if matched else 10**9


def _metadata_row_number(item: dict, text: str) -> int:
    try:
        row = int(str(item.get("row", "")).strip())
        if row > 0:
            return row
    except ValueError:
        pass
    cell_match = re.search(r"\d+$", str(item.get("cell", "")))
    if cell_match:
        return int(cell_match.group(0))
    return _row_number(text)


def _metadata_cell(item: dict, row_number: int, column: str = "") -> str:
    cell = str(item.get("cell", "")).strip().upper()
    if cell:
        return cell
    column = str(item.get("column", column)).strip().upper()
    return f"{column}{row_number}" if column and row_number < 10**9 else ""


def _title_from_text(text: str) -> str:
    matched = re.search(r"文件[:：]([^；]+)", text)
    return matched.group(1).strip() if matched else ""


def _unit_from_text(text: str) -> str:
    matched = re.search(r"(?:单位\s*[=:：]|单位为)\s*([^；;，,\s]+)", text)
    return matched.group(1).strip() if matched else ""


def _header_paths(rows: list[dict[str, object]]) -> dict[str, tuple[str, ...]]:
    by_column: dict[str, list[str]] = {}
    for row in rows:
        if row.get("current"):
            continue
        for col, value in dict(row["values"]).items():
            value = str(value).strip()
            if value and value not in by_column.setdefault(col, []):
                by_column[col].append(value)
    return {col: tuple(values) for col, values in by_column.items()}


def _cell_chunk_candidate(item: dict, label: str) -> "RowCandidate | None":
    """Decode the canonical ``build_cell_chunk`` metadata without reindexing it."""
    if str(item.get("chunk_type", "")) != "table_cell":
        return None
    text = str(item.get("text", ""))
    column = str(item.get("column", "")).strip().upper()
    value = str(item.get("value", "")).strip()
    row_number = _metadata_row_number(item, text)
    if not column or _to_float(value) is None:
        return None
    context = re.search(r"同行上下文：(.+?)(?:；表头上下文：|$)", text)
    row_label = ""
    if context:
        label_match = re.search(r"(?:项目|[A-Z]+列)\s*=\s*([^；]+)", context.group(1))
        row_label = label_match.group(1).strip() if label_match else ""
    header_path: tuple[str, ...] = ()
    header = re.search(r"表头上下文：(.+)$", text)
    if header:
        header_path = tuple(value for col, value in _parse_pairs(header.group(1)) if col == column)
    return RowCandidate(
        doc_id=str(item.get("doc_id", "")),
        source_title=str(item.get("source_title") or _title_from_text(text)),
        sheet_name=str(item.get("sheet_name", "")),
        row_number=row_number,
        cell=_metadata_cell(item, row_number, column),
        row_label=row_label,
        values={column: value},
        header_path_by_col={column: header_path} if header_path else {},
        unit=_unit_from_text(text),
        score=float(item.get("score", 0.0)),
    )


def _row_label(values: dict[str, str], requested_label: str) -> str:
    target = _norm(requested_label)
    exact = next((value for value in values.values() if _norm(value) == target), "")
    if exact:
        return exact
    contained = next((value for value in values.values() if target and target in _norm(value)), "")
    if contained:
        return contained
    return next((value for value in values.values() if _to_float(value) is None), "")


def _label_score(row_label: str, requested_label: str) -> int:
    row_norm, request_norm = _norm(row_label), _norm(requested_label)
    if not request_norm:
        return 0
    if row_norm == request_norm:
        return 3
    if request_norm in row_norm:
        return 2
    return 0


def _effective_measure(constraints: QuestionConstraints) -> str:
    quoted = [term.strip() for term in re.findall(r"“([^”]+)”", constraints.raw_question) if term.strip()]
    measure_match = re.search(r"在[“\"]([^”\"]+)[”\"]口径", constraints.raw_question)
    if measure_match:
        measure = measure_match.group(1).strip()
        if constraints.intent is QuestionIntent.TABLE_LOOKUP and _norm(measure) == "季度":
            return "年-季度"
        return measure
    if constraints.measure:
        return constraints.measure
    if constraints.intent is QuestionIntent.TABLE_LOOKUP and constraints.period:
        month = re.fullmatch(r"\d{4}年(\d{1,2})月", constraints.period)
        if month and "月度" in _norm(constraints.source_title or ""):
            return f"{month.group(1)}月"
    if constraints.intent is QuestionIntent.TABLE_LOOKUP and len(quoted) >= 2:
        return quoted[1]
    return ""


def _effective_label(constraints: QuestionConstraints) -> str:
    quoted = [term.strip() for term in re.findall(r"“([^”]+)”", constraints.raw_question) if term.strip()]
    # In source-table questions the first quoted token is the requested row
    # (for example “全国合计”), while a generic metric in the table title is
    # only topical context.  The explicit row selector takes precedence.
    if constraints.intent is QuestionIntent.TABLE_LOOKUP and quoted:
        return quoted[0]
    if constraints.intent is QuestionIntent.TABLE_LOOKUP and constraints.region:
        return constraints.region
    if constraints.metric:
        return constraints.metric
    return quoted[0] if quoted else ""


def _header_matches(header_path: tuple[str, ...], measure: str) -> bool:
    target = _norm(measure)
    if not target:
        return True
    joined = _norm("-".join(header_path))
    if not joined:
        return False
    if target in joined or joined in target:
        return True
    if target in {"年-季度", "年季度"}:
        return any("季度" in _norm(part) for part in header_path)
    if target == "季度":
        return any("季度" in _norm(part) for part in header_path)
    return False


def _candidate_columns(
    candidate: "RowCandidate", measure: str, *, allow_legacy_fallback: bool = False
) -> list[str]:
    numeric_columns = [
        col
        for col, value in sorted(candidate.values.items(), key=lambda item: _col_order(item[0]))
        if _to_float(value) is not None
    ]
    measure_norm = _norm(measure)
    matched = [
        col
        for col in numeric_columns
        if _header_matches(candidate.header_path_by_col.get(col, ()), measure)
    ]
    has_header = any(candidate.header_path_by_col.get(col) for col in numeric_columns)
    if has_header:
        if len(matched) == 1:
            return matched
        if allow_legacy_fallback and measure_norm in {"年-季度", "年季度"}:
            return numeric_columns[:1]
        if allow_legacy_fallback and measure_norm == "季度":
            return numeric_columns[-1:]
        if allow_legacy_fallback and measure_norm == "合计":
            return numeric_columns[:1]
        return []
    if matched:
        return matched
    if len(numeric_columns) == 1:
        return numeric_columns
    if not allow_legacy_fallback:
        return []
    if measure_norm in {"年-季度", "年季度"}:
        return numeric_columns[:1]
    if measure_norm == "季度":
        return numeric_columns[-1:]
    # The regional premium tables use the first numeric column as the total.
    # Their flattened header context can repeat "合计" across neighbouring
    # rows, so an exact single-header match is not always recoverable even
    # though the requested source, sheet, row and total column are explicit.
    if measure_norm == "合计":
        return numeric_columns[:1]
    if measure_norm in {"本年累计/截至当期", "本年累计截至当期"}:
        return numeric_columns[-1:]
    return numeric_columns[:1]


def _is_period_sensitive(constraints: QuestionConstraints) -> bool:
    title = _norm(constraints.source_title or "")
    if not title or title in _GENERIC_TITLES:
        return False
    return bool(constraints.metric or any(marker in title for marker in ("情况表", "月度", "季度", "统计表", "指标表")))


@dataclass(frozen=True)
class RowCandidate:
    doc_id: str
    source_title: str
    sheet_name: str
    row_number: int
    cell: str
    row_label: str
    values: dict[str, str]
    header_path_by_col: dict[str, tuple[str, ...]]
    unit: str
    score: float

    @property
    def is_note(self) -> bool:
        normalized = self.row_label.replace(" ", "")
        return any(marker in normalized for marker in NOTE_MARKERS)


class StructuredTableResolver:
    """Resolve table lookups and explicit arithmetic from retriever results."""

    table_top_k = 80

    def __init__(self, retriever):
        self.retriever = retriever

    def _empty(self, constraints: QuestionConstraints, reason: str) -> TableResolution:
        return TableResolution(
            raw_value=None,
            raw_unit="",
            display_value="",
            display_unit="",
            doc_id="",
            source_title=constraints.source_title or "",
            sheet_name=constraints.sheet_name or "",
            row_number=None,
            cell="",
            row_label="",
            header_path=(),
            operation=constraints.operation or "lookup",
            calculation_trace=(),
            ambiguity_reason=reason,
        )

    def _query(self, constraints: QuestionConstraints, label: str, measure: str) -> str:
        return " ".join(
            part
            for part in (
                constraints.source_title,
                constraints.period,
                constraints.sheet_name,
                constraints.region,
                label,
                measure,
            )
            if part
        )

    def _compatible_item(self, item: dict, constraints: QuestionConstraints) -> bool:
        text = str(item.get("text", ""))
        source_title = str(item.get("source_title") or _title_from_text(text))
        if constraints.source_title and not _source_matches(constraints.source_title, source_title):
            return False
        if constraints.period:
            period_text = _norm(source_title + text)
            if constraints.period not in period_text:
                month = re.fullmatch(r"(\d{4})年(\d{1,2})月", constraints.period)
                monthly_header_matches = bool(
                    month
                    and f"{month.group(1)}年" in period_text
                    and f"{month.group(2)}月" in period_text
                )
                if not monthly_header_matches:
                    return False
        if constraints.sheet_name:
            actual_sheet = str(item.get("sheet_name", ""))
            if actual_sheet and not _source_matches(constraints.sheet_name, actual_sheet):
                return False
        return True

    def _collect_candidates(
        self,
        constraints: QuestionConstraints,
        label: str,
        measure: str,
        header_query: str = "",
    ) -> list[RowCandidate]:
        results = list(self.retriever.search(self._query(constraints, label, measure), top_k=self.table_top_k))
        if header_query:
            results.extend(self.retriever.search(header_query, top_k=self.table_top_k))
        global_headers: dict[str, list[str]] = {}
        parsed_results: list[tuple[dict, list[dict[str, object]]]] = []
        for item in results:
            if not self._compatible_item(item, constraints):
                continue
            rows = extract_rows(str(item.get("text", "")))
            parsed_results.append((item, rows))
            for row in rows:
                values = {key: str(value) for key, value in dict(row["values"]).items()}
                is_header = bool(values) and all(
                    _to_float(value) is None for value in values.values()
                )
                if not is_header:
                    continue
                for col, value in values.items():
                    if value and value not in global_headers.setdefault(col, []):
                        global_headers[col].append(value)
        candidates: list[RowCandidate] = []
        for item, rows in parsed_results:
            text = str(item.get("text", ""))
            source_title = str(item.get("source_title") or _title_from_text(text))
            sheet_name = str(item.get("sheet_name", ""))
            paths = _header_paths(rows)
            for col, values in global_headers.items():
                paths[col] = tuple(dict.fromkeys((*paths.get(col, ()), *values)))
            for row in rows:
                if not row.get("current"):
                    continue
                values = {key: str(value) for key, value in dict(row["values"]).items()}
                row_label = _row_label(values, label)
                candidate = RowCandidate(
                    doc_id=str(item.get("doc_id", "")),
                    source_title=source_title,
                    sheet_name=sheet_name,
                    row_number=_metadata_row_number(item, text),
                    cell=_metadata_cell(item, _metadata_row_number(item, text)),
                    row_label=row_label,
                    values=values,
                    header_path_by_col=paths,
                    unit=_unit_from_text(text),
                    score=float(item.get("score", 0.0)),
                )
                if not candidate.is_note and _label_score(candidate.row_label, label):
                    candidates.append(candidate)
            cell_candidate = _cell_chunk_candidate(item, label)
            if (
                cell_candidate
                and not cell_candidate.is_note
                and _label_score(cell_candidate.row_label, label)
            ):
                candidates.append(cell_candidate)
        return sorted(
            candidates,
            key=lambda candidate: (
                -_label_score(candidate.row_label, label),
                candidate.row_number,
                -candidate.score,
            ),
        )

    def _lookup(
        self,
        constraints: QuestionConstraints,
        label: str | None = None,
        header_query: str = "",
        compatibility: bool = False,
    ) -> TableResolution | None:
        label = label or _effective_label(constraints)
        measure = _effective_measure(constraints)
        if not label:
            return self._empty(constraints, "缺少行指标")
        candidates = self._collect_candidates(constraints, label, measure, header_query)
        ambiguous_column = False
        for candidate in candidates:
            columns = _candidate_columns(
                candidate, measure, allow_legacy_fallback=compatibility
            )
            values = [
                (col, _to_float(candidate.values[col]))
                for col in columns
                if _to_float(candidate.values[col]) is not None
            ]
            if len(values) != 1:
                ambiguous_column = True
                continue
            col, raw_value = values[0]
            cell = candidate.cell or (
                f"{col}{candidate.row_number}" if candidate.row_number < 10**9 else col
            )
            header_path = candidate.header_path_by_col.get(col, ())
            return TableResolution(
                raw_value=raw_value,
                raw_unit=candidate.unit,
                display_value=str(candidate.values[col]),
                display_unit=candidate.unit,
                doc_id=candidate.doc_id,
                source_title=candidate.source_title,
                sheet_name=candidate.sheet_name,
                row_number=candidate.row_number if candidate.row_number < 10**9 else None,
                cell=cell,
                row_label=candidate.row_label,
                header_path=header_path,
                operation="lookup",
                calculation_trace=(f"{cell}={candidate.values[col]}",),
            )
        if ambiguous_column:
            return self._empty(constraints, "无法唯一确定口径列")
        return None

    def _cell_lookup(
        self, constraints: QuestionConstraints, cell: str
    ) -> TableResolution | None:
        """Resolve one explicit cell reference from canonical table-cell metadata."""
        requested_cell = cell.upper()
        candidates: list[RowCandidate] = []
        for item in self.retriever.search(
            self._query(constraints, requested_cell, ""), top_k=self.table_top_k
        ):
            if not self._compatible_item(item, constraints):
                continue
            item_cell = _metadata_cell(item, _metadata_row_number(item, str(item.get("text", ""))))
            if item_cell != requested_cell:
                continue
            candidate = _cell_chunk_candidate(item, requested_cell)
            if candidate:
                candidates.append(candidate)
        unique = {
            (candidate.doc_id, candidate.source_title, candidate.sheet_name, candidate.cell, tuple(candidate.values.items())):
            candidate
            for candidate in candidates
        }
        if len(unique) > 1:
            return self._empty(constraints, "无法唯一确定单元格")
        if not unique:
            return None
        candidate = next(iter(unique.values()))
        raw_value = _to_float(next(iter(candidate.values.values())))
        if raw_value is None:
            return None
        header_path = next(iter(candidate.header_path_by_col.values()), ())
        return TableResolution(
            raw_value=raw_value,
            raw_unit=candidate.unit,
            display_value=str(next(iter(candidate.values.values()))),
            display_unit=candidate.unit,
            doc_id=candidate.doc_id,
            source_title=candidate.source_title,
            sheet_name=candidate.sheet_name,
            row_number=candidate.row_number,
            cell=candidate.cell,
            row_label=candidate.row_label,
            header_path=header_path,
            operation="lookup",
            calculation_trace=(f"{candidate.cell}={next(iter(candidate.values.values()))}",),
        )

    def _resolve_calculation(
        self, constraints: QuestionConstraints, *, compatibility: bool = False
    ) -> TableResolution | None:
        operator = constraints.calculation_operator
        operands = constraints.calculation_operands
        if not operator or len(operands) != 2:
            return self._empty(constraints, "缺少明确算术操作")
        op = operator
        start_measure, end_measure = operands
        constant_values = (_to_float(start_measure), _to_float(end_measure))
        if all(value is not None for value in constant_values):
            start_value, end_value = constant_values
            assert start_value is not None and end_value is not None
            if op == "sum":
                raw_value = start_value + end_value
            elif op == "subtract":
                raw_value = start_value - end_value
            else:
                return self._empty(constraints, "常量计算仅支持加减")
            return TableResolution(
                raw_value=raw_value,
                raw_unit="",
                display_value=str(round(raw_value, 2)),
                display_unit="",
                doc_id="",
                source_title="",
                sheet_name="",
                row_number=None,
                cell="",
                row_label="常量计算",
                header_path=(),
                operation=op,
                calculation_trace=(f"{start_measure}={start_value}", f"{end_measure}={end_value}", f"{op}={raw_value}"),
            )
        target_label = constraints.metric
        if not target_label and not all(_CELL_REF_RE.fullmatch(value.upper()) for value in operands):
            return self._empty(constraints, "缺少行指标")
        target_constraints = replace(constraints, metric=target_label, measure=None)
        header_query = " ".join(
            part for part in (constraints.source_title, start_measure, end_measure) if part
        )
        if all(_CELL_REF_RE.fullmatch(value.upper()) for value in operands):
            start = self._cell_lookup(target_constraints, start_measure)
            end = self._cell_lookup(target_constraints, end_measure)
        else:
            start = self._lookup(
                replace(target_constraints, raw_question=f"{target_label} 在“{start_measure}”口径"),
                target_label,
                header_query,
                compatibility,
            )
            end = self._lookup(
                replace(target_constraints, raw_question=f"{target_label} 在“{end_measure}”口径"),
                target_label,
                header_query,
                compatibility,
            )
        if start and start.ambiguity_reason:
            return start
        if end and end.ambiguity_reason:
            return end
        if not start or not end:
            return None
        if start.raw_value is None or end.raw_value is None:
            return None
        if not compatibility and (not start.unit or not end.unit or start.unit != end.unit):
            return self._empty(constraints, "计算输入单位不一致")
        if not compatibility:
            same_document = bool(start.doc_id and end.doc_id and start.doc_id == end.doc_id)
            same_source = _source_matches(start.source_title, end.source_title)
            same_sheet = bool(
                start.sheet_name
                and end.sheet_name
                and start.sheet_name == end.sheet_name
            )
            same_row = bool(
                start.row_label and end.row_label and start.row_label == end.row_label
            )
            traced_headers = bool(start.header_path and end.header_path)
            if not (
                same_document
                and same_source
                and same_sheet
                and same_row
                and traced_headers
            ):
                return self._empty(constraints, "计算输入来源或口径不一致")
        if op == "ratio":
            if float(end.raw_value) == 0:
                return self._empty(constraints, "占比除数为零")
            raw_value = float(start.raw_value) / float(end.raw_value)
            unit = ""
        elif op == "sum":
            raw_value = float(start.raw_value) + float(end.raw_value)
            unit = end.unit or start.unit
        elif op == "subtract":
            raw_value = float(start.raw_value) - float(end.raw_value)
            unit = end.unit or start.unit
        else:
            raw_value = float(end.raw_value) - float(start.raw_value)
            unit = end.unit or start.unit
        operands = (
            TableOperand(
                label=start_measure,
                raw_value=start.raw_value,
                unit=start.unit,
                doc_id=start.doc_id,
                source_title=start.source_title,
                sheet_name=start.sheet_name,
                row=start.row_number,
                cell=start.cell,
                header_path=start.header_path,
                period=constraints.period or "",
            ),
            TableOperand(
                label=end_measure,
                raw_value=end.raw_value,
                unit=end.unit,
                doc_id=end.doc_id,
                source_title=end.source_title,
                sheet_name=end.sheet_name,
                row=end.row_number,
                cell=end.cell,
                header_path=end.header_path,
                period=constraints.period or "",
            ),
        )
        return TableResolution(
            raw_value=raw_value,
            raw_unit=unit,
            display_value=str(round(raw_value, 2)),
            display_unit=unit,
            doc_id=end.doc_id or start.doc_id,
            source_title=end.source_title or start.source_title,
            sheet_name=end.sheet_name or start.sheet_name,
            row_number=end.row_number,
            cell=end.cell,
            row_label=target_label,
            header_path=end.header_path,
            operation=op,
            calculation_trace=(*start.calculation_trace, *end.calculation_trace, f"{op}={raw_value}"),
            operands=operands,
        )

    def _period_ambiguity(
        self, constraints: QuestionConstraints, *, allow_title_year_legacy: bool = False
    ) -> TableResolution | None:
        if _is_period_sensitive(constraints) and not constraints.period:
            if allow_title_year_legacy and re.search(r"\d{4}年", constraints.source_title or ""):
                return None
            return self._empty(constraints, "缺少统计期间")
        return None

    def resolve(
        self, constraints: QuestionConstraints, *, compatibility: bool = False
    ) -> TableResolution | None:
        ambiguity = self._period_ambiguity(
            constraints, allow_title_year_legacy=compatibility
        )
        if ambiguity:
            return ambiguity
        if constraints.intent is QuestionIntent.TABLE_CALCULATE:
            return self._resolve_calculation(constraints, compatibility=compatibility)
        return self._lookup(constraints, compatibility=compatibility)

    def resolve_candidate(
        self, constraints: QuestionConstraints, label: str, *, compatibility: bool = False
    ) -> TableResolution | None:
        """Resolve a comparison candidate with the same title, period and measure."""
        candidate_constraints = replace(constraints, metric=label)
        return self.resolve(candidate_constraints, compatibility=compatibility)

    def compare(
        self, constraints: QuestionConstraints, labels: tuple[str, ...], *, compatibility: bool = False
    ) -> dict[str, TableResolution] | TableResolution | None:
        """Resolve every candidate, refusing a production comparison on any gap."""
        if not labels:
            return self._empty(constraints, "缺少明确比较候选")
        ambiguity = self._period_ambiguity(
            constraints, allow_title_year_legacy=compatibility
        )
        if ambiguity:
            return ambiguity
        resolved = {
            label: self.resolve_candidate(constraints, label, compatibility=compatibility)
            for label in labels
        }
        usable = {
            label: value
            for label, value in resolved.items()
            if value and value.raw_value is not None and not value.ambiguity_reason
        }
        if not any(value is not None for value in resolved.values()):
            return None
        ambiguous = next(
            (
                value
                for value in resolved.values()
                if value is not None and value.ambiguity_reason
            ),
            None,
        )
        if ambiguous and not compatibility:
            return ambiguous
        if not compatibility and len(usable) != len(labels):
            return None
        units = {value.unit for value in usable.values()}
        if not compatibility and (not units or "" in units or len(units) != 1):
            return self._empty(constraints, "比较候选单位不明确或不一致")
        if not compatibility:
            values = tuple(usable.values())
            doc_ids = {value.doc_id for value in values}
            normalized_titles = {
                _source_norm(value.source_title)
                for value in values
                if _source_norm(value.source_title)
            }
            sheets = {value.sheet_name for value in values}
            header_paths = {_norm("-".join(value.header_path)) for value in values}
            same_document = bool(doc_ids - {""}) and len(doc_ids) == 1 and "" not in doc_ids
            same_title_without_ids = (
                doc_ids == {""} and "" not in normalized_titles and len(normalized_titles) == 1
            )
            source_compatible = all(
                _source_matches(values[0].source_title, value.source_title) for value in values[1:]
            )
            if (
                not (same_document or same_title_without_ids)
                or not source_compatible
                or len(sheets) != 1
                or not header_paths
                or "" in header_paths
                or len(header_paths) != 1
            ):
                return self._empty(constraints, "比较候选来源或口径不一致")
        if compatibility:
            return usable

        direction = "min" if any(
            word in constraints.raw_question for word in ("最低", "最小", "更低")
        ) else "max"
        selected_label = (min if direction == "min" else max)(
            usable, key=lambda label: float(usable[label].raw_value)
        )
        selected = usable[selected_label]
        operands = tuple(
            TableOperand(
                label=label,
                raw_value=value.raw_value,
                unit=value.unit,
                doc_id=value.doc_id,
                source_title=value.source_title,
                sheet_name=value.sheet_name,
                row=value.row_number,
                cell=value.cell,
                header_path=value.header_path,
                period=constraints.period or "",
            )
            for label, value in usable.items()
            if value.raw_value is not None
        )
        return TableResolution(
            raw_value=selected.raw_value,
            raw_unit=selected.raw_unit,
            display_value=selected.display_value,
            display_unit=selected.display_unit,
            doc_id=selected.doc_id,
            source_title=selected.source_title,
            sheet_name=selected.sheet_name,
            row_number=selected.row_number,
            cell=selected.cell,
            row_label=selected_label,
            header_path=selected.header_path,
            operation=direction,
            calculation_trace=tuple(
                f"{operand.cell}={operand.raw_value}" for operand in operands
            )
            + (f"{direction}={selected_label}",),
            operands=operands,
        )
