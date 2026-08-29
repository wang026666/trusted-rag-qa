"""Unified offline orchestration and explicit trust-state transitions."""

from __future__ import annotations

import re

from src.generator.answerer import answer_regulation_question
from src.generator.models import (
    Citation,
    EvidenceTrace,
    QuestionConstraints,
    QuestionIntent,
    TableResolution,
    TableOperand,
    TrustStatus,
    UnifiedAnswerResult,
)
from src.generator.query_parser import parse_question
from src.generator.table_resolver import StructuredTableResolver
from src.retriever.hybrid import HybridRetriever
from src.retriever.tokenize import tokenize


MAX_TOP_K = 20
SUPPLEMENTAL_TOP_K = 20


def _base_result(
    constraints: QuestionConstraints,
    *,
    status: TrustStatus,
    answer: str,
    confidence: str = "low",
    support_coverage: float = 0.0,
    citations: tuple[Citation, ...] = (),
    evidence_trace: EvidenceTrace | None = None,
    consistency_status: str = "not_applicable",
    refusal_reason: str = "",
    generation_backend: str,
    fact_value: float | str | None = None,
    fact_unit: str = "",
) -> UnifiedAnswerResult:
    return UnifiedAnswerResult(
        question=constraints.raw_question,
        intent=constraints.intent,
        status=status,
        answer=answer,
        confidence=confidence,
        support_coverage=support_coverage,
        citations=citations,
        evidence_trace=evidence_trace,
        consistency_status=consistency_status,
        refusal_reason=refusal_reason,
        generation_backend=generation_backend,
        fact_value=fact_value,
        fact_unit=fact_unit,
    )


def out_of_scope_result(constraints: QuestionConstraints) -> UnifiedAnswerResult:
    reason = constraints.scope_reason or "该问题超出本资料库的可回答范围"
    return _base_result(
        constraints,
        status=TrustStatus.OUT_OF_SCOPE,
        answer=f"现有资料中没有足够依据回答该问题：{reason}。",
        refusal_reason=reason,
        generation_backend="deterministic_scope",
    )


def result_from_table_resolution(
    constraints: QuestionConstraints,
    resolution: TableResolution | None,
    *,
    allow_explicit_option_fallback: bool = False,
) -> UnifiedAnswerResult:
    if resolution is None:
        reason = "未找到与问题约束一致的表格事实"
        return _base_result(
            constraints,
            status=TrustStatus.INSUFFICIENT_EVIDENCE,
            answer="不足以根据资料回答。",
            refusal_reason=reason,
            generation_backend="deterministic_table_refusal",
        )
    if resolution.ambiguity_reason:
        return _base_result(
            constraints,
            status=TrustStatus.CLARIFICATION_REQUIRED,
            answer=f"需要补充信息：{resolution.ambiguity_reason}。",
            refusal_reason=resolution.ambiguity_reason,
            generation_backend="deterministic_clarification",
        )

    operands = resolution.operands
    fully_traced = bool(
        resolution.raw_value is not None
        and resolution.doc_id
        and resolution.source_title
        and resolution.cell
        and resolution.calculation_trace
    )
    if operands:
        doc_ids = {operand.doc_id for operand in operands}
        source_titles = {
            "".join(character for character in operand.source_title if character.isalnum()).lower()
            for operand in operands
        }
        sheets = {operand.sheet_name for operand in operands}
        periods = {operand.period for operand in operands}
        fully_traced = fully_traced and all(
            operand.doc_id
            and operand.source_title
            and operand.sheet_name
            and operand.cell
            and (
                allow_explicit_option_fallback
                or (operand.header_path and operand.period)
            )
            for operand in operands
        )
        compatible_provenance = all(
            len(values) == 1
            for values in (doc_ids, source_titles, sheets, periods)
        )
        fully_traced = fully_traced and compatible_provenance
        if constraints.period:
            fully_traced = fully_traced and periods == {constraints.period}
    if not fully_traced:
        reason = "表格事实缺少完整的来源、单元格或计算轨迹"
        return _base_result(
            constraints,
            status=TrustStatus.INSUFFICIENT_EVIDENCE,
            answer="不足以根据资料回答。",
            refusal_reason=reason,
            generation_backend="deterministic_table_refusal",
        )

    unit = resolution.display_unit or resolution.raw_unit
    if constraints.requested_unit and constraints.requested_unit in unit:
        unit = constraints.requested_unit
    label = resolution.row_label or constraints.metric or "表格事实"
    value = resolution.display_value or str(resolution.raw_value)
    if operands:
        citations = tuple(
            Citation(
                doc_id=operand.doc_id,
                source_title=operand.source_title,
                evidence=f"{operand.cell}={operand.raw_value}{operand.unit}",
                score=1.0,
                sheet_name=operand.sheet_name,
                cell=operand.cell,
            )
            for operand in operands
        )
    else:
        citations = (
            Citation(
                doc_id=resolution.doc_id,
                source_title=resolution.source_title,
                evidence="；".join(resolution.calculation_trace),
                score=1.0,
                sheet_name=resolution.sheet_name,
                cell=resolution.cell,
            ),
        )
    trace = EvidenceTrace(
        doc_id=resolution.doc_id,
        source_title=resolution.source_title,
        sheet_name=resolution.sheet_name,
        row=resolution.row_number,
        cell=resolution.cell,
        header_path=resolution.header_path,
        operation=resolution.operation,
        unit=unit,
        calculation_trace=resolution.calculation_trace,
        operands=operands,
    )
    return _base_result(
        constraints,
        status=TrustStatus.ANSWERED,
        answer=f"{label}：{value}{unit}。",
        confidence="high",
        support_coverage=1.0,
        citations=citations,
        evidence_trace=trace,
        consistency_status="supported",
        refusal_reason="",
        generation_backend="deterministic_table",
        fact_value=resolution.raw_value,
        fact_unit=unit,
    )


