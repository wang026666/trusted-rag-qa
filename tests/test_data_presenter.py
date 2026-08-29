import json
from pathlib import Path

from app.data_presenter import (
    build_database_counts,
    build_document_rows,
    build_domain_counts,
    build_format_counts,
    build_runtime_context,
    index_health,
    load_evaluation_snapshot,
    load_index_summary,
    load_manifest,
    report_preflight,
)


def test_domain_counts_are_exhaustive_and_mutually_exclusive():
    """Removing precedence or the fallback bucket must break total reconciliation."""
    records = [
        {"title": "商业银行资本管理办法", "file_type": "pdf"},
        {"title": "流动性风险管理办法", "file_type": "pdf"},
        {"title": "银行业总资产月度统计表", "file_type": "xls"},
        {"title": "消费者权益保护办法", "file_type": "docx"},
    ]

    assert build_domain_counts(records) == {
        "资本监管": 1,
        "流动性监管": 1,
        "风险管理": 0,
        "统计制度": 1,
        "其他": 1,
    }


def test_manifest_loader_skips_blank_lines_and_keeps_real_fields(tmp_path):
    """A blank line must not become a fake document record."""
    path = tmp_path / "manifest.jsonl"
    path.write_text(
        '{"doc_id":"nfra_001","title":"月度统计","file_type":"xls"}\n\n'
        '{"doc_id":"nfra_002","title":"资本办法","file_type":"pdf"}\n',
        encoding="utf-8",
    )

    assert load_manifest(path) == [
        {"doc_id": "nfra_001", "title": "月度统计", "file_type": "xls"},
        {"doc_id": "nfra_002", "title": "资本办法", "file_type": "pdf"},
    ]


def test_evaluation_snapshot_preserves_development_set_scope(tmp_path):
    """The development metric must never be relabelled as live answer accuracy."""
    path = tmp_path / "metrics.json"
    path.write_text(
        json.dumps(
            {
                "development_mcq": {
                    "citation_source_hit_rate": {"rate": 0.98, "total": 300}
                }
            }
        ),
        encoding="utf-8",
    )

    assert load_evaluation_snapshot(path) == {
        "citation_source_hit_rate": 0.98,
        "citation_source_total": 300,
        "scope_label": "开发集评测快照",
    }


def test_missing_or_malformed_json_degrades_to_empty_mapping(tmp_path):
    """Missing artifacts must not be replaced with hard-coded business values."""
    missing = tmp_path / "missing.json"
    malformed = tmp_path / "bad.json"
    malformed.write_text("not-json", encoding="utf-8")

    assert load_index_summary(missing) == {}
    assert load_index_summary(malformed) == {}


def test_document_rows_never_invent_update_time_or_source_link():
    """Unavailable manifest fields must remain visibly unavailable."""
    rows = build_document_rows(
        [
            {
                "doc_id": "nfra_001",
                "title": "月度统计",
                "file_type": "xls",
                "sha256": "abcdef1234567890",
                "source_url": "",
            }
        ]
    )

    assert rows[0] == {
        "文档编号": "nfra_001",
        "资料名称": "月度统计",
        "文件类型": "XLS",
        "来源链接": "未提供",
        "校验摘要": "abcdef123456",
        "索引状态": "已索引",
        "业务更新时间": "未提供",
    }


def test_format_and_database_counts_are_reconciled():
    """Format grouping or database grouping must account for every record once."""
    records = [
        {"title": "A", "file_type": "pdf"},
        {"title": "B", "file_type": "xls"},
        {"title": "C", "file_type": "xlsx"},
        {"title": "D", "file_type": "docx"},
        {"title": "E", "file_type": "txt"},
    ]

    assert build_format_counts(records) == {
        "PDF": 1,
        "XLS/XLSX": 2,
        "DOC/DOCX": 1,
        "其他": 1,
    }
    assert build_database_counts(records) == {
        "监管制度库": 3,
        "统计报表库": 2,
        "案例库": 0,
    }


