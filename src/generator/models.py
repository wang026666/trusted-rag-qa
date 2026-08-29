"""Immutable public contracts for trusted question answering."""

from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
from pathlib import PurePosixPath, PureWindowsPath


def _serialize(value: object) -> object:
    """Convert contract values to JSON-compatible public data."""
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {key: _serialize(item) for key, item in asdict(value).items()}
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    return value


class TrustStatus(str, Enum):
    ANSWERED = "answered"
    CLARIFICATION_REQUIRED = "clarification_required"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    OUT_OF_SCOPE = "out_of_scope"


class QuestionIntent(str, Enum):
    REGULATION_FACT = "regulation_fact"
    MULTI_FACT = "multi_fact"
    TABLE_LOOKUP = "table_lookup"
    TABLE_COMPARE = "table_compare"
    TABLE_CALCULATE = "table_calculate"
    OUT_OF_SCOPE = "out_of_scope"


@dataclass(frozen=True)
class RequiredClaim:
    claim_id: str
    subject: str
    polarity: str
    predicate: str
    object: str
    qualifiers: tuple[str, ...] = ()
    required_phrase: str = ""

    def to_dict(self) -> dict[str, object]:
        return _serialize(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class QuestionConstraints:
    raw_question: str
    normalized_question: str = ""
    intent: QuestionIntent = QuestionIntent.REGULATION_FACT
    source_title: str | None = None
    sheet_name: str | None = None
    period: str | None = None
    institution: str | None = None
    region: str | None = None
    metric: str | None = None
    measure: str | None = None
    operation: str | None = None
    calculation_operator: str | None = None
    calculation_operands: tuple[str, ...] = ()
    requested_unit: str | None = None
    required_concepts: tuple[str, ...] = ()
    required_claims: tuple[RequiredClaim, ...] = ()
    comparison_labels: tuple[str, ...] = ()
    policy_rule_id: str = ""
    scope_reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return _serialize(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class Citation:
    doc_id: str
    source_title: str
    evidence: str
    score: float
    relative_path: str = ""
    sheet_name: str = ""
    cell: str = ""

    def __post_init__(self) -> None:
        path = self.relative_path
        windows_path = PureWindowsPath(path)
        is_windows_rooted = bool(windows_path.root) and path.startswith("\\")
        if (
            PurePosixPath(path).is_absolute()
            or windows_path.is_absolute()
            or is_windows_rooted
        ):
            object.__setattr__(self, "relative_path", windows_path.name)

    def to_dict(self) -> dict[str, object]:
        return _serialize(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class TableOperand:
    label: str
    raw_value: float | str
    unit: str
    doc_id: str
    source_title: str
    sheet_name: str
    row: int | None
    cell: str
    header_path: tuple[str, ...]
    period: str = ""

    def to_dict(self) -> dict[str, object]:
        return _serialize(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class EvidenceTrace:
    doc_id: str
    source_title: str
    sheet_name: str = ""
    row: int | None = None
    cell: str = ""
    header_path: tuple[str, ...] = ()
    operation: str = ""
    unit: str = ""
    calculation_trace: tuple[str, ...] = ()
    operands: tuple[TableOperand, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return _serialize(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class TableResolution:
    raw_value: float | str | None
    raw_unit: str
    display_value: str
    display_unit: str
    doc_id: str
    source_title: str
    sheet_name: str
    row_number: int | None
    cell: str
    row_label: str
    header_path: tuple[str, ...]
    operation: str
    calculation_trace: tuple[str, ...]
    ambiguity_reason: str = ""
    operands: tuple[TableOperand, ...] = ()

    @property
    def unit(self) -> str:
        return self.display_unit or self.raw_unit

    def to_dict(self) -> dict[str, object]:
        return _serialize(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class ClaimSupport:
    claim_id: str
    citation_indexes: tuple[int, ...]

    def to_dict(self) -> dict[str, object]:
        return _serialize(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class UnifiedAnswerResult:
    question: str
    intent: QuestionIntent
    status: TrustStatus
    answer: str
    confidence: str
    support_coverage: float
    citations: tuple[Citation, ...]
    evidence_trace: EvidenceTrace | None
    consistency_status: str
    refusal_reason: str
    generation_backend: str
    generation_error_type: str = ""
    fact_value: float | str | None = None
    fact_unit: str = ""
    claim_supports: tuple[ClaimSupport, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return _serialize(self)  # type: ignore[return-value]
