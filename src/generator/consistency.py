from __future__ import annotations

import re
import unicodedata


_CLAIM_PATTERNS = (
    (
        "date",
        re.compile(r"(?<!\d)(?:19|20)\d{2}年(?:0?[1-9]|1[0-2])月(?:0?[1-9]|[12]\d|3[01])日"),
    ),
    ("date", re.compile(r"(?<!\d)(?:19|20)\d{2}[-/.](?:0?[1-9]|1[0-2])[-/.](?:0?[1-9]|[12]\d|3[01])(?!\d)")),
    ("document_number", re.compile(r"[\u4e00-\u9fffA-Za-z]{0,16}[〔（(]\d{4}[〕）)]\s*\d+\s*号")),
    ("article", re.compile(r"第[零〇一二两三四五六七八九十百千万\d]+[章条款项]")),
    ("percentage", re.compile(r"(?<!\d)\d+(?:\.\d+)?\s*[%％]")),
    (
        "number_with_unit",
        re.compile(
            r"(?<!\d)\d+(?:\.\d+)?\s*(?:万亿元|亿元|万元|元|个工作日|工作日|个月|年|月|日|倍|户|家|笔)(?![\u4e00-\u9fff])"
        ),
    ),
    (
        "organization",
        re.compile(
            r"(?:国家金融监督管理总局|中国人民银行|中国银行保险监督管理委员会|中国银保监会|财政部|国家统计局)"
        ),
    ),
)

_CN_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
_CN_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000}


def _chinese_number_to_int(value: str) -> int | None:
    if value.isdigit():
        return int(value)
    if not value or any(char not in _CN_DIGITS and char not in _CN_UNITS for char in value):
        return None

    total = 0
    section = 0
    number = 0
    for char in value:
        if char in _CN_DIGITS:
            number = _CN_DIGITS[char]
            continue
        unit = _CN_UNITS[char]
        if unit == 10000:
            section = (section + number) * unit
            total += section
            section = 0
            number = 0
        else:
            section += (number or 1) * unit
            number = 0
    return total + section + number


def _canonical_claim(claim: dict[str, str]) -> tuple[str, str]:
    claim_type = claim["type"]
    value = unicodedata.normalize("NFKC", claim["value"])
    value = re.sub(r"\s+", "", value)

    if claim_type == "article":
        match = re.fullmatch(r"第(.+)([章条款项])", value)
        if match:
            number = _chinese_number_to_int(match.group(1))
            if number is not None:
                value = f"第{number}{match.group(2)}"
    elif claim_type == "percentage":
        number = value.rstrip("%")
        value = f"{float(number):g}%"
    elif claim_type == "date":
        parts = re.findall(r"\d+", value)
        if len(parts) == 3:
            value = f"{int(parts[0]):04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"
    elif claim_type == "number_with_unit":
        match = re.fullmatch(r"(\d+(?:\.\d+)?)(.+)", value)
        if match:
            value = f"{float(match.group(1)):g}{match.group(2)}"
    elif claim_type == "document_number":
        value = value.replace("（", "(").replace("）", ")").replace("〔", "(").replace("〕", ")")
        prefix, separator, suffix = value.partition("(")
        if separator:
            for marker in ("依据", "根据", "按照", "依照", "参照"):
                if marker in prefix:
                    prefix = prefix.rsplit(marker, 1)[-1]
            value = f"{prefix}({suffix}"

    return claim_type, value


def extract_critical_claims(text: str) -> list[dict[str, str]]:
    normalized = unicodedata.normalize("NFKC", text or "")
    occupied: list[tuple[int, int]] = []
    matches: list[tuple[int, dict[str, str]]] = []

    for claim_type, pattern in _CLAIM_PATTERNS:
        for match in pattern.finditer(normalized):
            span = match.span()
            if any(span[0] < end and start < span[1] for start, end in occupied):
                continue
            occupied.append(span)
            matches.append(
                (
                    span[0],
                    {
                        "type": claim_type,
                        "value": match.group(0).strip().replace("％", "%"),
                    },
                )
            )

    matches.sort(key=lambda item: item[0])
    seen: set[tuple[str, str]] = set()
    claims: list[dict[str, str]] = []
    for _, claim in matches:
        canonical = _canonical_claim(claim)
        if canonical in seen:
            continue
        seen.add(canonical)
        claims.append(claim)
    return claims


def validate_answer_consistency(answer: str, evidence: list[dict]) -> dict:
    answer_claims = extract_critical_claims(answer)
    if not answer_claims:
        return {
            "status": "not_applicable",
            "score": 1.0,
            "supported_claims": [],
            "unsupported_claims": [],
        }

    evidence_text = "\n".join(str(item.get("text", "")) for item in evidence)
    evidence_claims = extract_critical_claims(evidence_text)
    evidence_keys = {_canonical_claim(claim) for claim in evidence_claims}
    supported = [claim for claim in answer_claims if _canonical_claim(claim) in evidence_keys]
    unsupported = [claim for claim in answer_claims if _canonical_claim(claim) not in evidence_keys]
    score = len(supported) / len(answer_claims)
    return {
        "status": "supported" if not unsupported else "unsupported",
        "score": round(score, 4),
        "supported_claims": supported,
        "unsupported_claims": unsupported,
    }
