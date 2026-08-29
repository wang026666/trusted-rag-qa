"""Deterministic parsing of trusted-RAG question constraints."""

from __future__ import annotations

import re

from src.generator.models import QuestionConstraints, QuestionIntent, RequiredClaim


OUT_OF_SCOPE_RULES = (
    (("实时账户余额", "实时余额", "个人账户", "交易明细", "银行卡交易", "交易流水", "每笔交易", "员工薪酬"), "资料库不包含个人或内部实时数据"),
    (("api key", "apikey", "密钥", "内部风险规则"), "请求涉及凭据或未公开安全信息"),
    (("预测", "一定上涨", "明天将获批", "未公布", "未公开"), "请求涉及未来或未公开事实"),
)

# Public regulatory materials can describe general management requirements, but
# cannot establish an institution's non-public operating targets or an
# employee-level compensation record.  These are request classes, not entity
# or case identifiers, so the rule applies independently of a bank's name.
_NONPUBLIC_FACT_SCOPE_PATTERNS = (
    (
        re.compile(r"(?:内部|非公开|私有).{0,12}(?:利润|经营).{0,12}(?:目标|预算|计划|预测)|(?:内部|非公开|私有).{0,12}(?:目标|预算|计划|预测).{0,12}(?:利润|经营)"),
        "资料库不包含机构内部经营目标或预算信息",
    ),
    (
        re.compile(r"(?:所有|全体|具体|个人|某)?(?:员工|职工|人员).{0,12}(?:薪酬|工资|奖金).{0,12}(?:明细|名单|记录)|(?:薪酬|工资|奖金).{0,12}(?:明细|名单|记录)"),
        "资料库不包含个人或机构内部薪酬明细",
    ),
)

_AMBIGUOUS_REQUESTS = (
    ("办法规定的报送期限", "未明确具体办法或报送事项"),
    ("保险公司经营情况怎样", "未明确保险公司、期间或经营指标"),
)

POLITE_PREFIXES = ("请问", "请说明", "请给出", "麻烦", "不用写文件名")
MEASURE_ALIASES = {
    "本年累计": "本年累计/截至当期",
    "截至当期": "本年累计/截至当期",
    "账面余额": "截至当期-账面余额",
    "合计": "合计",
}

_TABLE_MARKERS = ("工作表", "Excel", "取数")
_NAMED_TABLE_SUFFIXES = ("经营情况表", "资产负债情况表", "统计表", "指标表", "明细表")
_GENERIC_TABLE_TITLES = ("表", "报表", "表格", "该表", "此表")
_CALCULATE_MARKERS = ("计算", "相差", "差额", "增减", "变化", "占比", "同比", "环比")
_COMPARE_MARKERS = ("比较", "对比", "差异", "最高", "最低", "更高", "更低")
_MULTI_FACT_MARKERS = ("分别", "各自", "以及", "同时", "并且", "两项", "多项")
_INSTITUTIONS = (
    "大型商业银行",
    "股份制商业银行",
    "外资银行",
    "商业银行",
    "银行业金融机构",
    "保险公司",
    "保险业",
    "银行",
)
_METRICS = (
    "原保险保费收入",
    "原保险赔付支出",
    "新增保险金额",
    "资金运用余额",
    "可疑类贷款余额",
    "损失类贷款余额",
    "正常类贷款",
    "核心一级资本充足率",
    "资本充足率",
    "杠杆率",
    "总资产",
    "总负债",
)
_REGULATORY_NOUNS = (
    "交易账簿",
    "银行账簿",
    "划分政策",
    "政策和程序",
    "监管规则",
    "报送",
    "填报",
    "监管指标",
    "风险管理",
)
_NORMATIVE_TERMS = ("原则上", "除外", "例外", "不得", "禁止", "不准", "可以", "应当", "必须")
_REGIONS = ("全国", "各地区", "北京", "上海", "广东", "深圳")
_UNITS = ("万亿元", "亿元", "万元", "元", "百分点", "%")
_CONSUMER_COMPANY_ALIASES = ("消费金融公司", "消金公司")
_SHAREHOLDER_ALIASES = ("股东", "出资人")
_DEPOSIT_ALIASES = ("存款", "存入款项")
CONSUMER_DEPOSIT_POLICY_RULE_ID = "consumer_finance_deposit_scope"
_ARITHMETIC_GENERIC_TERMS = (
    "多少",
    "什么",
    "如何",
    "怎么",
    "哪项",
    "哪个",
    "是否",
    "请问",
    "结果",
)
_NATURAL_ARITHMETIC_RE = re.compile(
    r"(?:^|[,，:：]|表(?:中|内))"
    r"(?P<target>[\u4e00-\u9fffA-Za-z0-9_%\-]{1,24})的"
    r"(?P<left>[\u4e00-\u9fffA-Za-z0-9_%\-]{1,24}?)"
    r"(?P<operator>加(?!强)|减(?!少))"
    r"(?P<right>[\u4e00-\u9fffA-Za-z0-9_%\-]{1,24}?)"
    r"(?:是多少|等于(?:多少)?)"
)
_QUOTED_ARITHMETIC_RE = re.compile(
    r"[“\"‘'](?P<target>[^”\"’']+)[”\"’']的"
    r"[“\"‘'](?P<left>[^”\"’']+)[”\"’']"
    r"(?P<operator>加(?!强)|减(?!少)|合计|差额|相差|变化|占比)"
    r"[“\"‘'](?P<right>[^”\"’']+)[”\"’']"
)
_QUOTED_RANGE_DIFFERENCE_RE = re.compile(
    r"[“\"‘'](?P<target>[^”\"’']+)[”\"’']从"
    r"[“\"‘'](?P<left>[^”\"’']+)[”\"’']到"
    r"[“\"‘'](?P<right>[^”\"’']+)[”\"’']"
    r".{0,24}(?:变化|差额|相差)"
)
_NUMERIC_OR_CELL_ARITHMETIC_RE = re.compile(
    r"(?P<left>(?:\d+(?:\.\d+)?|[A-Z]+[1-9]\d*))"
    r"\s*(?P<operator>加(?!强)|减(?!少))\s*"
    r"(?P<right>(?:\d+(?:\.\d+)?|[A-Z]+[1-9]\d*))"
)
_CALCULATION_OPERATOR_NAMES = {
    "加": "sum",
    "合计": "sum",
    "减": "subtract",
    "差额": "difference",
    "相差": "difference",
    "变化": "difference",
    "占比": "ratio",
}


