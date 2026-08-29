from __future__ import annotations

import re

from src.generator.consistency import validate_answer_consistency
from src.generator.models import (
    ClaimSupport,
    Citation,
    QuestionConstraints,
    RequiredClaim,
    TrustStatus,
    UnifiedAnswerResult,
)
from src.generator.question_type import classify_question


REFUSAL = "不足以根据资料回答。"
_MULTI_EVIDENCE_MARKERS = (
    "分别",
    "哪些",
    "以及",
    "同时",
    "比较",
    "差异",
    "列举",
    "包括哪些",
    "如何计算",
)
_EXPLICIT_OUT_OF_SCOPE_MARKERS = (
    "未公布",
    "尚未公开",
    "实时余额",
    "内部利润目标",
    "内部授信客户名单",
    "薪酬明细",
    "api key",
    "一定上涨",
)
_CONSUMER_DEPOSIT_POLICY_RULE_ID = "consumer_finance_deposit_scope"


def _clean_evidence(text: str, limit: int = 420) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _confidence(score: float) -> str:
    if score >= 8:
        return "high"
    if score >= 0.1:
        return "medium"
    return "low"


def _question_bigrams(question: str) -> set[str]:
    cjk = re.findall(r"[\u4e00-\u9fff]", question or "")
    bigrams = {a + b for a, b in zip(cjk, cjk[1:])}
    alnum = set(re.findall(r"[A-Za-z0-9_]{2,}", question or ""))
    return bigrams | alnum


def _support_coverage(question: str, evidence_text: str) -> float:
    terms = _question_bigrams(question)
    if len(terms) < 3:
        return 1.0
    matched = sum(1 for term in terms if term in evidence_text)
    return matched / len(terms)


def build_citation(item: dict) -> dict:
    return {
        "chunk_id": item.get("chunk_id", ""),
        "source_title": item.get("source_title", ""),
        "file_path": item.get("file_path", ""),
        "file_label": item.get("file_label", ""),
        "page": item.get("page", ""),
        "section": item.get("section", ""),
        "sheet_name": item.get("sheet_name", ""),
        "row": item.get("row", ""),
        "cell": item.get("cell", ""),
        "score": item.get("score", 0),
        "evidence": _clean_evidence(item.get("text", "")),
    }


def _answer_shape_bonus(question: str, text: str) -> float:
    bonus = 0.0
    if any(key in question for key in ("时限", "多少", "几名", "几家", "比例", "下限")):
        if re.search(r"\d+(?:\.\d+)?\s*(?:%|个工作日|个自然日|人|家|日|年)", text):
            bonus += 5.0
    if any(key in question for key in ("计算公式", "如何计算")):
        if any(marker in text for marker in ("=", "÷", "指标值")):
            bonus += 6.0
    if any(key in question for key in ("哪些", "分别", "包括")):
        if re.search(r"[（(][一-十\d]+[）)]|\d+[.、]", text):
            bonus += 2.0
    return bonus


def _evidence_answer_score(question: str, item: dict) -> float:
    text = re.sub(r"\s+", " ", item.get("text", "")).strip()
    terms = _question_bigrams(question)
    matched = sum(1 for term in terms if term in text)
    length_penalty = 4.0 if len(text) < 20 and not re.search(r"\d|[%=÷]", text) else 0.0
    source_haystack = " ".join(
        str(item.get(key, ""))
        for key in ("text", "source_title", "file_label")
    )
    quoted_source_bonus = 20.0 * sum(
        1
        for title in re.findall(r"《([^》]+)》", question)
        if title.strip() and title.strip() in source_haystack
    )
    return (
        float(matched)
        + _answer_shape_bonus(question, text)
        + quoted_source_bonus
        - length_penalty
    )


