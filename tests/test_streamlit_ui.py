import unittest

from app.ui_theme import (
    BANK_PLATFORM_CSS,
    backend_label,
    citation_location,
    confidence_presentation,
    consistency_label,
    coverage_presentation,
    format_match_score,
    intent_label,
    status_presentation,
)


class StreamlitUIThemeTests(unittest.TestCase):
    def test_bank_platform_css_keeps_the_approved_financial_design_language(self):
        required_tokens = {"#081B33", "#102A4C", "#C7A35A", "#F4F6F9", "#B33A3A"}
        for token in required_tokens:
            with self.subTest(token=token):
                self.assertIn(token, BANK_PLATFORM_CSS)
        self.assertIn("@media (max-width:767px)", BANK_PLATFORM_CSS)
        self.assertIn(
            '[data-testid="stVerticalBlock"] > [data-testid="stVerticalBlockBorderWrapper"]',
            BANK_PLATFORM_CSS,
        )
        self.assertNotIn('\n[data-testid="stVerticalBlockBorderWrapper"] {', BANK_PLATFORM_CSS)
        self.assertIn(".br-sidebar-foot {", BANK_PLATFORM_CSS)
        self.assertIn("position:static", BANK_PLATFORM_CSS)
        self.assertIn('[data-testid="stDecoration"]', BANK_PLATFORM_CSS)
        self.assertIn('[data-testid="stButton"] button[kind="primary"]', BANK_PLATFORM_CSS)
        self.assertIn('[data-testid="stHorizontalBlock"]', BANK_PLATFORM_CSS)
        self.assertIn("flex-direction:column !important", BANK_PLATFORM_CSS)

    def test_status_and_confidence_codes_are_translated(self):
        self.assertEqual(status_presentation("answered", 2)["label"], "证据充分")
        self.assertEqual(confidence_presentation("low")["label"], "低")
        self.assertEqual(intent_label("regulation_fact"), "监管制度问答")
        self.assertEqual(consistency_label("supported"), "证据一致")
        self.assertEqual(backend_label("deterministic_extractive"), "本地证据抽取")

    def test_metrics_preserve_backend_semantics(self):
        self.assertEqual(coverage_presentation(0.96)["value"], "96%")
        self.assertEqual(format_match_score(0.96321), "0.9632")
        self.assertNotIn("%", format_match_score(0.96321))

    def test_missing_source_coordinates_are_explicit(self):
        self.assertEqual(citation_location({}), "原数据未提供页码定位")


if __name__ == "__main__":
    unittest.main()