def normalize_question(text: str) -> str:
    """Normalize spacing and punctuation without weakening question meaning."""
    return re.sub(r"\s+", "", str(text or "").strip()).translate(
        str.maketrans({"（": "(", "）": ")", "：": ":", "，": ",", "？": "?"})
    )


def _first_present(text: str, terms: tuple[str, ...]) -> str | None:
    return next((term for term in terms if term in text), None)


def _nonpublic_scope_reason(text: str) -> str:
    return next(
        (reason for pattern, reason in _NONPUBLIC_FACT_SCOPE_PATTERNS if pattern.search(text)),
        "",
    )


def _extract_source_title(text: str) -> str | None:
    quoted = re.search(r"《([^》]+)》", text)
    if quoted:
        return quoted.group(1).strip() or None

    explicit_table = re.search(
        r"(?P<title>\d{4}年[^，,。；;:：?？]{0,100}?表)(?=(?:中|内|里|取数|的|[,，。；;:：?？]|$))",
        text,
    )
    if explicit_table:
        return explicit_table.group("title").strip()

    table_end = text.find("表")
    if table_end < 0:
        return None
    prefix = text[: table_end + 1]
    dated_title = re.search(r"\d{4}年(?:\d{1,2}月|第[一二三四五六七八九十\d]+季度)?.*表$", prefix)
    if dated_title:
        title = dated_title.group(0)
        period = re.match(r"\d{4}年(?:\d{1,2}月|第[一二三四五六七八九十\d]+季度)", title)
        if period and title[period.end() :].lstrip("的") not in _GENERIC_TABLE_TITLES:
            return title

    for suffix in _NAMED_TABLE_SUFFIXES:
        suffix_end = text.find(suffix)
        if suffix_end < 0:
            continue
        fragment = text[: suffix_end + len(suffix)]
        fragment = re.split(r"[，,。；;：:?！？]", fragment)[-1]
        for prefix in (*POLITE_PREFIXES, "根据", "在", "查询", "附件", "Excel", "excel"):
            if fragment.startswith(prefix):
                fragment = fragment[len(prefix) :]
        return fragment.strip("《》\"“” ") or None
    return None


def _extract_sheet_name(text: str) -> str | None:
    matched = re.search(r"工作表\s*[:：]?\s*[《\"“]?([^》\"”()，,。；;?？]+)", text)
    return matched.group(1).strip() if matched else None