def _comparison_resolution_from_candidates(
    constraints: QuestionConstraints, candidates: dict[str, TableResolution]
) -> TableResolution | None:
    """Turn explicitly supplied MCQ candidates into one traced fact.

    This keeps legacy table-header fallbacks inside the shared answer engine.
    The evaluator still receives only a normal ``UnifiedAnswerResult`` and
    never reaches into a separate table-prediction path.
    """
    usable = {
        label: value
        for label, value in candidates.items()
        if value.raw_value is not None and value.doc_id and value.cell
    }
    if not usable:
        return None
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
        ) + (f"{direction}={selected_label}",),
        operands=operands,
    )


def _exception_query(constraints: QuestionConstraints) -> str:
    """Request both sides of the deposit-rule distinction when it is material."""
    if constraints.policy_rule_id == "consumer_finance_deposit_scope":
        return "消费金融公司 不吸收公众存款 接受股东及其境内子公司存款"
    return ""


def _merge_evidence(primary: list[dict], supplemental: list[dict]) -> list[dict]:
    merged: list[dict] = []
    seen: set[str] = set()
    for item in (*primary, *supplemental):
        key = str(item.get("chunk_id") or id(item))
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def _mcq_base_query(constraints: QuestionConstraints) -> str:
    """Keep an MCQ source lookup independent of the answer-option wording."""
    parts = [value for value in (constraints.source_title, constraints.sheet_name) if value]
    quoted_terms = re.findall(r"[“\"]([^”\"]+)[”\"]", constraints.raw_question)
    parts.extend(term.strip() for term in quoted_terms if term.strip())
    return " ".join(dict.fromkeys(parts)) or constraints.raw_question


def _source_keys(item: dict) -> set[str]:
    return {
        str(item.get(key, ""))
        for key in ("doc_id", "file_path", "file_label")
        if item.get(key)
    }


def _same_source(item: dict, allowed_sources: set[str]) -> bool:
    return bool(_source_keys(item) & allowed_sources)


def _option_support_score(option: str, evidence_text: str) -> float:
    option = str(option)
    if option and option in evidence_text:
        return 100.0
    tokens = set(tokenize(option))
    if not tokens:
        return 0.0
    return sum(token in evidence_text for token in tokens) / len(tokens)


def _citation_from_evidence(item: dict) -> Citation:
    text = re.sub(r"\s+", " ", str(item.get("text", ""))).strip()
    return Citation(
        doc_id=str(item.get("doc_id", "")),
        source_title=str(item.get("source_title", "")),
        evidence=text[:700],
        score=float(item.get("score", 0.0) or 0.0),
        relative_path=str(item.get("file_path", "")),
        sheet_name=str(item.get("sheet_name", "")),
        cell=str(item.get("cell", "")),
    )


