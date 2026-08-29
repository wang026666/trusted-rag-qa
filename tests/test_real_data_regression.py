"""Regression checks against the shipped local index and real source facts."""

from __future__ import annotations

import unittest

from src.config.settings import get_settings
from src.generator.models import TrustStatus
from src.generator.unified_engine import build_unified_engine


class RealDataRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = build_unified_engine(get_settings(), llm=None)

    def test_real_regulation_query(self) -> None:
        result = self.engine.answer("商业银行大额风险暴露制度有哪些主要监管要求？")

        self.assertIs(result.status, TrustStatus.ANSWERED)
        self.assertTrue(result.citations)
        self.assertIn("大额风险暴露", result.answer)

    def test_real_table_beijing(self) -> None:
        result = self.engine.answer("2025年9月北京原保险保费收入合计是多少？")

        self.assertIs(result.status, TrustStatus.ANSWERED)
        self.assertAlmostEqual(float(result.fact_value), 3267.58, places=2)
        self.assertIsNotNone(result.evidence_trace)
        assert result.evidence_trace is not None
        self.assertEqual(result.evidence_trace.source_title, "2025年9月全国各地区原保险保费收入情况表")
        self.assertEqual(result.evidence_trace.cell, "C5")

    def test_out_of_scope_refusal(self) -> None:
        result = self.engine.answer("火星上有多少家商业银行？")

        self.assertIn(
            result.status,
            {TrustStatus.OUT_OF_SCOPE, TrustStatus.INSUFFICIENT_EVIDENCE},
        )
        self.assertEqual(result.confidence, "low")
        self.assertFalse(result.citations)

    def test_rejects_unsupported_internal_business_target(self) -> None:
        result = self.engine.answer("火星银行2028年的内部利润目标是多少？")

        self.assertIn(
            result.status,
            {TrustStatus.OUT_OF_SCOPE, TrustStatus.INSUFFICIENT_EVIDENCE},
        )
        self.assertEqual(result.confidence, "low")
        self.assertFalse(result.citations)
        self.assertIn("没有足够依据", result.answer)

    def test_rejects_specific_employee_compensation_detail(self) -> None:
        result = self.engine.answer("南京银行某支行所有员工的最新薪酬明细是多少？")

        self.assertIn(
            result.status,
            {TrustStatus.OUT_OF_SCOPE, TrustStatus.INSUFFICIENT_EVIDENCE},
        )
        self.assertEqual(result.confidence, "low")
        self.assertFalse(result.citations)
        self.assertIn("没有足够依据", result.answer)

    def test_real_xls_lookup(self) -> None:
        result = self.engine.answer(
            "请从2026年银行业总资产、总负债（月度）表中取数："
            "银行业金融机构2026年1月总资产是多少？"
        )

        self.assertIs(result.status, TrustStatus.ANSWERED)
        self.assertAlmostEqual(float(result.fact_value), 4806061.691219, places=3)
        self.assertIsNotNone(result.evidence_trace)
        assert result.evidence_trace is not None
        self.assertEqual(result.evidence_trace.source_title, "2026年银行业总资产、总负债（月度）")
        self.assertEqual(result.evidence_trace.header_path, ("2026年", "1月"))


if __name__ == "__main__":
    unittest.main()