def _extract_period(text: str) -> str | None:
    # Source tables use both “2023年4季度” and “2023年第4季度”.  Both
    # forms identify the table period and are equally explicit.
    matched = re.search(
        r"\d{4}年(?:\d{1,2}月|第?[一二三四五六七八九十\d]+季度)", text
    )
    return matched.group(0) if matched else None


def _extract_measure(text: str) -> str | None:
    for alias, canonical in MEASURE_ALIASES.items():
        if alias in text:
            return canonical
    return None


def _explicit_location_entities(text: str) -> tuple[str, ...]:
    """Return a location explicitly asserted as the subject of a fact question.

    A retrieved document must mention this entity before a factual answer is
    accepted.  This prevents a lexical match on a generic institution term
    from turning an unsupported place-specific question into an answer.
    """
    entities: list[str] = []
    for match in re.finditer(
        r"(?P<entity>[\u4e00-\u9fff]{2,12})(?:上|内|外)(?:有|共有|存在)", text
    ):
        entity = match.group("entity").strip()
        if entity and entity not in entities:
            entities.append(entity)
    return tuple(entities)


def _infer_regional_table_title(
    source_title: str | None,
    period: str | None,
    region: str | None,
    metric: str | None,
) -> str | None:
    """Bind regional premium questions to their designated regional table."""
    if source_title or not (period and region and metric):
        return source_title
    if metric == "原保险保费收入":
        return f"{period}全国各地区原保险保费收入情况表"
    return None


def _required_concepts(text: str, measure: str | None, scope_terms: tuple[str, ...]) -> tuple[str, ...]:
    concepts: list[str] = []
    for term in (
        *_INSTITUTIONS,
        *_METRICS,
        *_REGULATORY_NOUNS,
        *_NORMATIVE_TERMS,
    ):
        if (
            term in text
            and term not in concepts
            and not any(term in existing for existing in concepts)
        ):
            concepts.append(term)
    for term in scope_terms:
        if term not in concepts:
            concepts.append(term)
    if measure and measure not in concepts:
        concepts.append(measure)
    return tuple(concepts)


def _policy_rule_id(text: str) -> str:
    if (
        any(alias in text for alias in _CONSUMER_COMPANY_ALIASES)
        and any(alias in text for alias in _SHAREHOLDER_ALIASES)
        and any(alias in text for alias in _DEPOSIT_ALIASES)
    ):
        return CONSUMER_DEPOSIT_POLICY_RULE_ID
    return ""


def _specific_present(text: str, terms: tuple[str, ...]) -> tuple[str, ...]:
    selected: list[str] = []
    for term in terms:
        if term in text and not any(term in existing for existing in selected):
            selected.append(term)
    return tuple(selected)


def _comparison_labels(text: str, intent: QuestionIntent) -> tuple[str, ...]:
    if intent is not QuestionIntent.TABLE_COMPARE:
        return ()
    metrics = _specific_present(text, _METRICS)
    if len(metrics) >= 2:
        return metrics
    institutions = _specific_present(text, _INSTITUTIONS)
    if len(institutions) >= 2:
        return institutions
    quoted = tuple(
        term.strip()
        for term in re.findall(r"[“\"]([^”\"]+)[”\"]", text)
        if term.strip()
    )
    if len(set(quoted)) >= 2:
        return tuple(dict.fromkeys(quoted))
    bounded = re.search(
        r"(?:比较|对比)(.{1,80}?)(?:哪个|哪项|谁|孰|的差异)", text
    )
    if not bounded:
        return ()
    labels = tuple(
        label.strip()
        for label in re.split(r"和|与|、", bounded.group(1))
        if 1 <= len(label.strip()) <= 30
    )
    return labels if len(labels) >= 2 else ()


def _claim_polarity(text: str) -> str:
    if any(term in text for term in ("不得", "禁止", "不准", "不吸收")):
        return "negative"
    if any(term in text for term in ("可以", "能否", "是否可以")):
        return "positive"
    return "normative"


def _claim_qualifiers(text: str) -> tuple[str, ...]:
    qualifiers: list[str] = []
    for pattern in (
        r"在([^,。?]{1,30})下",
        r"仅当([^,。?]{1,30})时",
        r"除([^,。?]{1,30})外",
    ):
        for match in re.finditer(pattern, text):
            qualifier = match.group(1).strip()
            if qualifier and qualifier not in qualifiers:
                qualifiers.append(qualifier)
    return tuple(qualifiers)


