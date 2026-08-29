import unittest

from src.generator.models import QuestionConstraints, QuestionIntent
from src.generator.table_resolver import StructuredTableResolver


class FixtureRetriever:
    def __init__(self, rows):
        self.rows = rows

    def search(self, question, top_k=5):
        return self.rows[:top_k]


class TableTraceTests(unittest.TestCase):
    def test_lookup_returns_sheet_cell_header_and_value(self):
        row = {
            "doc_id": "insurance-202312",
            "source_title": "2023年12月保险业经营情况表",
            "sheet_name": "保险业经营数据（月度）",
            "text": (
                "第5行：A列=原保险保费收入；C列=51246.71；"
                "上文表头/相邻行：C列=本年累计/截至当期；单位=亿元"
            ),
            "cell": "C5",
            "score": 1.0,
        }
        constraints = QuestionConstraints(
            raw_question="2023年12月保险业经营情况表中原保险保费收入本年累计是多少亿元？",
            intent=QuestionIntent.TABLE_LOOKUP,
            source_title="2023年12月保险业经营情况表",
            period="2023年12月",
            metric="原保险保费收入",
            measure="本年累计/截至当期",
            requested_unit="亿元",
        )

        result = StructuredTableResolver(FixtureRetriever([row])).resolve(constraints)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.raw_value, 51246.71)
        self.assertEqual(result.sheet_name, "保险业经营数据（月度）")
        self.assertEqual(result.cell, "C5")
        self.assertEqual(result.header_path, ("本年累计/截至当期",))


if __name__ == "__main__":
    unittest.main()