def _relevant_excerpt(question: str, text: str, limit: int = 700) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    terms = _question_bigrams(question)
    positions = [text.find(term) for term in terms if text.find(term) >= 0]
    if not positions:
        return _clean_evidence(text, limit)
    candidates = []
    for position in positions:
        start = max(0, min(position - limit // 2, len(text) - limit))
        excerpt = text[start : start + limit]
        score = sum(1 for term in terms if term in excerpt) + _answer_shape_bonus(question, excerpt)
        candidates.append((score, -start, start, excerpt))
    _, _, start, excerpt = max(candidates)
    prefix = "..." if start else ""
    suffix = "..." if start + limit < len(text) else ""
    return f"{prefix}{excerpt.rstrip()}{suffix}"


def _extractive_answer(question: str, evidence: list[dict]) -> str:
    return "根据检索证据：" + " ".join(
        _relevant_excerpt(question, item.get("text", "")) for item in evidence
    )


def _select_answer_evidence(question: str, evidence: list[dict]) -> list[dict]:
    limit = 3 if any(marker in question for marker in _MULTI_EVIDENCE_MARKERS) else 1
    ranked = sorted(
        enumerate(evidence),
        key=lambda pair: (_evidence_answer_score(question, pair[1]), -pair[0]),
        reverse=True,
    )
    if not ranked:
        return []
    if limit == 1:
        return [ranked[0][1]]
    best_score = _evidence_answer_score(question, ranked[0][1])
    threshold = max(1.0, best_score * 0.30)
    selected = [
        item
        for _, item in ranked
        if _evidence_answer_score(question, item) >= threshold
    ]
    return selected[:limit] or [ranked[0][1]]


def _is_explicitly_out_of_scope(question: str) -> bool:
    text = str(question or "").lower()
    return any(marker in text for marker in _EXPLICIT_OUT_OF_SCOPE_MARKERS)


def _refusal(question: str, question_type: str, coverage: float = 0.0) -> dict:
    return {
        "question": question,
        "question_type": question_type,
        "answer": REFUSAL,
        "confidence": "low",
        "support_coverage": round(coverage, 4),
        "citations": [],
        "generation_backend": "refusal",
        "consistency_status": "not_applicable",
        "consistency_score": 1.0,
        "supported_claims": [],
        "unsupported_claims": [],
    }


def _consistency_fields(result: dict) -> dict:
    return {
        "consistency_status": result["status"],
        "consistency_score": result["score"],
        "supported_claims": result["supported_claims"],
        "unsupported_claims": result["unsupported_claims"],
    }


def answer_question(
    question: str,
    evidence: list[dict],
    min_score: float = 0.05,
    min_coverage: float = 0.45,
    llm=None,
) -> dict:
    question_type = classify_question(question)
    if _is_explicitly_out_of_scope(question):
        return _refusal(question, question_type)
    best_score = evidence[0].get("score", 0) if evidence else 0
    if not evidence or best_score < min_score:
        return _refusal(question, question_type)

    top = evidence[:3]
    answer_evidence = _select_answer_evidence(question, top)
    evidence_text = " ".join(item.get("text", "") for item in top)
    coverage = _support_coverage(question, evidence_text)
    if coverage < min_coverage:
        return _refusal(question, question_type, coverage)

    citations = [build_citation(item) for item in top]
    answer_citations = [build_citation(item) for item in answer_evidence]
    llm_error = ""
    if llm is not None:
        try:
            generated = llm.generate(question, top, question_type)
            if generated:
                consistency = validate_answer_consistency(generated, top)
                if consistency["status"] == "unsupported":
                    return {
                        "question": question,
                        "question_type": question_type,
                        "answer": _extractive_answer(question, answer_evidence),
                        "confidence": _confidence(float(best_score)),
                        "support_coverage": round(coverage, 4),
                        "citations": answer_citations,
                        "generation_backend": "llm_consistency_fallback",
                        **_consistency_fields(consistency),
                    }
                return {
                    "question": question,
                    "question_type": question_type,
                    "answer": generated,
                    "confidence": _confidence(float(best_score)),
                    "support_coverage": round(coverage, 4),
                    "citations": citations,
                    "generation_backend": "llm",
                    **_consistency_fields(consistency),
                }
        except Exception as exc:
            llm_error = f"{type(exc).__name__}: {exc}"

    answer = _extractive_answer(question, answer_evidence)
    consistency = validate_answer_consistency(answer, answer_evidence)
    result = {
        "question": question,
        "question_type": question_type,
        "answer": answer,
        "confidence": _confidence(float(best_score)),
        "support_coverage": round(coverage, 4),
        "citations": answer_citations,
        "generation_backend": "extractive_fallback" if llm_error else "extractive",
        **_consistency_fields(consistency),
    }
    if llm_error:
        result["llm_error"] = llm_error
    return result


def _concept_coverage(
    required_concepts: tuple[str, ...], evidence: list[dict]
) -> tuple[float, tuple[str, ...]]:
    """Measure support against parsed domain concepts, not question phrasing."""
    if not required_concepts:
        return 1.0, ()
    evidence_text = "\n".join(str(item.get("text", "")) for item in evidence)
    aliases = {
        "消费金融公司": ("消费金融公司", "消金公司"),
        "股东": ("股东", "出资人"),
        "存款": ("存款", "存入款项"),
    }
    missing = tuple(
        concept
        for concept in required_concepts
        if not any(term in evidence_text for term in aliases.get(concept, (concept,)))
    )
    coverage = (len(required_concepts) - len(missing)) / len(required_concepts)
    return coverage, missing


def _bind_concepts_to_evidence(
    constraints: QuestionConstraints, evidence: list[dict]
) -> list[dict]:
    """Select at least one concrete evidence item for every supported fact concept."""
    selected: list[dict] = []
    for concept in constraints.required_concepts:
        item = next(
            (candidate for candidate in evidence if concept in str(candidate.get("text", ""))),
            None,
        )
        if item is not None and item not in selected:
            selected.append(item)

    if constraints.intent.value == "multi_fact":
        for item in _select_answer_evidence(constraints.raw_question, evidence):
            if item not in selected:
                selected.append(item)
    if not selected:
        selected = _select_answer_evidence(constraints.raw_question, evidence)
    return selected


def _claim_segments(text: str) -> tuple[str, ...]:
    return tuple(
        re.sub(r"\s+", "", segment)
        for segment in re.split(r"[\n，,。；;]+", str(text or ""))
        if segment.strip()
    )


def _sentence_segments(text: str) -> tuple[str, ...]:
    return tuple(
        re.sub(r"\s+", "", segment)
        for segment in re.split(r"[\n。；;]+", str(text or ""))
        if segment.strip()
    )


_EXPLICIT_SUBJECTS = (
    "消费金融公司",
    "商业银行",
    "银行业金融机构",
    "保险公司",
    "支付机构",
    "证券公司",
    "财务公司",
    "信托公司",
    "汽车金融公司",
    "金融租赁公司",
    "村镇银行",
)
_EXPLICIT_INSTITUTION_RE = re.compile(
    r"(?=([\u4e00-\u9fffA-Za-z0-9]{2,24}?(?:公司|银行|机构|委员会|部门)))"
)
_NORMATIVE_PREDICATE_RE = re.compile(
    r"不吸收|应当|必须|不得|禁止|不准|可以|不低于|接受|吸收|经营|开展|履行|保存|报告"
)
_REPORTING_ATTRIBUTION_RE = re.compile(
    r"(?:监管)?(?:简报|新闻|报告|材料)(?:显示|称|指出|载明)$"
)


def _subject_aliases(subject: str) -> tuple[str, ...]:
    return {
        "消费金融公司": ("消费金融公司", "消金公司"),
        "股东": ("股东", "出资人"),
        "银行": ("商业银行", "银行业金融机构", "银行"),
    }.get(subject, (subject,))


def _normative_subject_relations(subject: str, segment: str) -> tuple[str, ...]:
    aliases = _subject_aliases(subject)
    relations: list[str] = []
    for predicate in _NORMATIVE_PREDICATE_RE.finditer(segment):
        prefix = segment[: predicate.start()]
        spans = tuple(
            (matched.start(1), matched.end(1))
            for matched in _EXPLICIT_INSTITUTION_RE.finditer(prefix)
        )
        if not spans:
            continue
        nearest_end = max(end for _, end in spans)
        target_spans = tuple(
            (matched.start(), matched.end())
            for alias in aliases
            for matched in re.finditer(re.escape(alias), prefix)
        )
        if any(end == nearest_end for _, end in target_spans):
            tail = prefix[nearest_end:]
            relations.append(
                "attribution" if _REPORTING_ATTRIBUTION_RE.search(tail) else "target"
            )
        else:
            relations.append("different")
    return tuple(relations)


def _has_different_explicit_subject(subject: str, segment: str) -> bool:
    relations = _normative_subject_relations(subject, segment)
    if relations:
        return any(relation != "target" for relation in relations)
    aliases = _subject_aliases(subject)
    return any(
        candidate in segment
        and not any(candidate in alias or alias in candidate for alias in aliases)
        for candidate in _EXPLICIT_SUBJECTS
    )


def _subject_supported(subject: str, segment: str) -> bool:
    if not subject:
        return False
    aliases = _subject_aliases(subject)
    relations = _normative_subject_relations(subject, segment)
    if relations:
        return "target" in relations and all(
            relation == "target" for relation in relations
        )
    return (
        any(alias in segment for alias in aliases)
        and not _has_different_explicit_subject(subject, segment)
    )


def _object_supported(claim_object: str, segment: str) -> bool:
    if claim_object == "账簿划分政策":
        return "账簿划分" in segment and "政策" in segment
    if claim_object == "股东及其境内子公司的存款":
        owner_supported = any(term in segment for term in ("股东", "出资人"))
        deposit_supported = any(term in segment for term in ("存款", "存入款项"))
        return owner_supported and "境内子公司" in segment and deposit_supported
    return claim_object in segment


def _predicate_supported(claim: RequiredClaim, segment: str) -> bool:
    if claim.predicate == "建立":
        return any(term in segment for term in ("建立", "制定"))
    if claim.predicate == "监管要求":
        return any(
            term in segment
            for term in ("应当", "不得", "必须", "可以", "要求", "不低于")
        )
    if claim.predicate == "吸收":
        return "吸收" in segment
    if claim.predicate == "接受":
        return "接受" in segment and "拒绝接受" not in segment
    return claim.predicate in segment


def _polarity_supported(polarity: str, segment: str) -> bool:
    if polarity == "negative":
        return any(term in segment for term in ("不吸收", "不得", "禁止", "不准"))
    if polarity == "positive":
        return any(term in segment for term in ("可以", "可接受", "可经营"))
    return any(
        term in segment
        for term in ("应当", "必须", "不得", "禁止", "不准", "可以", "要求", "不低于")
    )


def _consumer_enumeration_windows(
    segments: tuple[str, ...], claim: RequiredClaim
) -> tuple[str, ...]:
    windows: list[str] = []
    for governing, item in zip(segments, segments[1:]):
        has_governing_relation = (
            _subject_supported(claim.subject, governing)
            and any(
                predicate in governing
                for predicate in ("可以经营", "可经营", "可以开展", "经营范围", "业务包括")
            )
            and any(marker in governing for marker in ("下列", "包括", "：", ":"))
        )
        enumerated_item = bool(
            re.match(r"^(?:[（(][一二三四五六七八九十\d]+[）)]|[一二三四五六七八九十\d]+[.、])", item)
        )
        if (
            has_governing_relation
            and enumerated_item
            and not _has_different_explicit_subject(claim.subject, item)
        ):
            windows.append(governing + item)
    return tuple(windows)


def _item_supports_claim(item: dict, claim: RequiredClaim) -> bool:
    text = str(item.get("text", ""))
    if claim.claim_id.startswith("consumer_deposit_"):
        segments = _sentence_segments(text)
        windows = (*segments, *_consumer_enumeration_windows(segments, claim))
    else:
        segments = _claim_segments(text)
        windows = segments
    return any(
        _subject_supported(claim.subject, segment)
        and _object_supported(claim.object, segment)
        and _predicate_supported(claim, segment)
        and _polarity_supported(claim.polarity, segment)
        and all(qualifier in segment for qualifier in claim.qualifiers)
        for segment in windows
    )


def _source_key(item: dict) -> str:
    return re.sub(
        r"[\s_（）()：:，,。、《》.\-]+",
        "",
        str(item.get("source_title", "")),
    ).lower()


def _claim_evidence_bindings(
    constraints: QuestionConstraints, evidence: list[dict]
) -> tuple[list[dict], tuple[ClaimSupport, ...]] | None:
    if not constraints.required_claims:
        return [], ()
    candidates = {
        claim.claim_id: [item for item in evidence if _item_supports_claim(item, claim)]
        for claim in constraints.required_claims
    }
    if any(not items for items in candidates.values()):
        return None

    bindings: list[tuple[RequiredClaim, dict]] = []
    if constraints.policy_rule_id == _CONSUMER_DEPOSIT_POLICY_RULE_ID:
        principle, exception = constraints.required_claims
        matched_pair = next(
            (
                (left, right)
                for left in candidates[principle.claim_id]
                for right in candidates[exception.claim_id]
                if left.get("doc_id")
                and left.get("doc_id") == right.get("doc_id")
                and _source_key(left)
                and _source_key(left) == _source_key(right)
            ),
            None,
        )
        if matched_pair is None:
            return None
        bindings = [(principle, matched_pair[0]), (exception, matched_pair[1])]
    else:
        bindings = [
            (claim, candidates[claim.claim_id][0])
            for claim in constraints.required_claims
        ]

    selected: list[dict] = []
    for _, item in bindings:
        if item not in selected:
            selected.append(item)
    supports = tuple(
        ClaimSupport(claim_id=claim.claim_id, citation_indexes=(selected.index(item),))
        for claim, item in bindings
    )
    return selected, supports


def _typed_citation(question: str, item: dict) -> Citation:
    doc_id = str(item.get("doc_id", ""))
    if not doc_id:
        doc_id = str(item.get("chunk_id", "")).split("::", 1)[0]
    return Citation(
        doc_id=doc_id,
        source_title=str(item.get("source_title", "")),
        evidence=_relevant_excerpt(question, str(item.get("text", ""))),
        score=float(item.get("score", 0.0)),
        relative_path=str(item.get("file_label") or item.get("file_path") or ""),
        sheet_name=str(item.get("sheet_name", "")),
        cell=str(item.get("cell", "")),
    )


def _regulation_refusal(
    constraints: QuestionConstraints,
    coverage: float,
    reason: str,
) -> UnifiedAnswerResult:
    return UnifiedAnswerResult(
        question=constraints.raw_question,
        intent=constraints.intent,
        status=TrustStatus.INSUFFICIENT_EVIDENCE,
        answer=REFUSAL,
        confidence="low",
        support_coverage=round(coverage, 4),
        citations=(),
        evidence_trace=None,
        consistency_status="not_applicable",
        refusal_reason=reason,
        generation_backend="deterministic_refusal",
    )


def answer_regulation_question(
    constraints: QuestionConstraints,
    evidence: list[dict],
    min_score: float = 0.05,
    llm=None,
) -> UnifiedAnswerResult:
    """Return a typed, evidence-bound answer for a regulatory question."""
    eligible_evidence = [
        item for item in evidence if float(item.get("score", 0.0)) >= min_score
    ]
    best_score = max(
        (float(item.get("score", 0.0)) for item in eligible_evidence), default=0.0
    )
    if not eligible_evidence:
        return _regulation_refusal(constraints, 0.0, "未检索到达到阈值的事实证据")

    if constraints.intent.value == "multi_fact" and not constraints.required_claims:
        return _regulation_refusal(
            constraints, 0.0, "无法将多事实问题解析为完整的待支持声明"
        )

    coverage, missing = _concept_coverage(
        constraints.required_concepts, eligible_evidence
    )
    if missing:
        return _regulation_refusal(
            constraints,
            coverage,
            "以下必需概念未被证据完整支持：" + "、".join(missing),
        )
    if constraints.required_claims:
        claim_bindings = _claim_evidence_bindings(constraints, eligible_evidence)
        if claim_bindings is None:
            return _regulation_refusal(
                constraints, coverage, "至少一项必需事实无法绑定到同一证据片段"
            )
        answer_evidence, claim_supports = claim_bindings
    else:
        answer_evidence = _bind_concepts_to_evidence(
            constraints, eligible_evidence
        )
        claim_supports = ()
    if not answer_evidence:
        return _regulation_refusal(constraints, coverage, "无法将回答事实绑定到具体证据")

    deterministic_answer = _extractive_answer(constraints.raw_question, answer_evidence)
    citations = tuple(_typed_citation(constraints.raw_question, item) for item in answer_evidence)
    deterministic_consistency = validate_answer_consistency(
        deterministic_answer, answer_evidence
    )

    if llm is not None:
        try:
            generated = llm.generate(
                constraints.raw_question,
                answer_evidence,
                classify_question(constraints.raw_question),
            )
            if generated:
                consistency = validate_answer_consistency(generated, answer_evidence)
                if consistency["status"] == "supported":
                    return UnifiedAnswerResult(
                        question=constraints.raw_question,
                        intent=constraints.intent,
                        status=TrustStatus.ANSWERED,
                        answer=generated,
                        confidence=_confidence(best_score),
                        support_coverage=round(coverage, 4),
                        citations=citations,
                        evidence_trace=None,
                        consistency_status="supported",
                        refusal_reason="",
                        generation_backend="llm",
                        claim_supports=claim_supports,
                    )
        except Exception:
            pass

    return UnifiedAnswerResult(
        question=constraints.raw_question,
        intent=constraints.intent,
        status=TrustStatus.ANSWERED,
        answer=deterministic_answer,
        confidence=_confidence(best_score),
        support_coverage=round(coverage, 4),
        citations=citations,
        evidence_trace=None,
        consistency_status=str(deterministic_consistency["status"]),
        refusal_reason="",
        generation_backend="deterministic_extractive",
        claim_supports=claim_supports,
    )


def choose_mcq_option(question: str, options: dict[str, str], evidence: list[dict]) -> str:
    if not evidence:
        return ""
    evidence_text = " ".join(item.get("text", "") for item in evidence)
    scores: dict[str, int] = {}
    for key, option in options.items():
        tokens = set(re.findall(r"[\u4e00-\u9fffa-zA-Z0-9.]+", str(option)))
        scores[key] = sum(1 for token in tokens if token and token in evidence_text)
    return max(scores, key=scores.get) if scores else ""
