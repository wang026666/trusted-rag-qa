import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "run_eval.py"


def _load_run_eval_module():
    spec = importlib.util.spec_from_file_location("run_eval", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DevelopmentMcqProtocolTests(unittest.TestCase):
    def test_free_form_records_restore_original_unanswerable_cases(self) -> None:
        module = _load_run_eval_module()
        source = [
            {"id": "A001", "question": "可回答问题", "answerable": True},
            {"id": "U001", "question": "资料外问题一", "answerable": False},
            {"id": "U002", "question": "资料外问题二", "answerable": False},
        ]

        records = module.free_form_records_from_source(source)

        self.assertEqual(
            records,
            [
                {
                    "record_type": "free_form_eval",
                    "id": "U001",
                    "question": "资料外问题一",
                    "expected_behavior": "refusal_or_clarification_without_citation",
                },
                {
                    "record_type": "free_form_eval",
                    "id": "U002",
                    "question": "资料外问题二",
                    "expected_behavior": "refusal_or_clarification_without_citation",
                },
            ],
        )

    def test_xlsx_seed_uses_standard_library_fallback_when_pandas_is_unavailable(self) -> None:
        module = _load_run_eval_module()
        headers = ["id", "question", "option_a", "option_b", "option_c", "option_d"]
        values = headers + ["Q001", "题目", "A", "B", "C", "D"]
        shared = "".join(f"<si><t>{value}</t></si>" for value in values)
        header_cells = "".join(
            f'<c r="{chr(65 + index)}1" t="s"><v>{index}</v></c>'
            for index in range(len(headers))
        )
        value_cells = "".join(
            f'<c r="{chr(65 + index)}2" t="s"><v>{index + len(headers)}</v></c>'
            for index in range(len(headers))
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "development.xlsx"
            with ZipFile(path, "w") as archive:
                archive.writestr(
                    "xl/sharedStrings.xml",
                    '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                    f"{shared}</sst>",
                )
                archive.writestr(
                    "xl/worksheets/sheet1.xml",
                    '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                    f"<sheetData><row r=\"1\">{header_cells}</row><row r=\"2\">{value_cells}</row></sheetData>"
                    "</worksheet>",
                )

            rows = module._load_xlsx_rows(path)

        self.assertEqual(rows, [{"id": "Q001", "question": "题目", "option_a": "A", "option_b": "B", "option_c": "C", "option_d": "D"}])

    def test_development_mcq_record_retains_all_required_fields(self) -> None:
        module = _load_run_eval_module()
        source = {
            "id": "Q001",
            "question": "根据附件，下列哪项正确？",
            "option_a": "A项",
            "option_b": "B项",
            "option_c": "C项",
            "option_d": "D项",
            "answer": "C",
            "answer_text": "C项",
            "source_type": "word",
            "qa_type": "单事实检索",
            "source_title": "示例制度",
            "evidence": "评测证据",
        }

        record = module.development_mcq_record(source)

        self.assertEqual(
            set(source),
            {key for key in source if record[key] == source[key]},
        )
        self.assertEqual(record["record_type"], "development_mcq")

    def test_mcq_maps_engine_fact_to_exact_option_without_text_threshold(self) -> None:
        from src.evaluator.metrics import map_fact_to_option
        from src.generator.models import TrustStatus

        result = SimpleNamespace(
            status=TrustStatus.ANSWERED,
            fact_value=3267.58,
            answer="3267.58",
        )

        predicted = map_fact_to_option(
            result,
            {"A": "38433.67", "B": "3267.58", "C": "130.18", "D": "0"},
        )

        self.assertEqual(predicted, "B")

    def test_mcq_summary_uses_exact_predicted_option_equality(self) -> None:
        from src.evaluator.metrics import summarize_mcq_rows

        summary = summarize_mcq_rows(
            [
                {"qa_type": "单事实检索", "answer": "A", "predicted": "A", "source_hit": True},
                {"qa_type": "单事实检索", "answer": "B", "predicted": "A", "source_hit": True},
                {"qa_type": "表格取数", "answer": "D", "predicted": "D", "source_hit": False},
            ]
        )

        self.assertEqual(summary["overall_accuracy"], {"correct": 2, "total": 3, "rate": 2 / 3})
        self.assertEqual(summary["by_qa_type"]["单事实检索"]["correct"], 1)
        self.assertEqual(summary["by_qa_type"]["表格取数"]["correct"], 1)
        self.assertEqual(summary["citation_source_hit_rate"], {"hit": 2, "total": 3, "rate": 2 / 3})


if __name__ == "__main__":
    unittest.main()