class UnifiedQuestionEngine:
    def __init__(self, settings, retriever, table_resolver, llm=None):
        self.settings = settings
        self.retriever = retriever
        self.table_resolver = table_resolver
        self.llm = llm

    def _answer_mcq_options(
        self,
        constraints: QuestionConstraints,
        options: dict[str, str],
        top_k: int,
    ) -> UnifiedAnswerResult | None:
        """Verify exactly one MCQ candidate using evidence from the selected source."""
        base_query = _mcq_base_query(constraints)
        base_results = list(self.retriever.search(base_query, top_k=top_k))
        if not base_results:
            return None
        allowed_sources = _source_keys(base_results[0])
        if not allowed_sources:
            return None
        candidates: list[tuple[float, str, str, list[dict]]] = []
        for key, option in options.items():
            option_results = list(
                self.retriever.search(f"{base_query} {option}", top_k=top_k)
            )
            scoped = [
                item for item in option_results if _same_source(item, allowed_sources)
            ]
            if not scoped:
                continue
            evidence_text = " ".join(str(item.get("text", "")) for item in scoped)
            score = float(scoped[0].get("score", 0.0) or 0.0)
            score += 20.0 + _option_support_score(option, evidence_text) * 10.0
            candidates.append((score, key, option, scoped))
        if not candidates:
            return None
        candidates.sort(key=lambda candidate: candidate[0], reverse=True)
        best_score, _, best_option, best_evidence = candidates[0]
        if len(candidates) > 1 and candidates[1][0] == best_score:
            return _base_result(
                constraints,
                status=TrustStatus.CLARIFICATION_REQUIRED,
                answer="需要补充信息：多个候选项的证据支持度相同。",
                refusal_reason="多个候选项的证据支持度相同",
                generation_backend="deterministic_mcq_clarification",
            )
        return _base_result(
            constraints,
            status=TrustStatus.ANSWERED,
            answer=best_option,
            confidence="high" if best_score >= 8 else "medium",
            support_coverage=1.0,
            citations=(_citation_from_evidence(best_evidence[0]),),
            consistency_status="supported",
            generation_backend="deterministic_mcq",
        )

    def answer(
        self,
        question: str,
        top_k: int | None = None,
        options: dict[str, str] | None = None,
    ) -> UnifiedAnswerResult:
        requested_top_k = self.settings.top_k if top_k is None else top_k
        if (
            isinstance(requested_top_k, bool)
            or not isinstance(requested_top_k, int)
            or requested_top_k <= 0
        ):
            raise ValueError("top_k must be a positive integer")
        requested_top_k = min(requested_top_k, MAX_TOP_K)
        constraints = parse_question(question)
        if constraints.intent is QuestionIntent.OUT_OF_SCOPE:
            return out_of_scope_result(constraints)
        if constraints.scope_reason:
            return _base_result(
                constraints,
                status=TrustStatus.CLARIFICATION_REQUIRED,
                answer=f"需要补充信息：{constraints.scope_reason}。",
                refusal_reason=constraints.scope_reason,
                generation_backend="deterministic_clarification",
            )
        if constraints.intent is QuestionIntent.TABLE_COMPARE:
            labels = constraints.comparison_labels or tuple((options or {}).values())
            compatibility = bool(options)
            comparison = self.table_resolver.compare(
                constraints, labels, compatibility=compatibility
            )
            resolution = (
                _comparison_resolution_from_candidates(constraints, comparison)
                if isinstance(comparison, dict)
                else comparison
            )
            return result_from_table_resolution(
                constraints,
                resolution,
                allow_explicit_option_fallback=compatibility,
            )
        if constraints.intent in {
            QuestionIntent.TABLE_LOOKUP,
            QuestionIntent.TABLE_CALCULATE,
        }:
            # A supplied MCQ option set is an explicit finite candidate space.
            # It permits legacy header fallbacks while the resolution still
            # remains in this production engine and carries its cell trace.
            resolution = self.table_resolver.resolve(
                constraints, compatibility=bool(options)
            )
            return result_from_table_resolution(
                constraints,
                resolution,
                allow_explicit_option_fallback=bool(options),
            )

        if options:
            mcq_result = self._answer_mcq_options(constraints, options, requested_top_k)
            if mcq_result is not None:
                return mcq_result

        evidence = list(self.retriever.search(question, top_k=requested_top_k))
        supplemental_query = _exception_query(constraints)
        if supplemental_query:
            supplemental = list(
                self.retriever.search(supplemental_query, top_k=SUPPLEMENTAL_TOP_K)
            )
            evidence = _merge_evidence(evidence, supplemental)
        return answer_regulation_question(
            constraints=constraints,
            evidence=evidence,
            min_score=self.settings.min_score,
            llm=self.llm,
        )


def build_unified_engine(settings, retriever=None, llm=None) -> UnifiedQuestionEngine:
    retriever = retriever or HybridRetriever.from_index_dir(
        settings.index_dir, settings=settings
    )
    return UnifiedQuestionEngine(
        settings=settings,
        retriever=retriever,
        table_resolver=StructuredTableResolver(retriever),
        llm=llm,
    )


__all__ = [
    "MAX_TOP_K",
    "SUPPLEMENTAL_TOP_K",
    "UnifiedQuestionEngine",
    "build_unified_engine",
    "out_of_scope_result",
    "result_from_table_resolution",
]