def _required_claims(
    text: str,
    intent: QuestionIntent,
    institution: str | None,
    policy_rule_id: str,
    qualifiers: tuple[str, ...],
) -> tuple[RequiredClaim, ...]:
    if policy_rule_id == CONSUMER_DEPOSIT_POLICY_RULE_ID:
        return (
            RequiredClaim(
                claim_id="consumer_deposit_principle",
                subject="消费金融公司",
                polarity="negative",
                predicate="吸收",
                object="公众存款",
                required_phrase="不吸收公众存款",
            ),
            RequiredClaim(
                claim_id="consumer_deposit_exception",
                subject="消费金融公司",
                polarity="positive",
                predicate="接受",
                object="股东及其境内子公司的存款",
                required_phrase="可以接受股东及其境内子公司的存款",
            ),
        )

    metrics = _specific_present(text, _METRICS)
    if metrics:
        subject = institution or ""
        polarity = _claim_polarity(text)
        return tuple(
            RequiredClaim(
                claim_id=f"regulatory_metric_{index + 1}",
                subject=subject,
                polarity=polarity,
                predicate="监管要求",
                object=metric,
                qualifiers=qualifiers,
            )
            for index, metric in enumerate(metrics)
        )

    if intent is QuestionIntent.MULTI_FACT:
        object_list = re.search(
            r"在(.{2,160}?)方面(?:应当|必须|需要|应)履行", text
        )
        predicate = "履行"
        if object_list is None and institution:
            object_list = re.search(
                re.escape(institution) + r"(.{2,160}?)(?:的)?监管要求", text
            )
            predicate = "监管要求"
        if object_list and institution:
            objects = tuple(
                re.sub(r"(?:的)?(?:相关)?(?:义务|要求)$", "", item.strip())
                for item in re.split(r"以及|并且|同时|[,、]|和|与", object_list.group(1))
                if re.sub(r"(?:的)?(?:相关)?(?:义务|要求)$", "", item.strip())
            )
            if len(objects) >= 2:
                return tuple(
                    RequiredClaim(
                        claim_id=f"regulatory_duty_{index + 1}",
                        subject=institution,
                        polarity="normative",
                        predicate=predicate,
                        object=claim_object,
                        qualifiers=qualifiers,
                    )
                    for index, claim_object in enumerate(objects)
                )

    if intent is QuestionIntent.MULTI_FACT and "交易账簿" in text and "银行账簿" in text:
        return (
            RequiredClaim(
                claim_id="book_classification_policy",
                subject=institution or "银行",
                polarity="normative",
                predicate="建立",
                object="账簿划分政策",
                qualifiers=qualifiers,
            ),
        )
    return ()


def _extract_bounded_natural_arithmetic(
    text: str,
) -> tuple[str, str, str, str] | None:
    if not re.search(
        r"(?:\d{4}年(?:\d{1,2}月|第[一二三四五六七八九十\d]+季度)?.{0,40}表|表(?:中|内)|工作表)",
        text,
    ):
        return None
    matched = _NATURAL_ARITHMETIC_RE.search(text)
    if not matched:
        return None
    target, left, right = (
        matched.group("target"),
        matched.group("left"),
        matched.group("right"),
    )
    if any(
        generic in operand
        for operand in (left, right)
        for generic in _ARITHMETIC_GENERIC_TERMS
    ):
        return None
    return target, left, right, matched.group("operator")


def _calculation_contract(
    text: str,
) -> tuple[str | None, str | None, tuple[str, ...]]:
    """Parse arithmetic once so later stages never reinterpret question text."""
    natural = _extract_bounded_natural_arithmetic(text)
    if natural:
        target, left, right, operator = natural
        return target, _CALCULATION_OPERATOR_NAMES[operator], (left, right)
    quoted_range = _QUOTED_RANGE_DIFFERENCE_RE.search(text)
    if quoted_range:
        return (
            quoted_range.group("target").strip(),
            "difference",
            (quoted_range.group("left").strip(), quoted_range.group("right").strip()),
        )
    quoted = _QUOTED_ARITHMETIC_RE.search(text)
    if quoted:
        return (
            quoted.group("target").strip(),
            _CALCULATION_OPERATOR_NAMES[quoted.group("operator")],
            (quoted.group("left").strip(), quoted.group("right").strip()),
        )
    direct = _NUMERIC_OR_CELL_ARITHMETIC_RE.search(text)
    if direct:
        return (
            None,
            _CALCULATION_OPERATOR_NAMES[direct.group("operator")],
            (direct.group("left"), direct.group("right")),
        )
    return None, None, ()