def test_report_preflight_accepts_only_bounded_csv_or_xlsx():
    """A UI-only preflight must not imply analysis, persistence, or macro support."""
    accepted = report_preflight(
        "G01.xlsx",
        2048,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    macro = report_preflight(
        "G01.xlsm",
        2048,
        "application/vnd.ms-excel.sheet.macroEnabled.12",
    )
    oversized = report_preflight("G01.csv", 21 * 1024 * 1024, "text/csv")

    assert accepted["accepted"] is True
    assert accepted["analysis_status"] == "未执行"
    assert accepted["persistence"] == "不写入知识库"
    assert macro["accepted"] is False
    assert oversized["accepted"] is False


def test_index_health_requires_both_nonempty_indexes(tmp_path):
    """One present index must not mark the whole retrieval layer ready."""
    index_dir = tmp_path / "indexes"
    index_dir.mkdir()
    (index_dir / "bm25_index.json").write_text(
        json.dumps({"k1": 1.5, "b": 0.75, "documents": [{"chunk_id": "a", "text": "制度"}]}),
        encoding="utf-8",
    )

    health = index_health(index_dir, {"failure_count": 0, "table_cell_count": 12})

    assert health["ready"] is False
    assert health["bm25_ready"] is True
    assert health["vector_ready"] is False
    assert health["failure_count"] == 0
    assert health["table_cell_count"] == 12


def test_index_health_rejects_parseable_but_empty_index_payloads(tmp_path):
    """Replacing a real index with `{}` must disable retrieval rather than look ready."""
    index_dir = tmp_path / "indexes"
    index_dir.mkdir()
    (index_dir / "bm25_index.json").write_text("{}", encoding="utf-8")
    (index_dir / "vector_index.json").write_text("{}", encoding="utf-8")

    health = index_health(index_dir, {"failure_count": 0, "table_cell_count": 12})

    assert health["ready"] is False
    assert health["bm25_ready"] is False
    assert health["vector_ready"] is False


def test_index_health_rejects_misaligned_bm25_and_vector_documents(tmp_path):
    """Matching files with different chunk identities must not enable hybrid retrieval."""
    index_dir = tmp_path / "indexes"
    index_dir.mkdir()
    (index_dir / "bm25_index.json").write_text(
        json.dumps({"k1": 1.5, "b": 0.75, "documents": [{"chunk_id": "a", "text": "制度"}]}),
        encoding="utf-8",
    )
    (index_dir / "vector_index.json").write_text(
        json.dumps({"backend": "local_tfidf", "documents": [{"chunk_id": "b", "text": "制度"}]}),
        encoding="utf-8",
    )

    health = index_health(index_dir, {})

    assert health["bm25_ready"] is True
    assert health["vector_ready"] is True
    assert health["ready"] is False


def test_runtime_context_reconciles_all_artifact_views(tmp_path):
    """Dashboard and knowledge views must consume one consistent artifact snapshot."""
    index_dir = tmp_path / "outputs" / "indexes"
    knowledge_dir = tmp_path / "knowledge_base"
    evaluation_dir = tmp_path / "evaluation"
    index_dir.mkdir(parents=True)
    knowledge_dir.mkdir()
    evaluation_dir.mkdir()
    documents = [
        {"chunk_id": "a", "text": "资本办法"},
        {"chunk_id": "b", "text": "月度统计"},
    ]
    (index_dir / "bm25_index.json").write_text(
        json.dumps({"k1": 1.5, "b": 0.75, "documents": documents}), encoding="utf-8"
    )
    (index_dir / "vector_index.json").write_text(
        json.dumps({"backend": "local_tfidf", "documents": documents}), encoding="utf-8"
    )
    (index_dir / "index_summary.json").write_text(
        json.dumps(
            {
                "manifest_count": 2,
                "chunk_count": 12,
                "table_cell_count": 8,
                "failure_count": 0,
            }
        ),
        encoding="utf-8",
    )
    (evaluation_dir / "metrics.json").write_text(
        json.dumps(
            {"development_mcq": {"citation_source_hit_rate": {"rate": 0.98, "total": 300}}}
        ),
        encoding="utf-8",
    )
    (knowledge_dir / "manifest.jsonl").write_text(
        '{"doc_id":"a","title":"资本办法","file_type":"pdf"}\n'
        '{"doc_id":"b","title":"月度统计","file_type":"xls"}\n',
        encoding="utf-8",
    )

    context = build_runtime_context(tmp_path)

    assert context["manifest_count_matches"] is True
    assert context["domain_counts"] == {
        "资本监管": 1,
        "流动性监管": 0,
        "风险管理": 0,
        "统计制度": 1,
        "其他": 0,
    }
    assert context["format_counts"]["PDF"] == 1
    assert context["database_counts"]["统计报表库"] == 1
    assert context["health"]["ready"] is True
    assert context["evaluation"]["scope_label"] == "开发集评测快照"