def _has_explicit_calculation(
    text: str, contract: tuple[str | None, str | None, tuple[str, ...]] | None = None
) -> bool:
    if contract is None:
        contract = _calculation_contract(text)
    if contract[1]:
        return True
    if _first_present(text, _CALCULATE_MARKERS):
        return True
    return False


def _classify_intent(
    text: str,
    source_title: str | None,
    measure: str | None,
    calculation: tuple[str | None, str | None, tuple[str, ...]],
) -> tuple[QuestionIntent, str]:
    if _has_explicit_calculation(text, calculation):
        return QuestionIntent.TABLE_CALCULATE, "calculate"
    if _first_present(text, _COMPARE_MARKERS):
        return QuestionIntent.TABLE_COMPARE, "compare"
    if any(marker in text for marker in _MULTI_FACT_MARKERS):
        return QuestionIntent.MULTI_FACT, ""
    source_is_table = bool(
        source_title
        and any(source_title.endswith(suffix) for suffix in _NAMED_TABLE_SUFFIXES)
    )
    if source_is_table or measure or any(marker in text for marker in _TABLE_MARKERS):
        return QuestionIntent.TABLE_LOOKUP, "lookup"
    return QuestionIntent.REGULATION_FACT, ""


def parse_question(question: str) -> QuestionConstraints:
    """Parse only explicit constraints; never infer a missing period or source."""
    raw_question = str(question or "")
    normalized = normalize_question(raw_question)
    lower_text = normalized.lower()

    for terms, reason in OUT_OF_SCOPE_RULES:
        matched_terms = tuple(term for term in terms if term in lower_text)
        if matched_terms:
            return QuestionConstraints(
                raw_question=raw_question,
                normalized_question=normalized,
                intent=QuestionIntent.OUT_OF_SCOPE,
                required_concepts=_required_concepts(normalized, None, matched_terms),
                scope_reason=reason,
            )

    nonpublic_reason = _nonpublic_scope_reason(normalized)
    if nonpublic_reason:
        return QuestionConstraints(
            raw_question=raw_question,
            normalized_question=normalized,
            intent=QuestionIntent.OUT_OF_SCOPE,
            scope_reason=nonpublic_reason,
        )

    for phrase, reason in _AMBIGUOUS_REQUESTS:
        if phrase in normalized:
            return QuestionConstraints(
                raw_question=raw_question,
                normalized_question=normalized,
                intent=QuestionIntent.REGULATION_FACT,
                scope_reason=reason,
            )

    source_title = _extract_source_title(normalized)
    measure = _extract_measure(normalized)
    calculation_target, calculation_operator, calculation_operands = _calculation_contract(normalized)
    intent, operation = _classify_intent(
        normalized, source_title, measure,
        (calculation_target, calculation_operator, calculation_operands),
    )
    metric = calculation_target or _first_present(normalized, _METRICS)
    institution = _first_present(normalized, _INSTITUTIONS)
    region = _first_present(normalized, _REGIONS)
    period = _extract_period(normalized)
    source_title = _infer_regional_table_title(source_title, period, region, metric)
    requested_unit = _first_present(normalized, _UNITS)
    policy_rule_id = _policy_rule_id(normalized)
    claim_qualifiers = _claim_qualifiers(normalized)
    required_concepts = list(
        _required_concepts(normalized, measure, _explicit_location_entities(normalized))
    )
    if policy_rule_id:
        for concept in ("消费金融公司", "股东", "存款"):
            if concept not in required_concepts:
                required_concepts.append(concept)

    return QuestionConstraints(
        raw_question=raw_question,
        normalized_question=normalized,
        intent=intent,
        source_title=source_title,
        sheet_name=_extract_sheet_name(normalized),
        period=period,
        institution=institution,
        region=region,
        metric=metric,
        measure=measure,
        operation=operation or None,
        calculation_operator=calculation_operator,
        calculation_operands=calculation_operands,
        requested_unit=requested_unit,
        required_concepts=tuple(required_concepts),
        required_claims=_required_claims(
            normalized,
            intent,
            institution,
            policy_rule_id,
            claim_qualifiers,
        ),
        comparison_labels=_comparison_labels(normalized, intent),
        policy_rule_id=policy_rule_id,
    )
