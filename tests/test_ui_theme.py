import unittest

from app.ui_theme import (
    QUICK_QUESTIONS,
    backend_label,
    citation_location,
    citations_for_display,
    confidence_presentation,
    consistency_label,
    coverage_presentation,
    format_match_score,
    intent_label,
    status_presentation,
)


class TrustedRAGThemeTests(unittest.TestCase):
    def test_answered_status_is_rendered_as_a_positive_evidence_state(self):
        """Removing the trusted-state branch must not expose a raw status code."""
        presentation = status_presentation("answered", citation_count=3)

        self.assertEqual(presentation["label"], "证据充分")
        self.assertEqual(presentation["tone"], "success")
        self.assertEqual(presentation["detail"], "已引用 3 条可核验证据")

    def test_unsupported_status_is_rendered_as_a_safe_warning(self):
        """Unsafe answers must remain visibly distinct from supported answers."""
        presentation = status_presentation("out_of_scope", citation_count=0)

        self.assertEqual(presentation["label"], "资料库范围外")
        self.assertEqual(presentation["tone"], "danger")
        self.assertEqual(presentation["detail"], "未引用可支持当前问题的资料")

    def test_unknown_status_never_leaks_internal_codes_to_the_interface(self):
        """A newly introduced backend status should degrade to reader-facing wording."""
        presentation = status_presentation("backend_pending_review", citation_count=1)

        self.assertEqual(presentation["label"], "状态待核验")
        self.assertEqual(presentation["tone"], "neutral")
        self.assertEqual(presentation["detail"], "已引用 1 条可核验证据")

    def test_quick_questions_cover_the_three_primary_query_paths(self):
        """The home workspace must guide policy, table, and comparison questions."""
        labels = {item["label"] for item in QUICK_QUESTIONS}

        self.assertIn("制度解释", labels)
        self.assertIn("报表取数", labels)
        self.assertIn("指标比较", labels)

    def test_coverage_is_labeled_as_evidence_coverage_not_accuracy(self):
        """The UI must not convert support coverage into an accuracy claim."""
        self.assertEqual(
            coverage_presentation(0.96),
            {
                "label": "证据覆盖度",
                "value": "96%",
                "detail": "表示回答要点获得引用支持的比例",
            },
        )

    def test_invalid_coverage_is_visibly_unavailable(self):
        """Missing or out-of-range coverage must not be clamped into a plausible score."""
        self.assertEqual(coverage_presentation(None)["value"], "未提供")
        self.assertEqual(coverage_presentation(1.2)["value"], "未提供")

    def test_confidence_maps_backend_levels_without_inventing_percentage(self):
        """A categorical backend confidence must remain categorical."""
        self.assertEqual(confidence_presentation("high"), {"label": "高", "tone": "success"})
        self.assertEqual(confidence_presentation("unexpected"), {"label": "待核验", "tone": "neutral"})

    def test_missing_page_and_section_are_never_invented(self):
        """Absent coordinates must render an explicit provenance limitation."""
        self.assertEqual(
            citation_location({"sheet_name": "Sheet1", "cell": "B7"}),
            "工作表 Sheet1 · 单元格 B7",
        )
        self.assertEqual(citation_location({}), "原数据未提供页码定位")

    def test_match_score_is_not_formatted_as_probability(self):
        """Raw retrieval scores must not gain a percent sign."""
        self.assertEqual(format_match_score(0.96321), "0.9632")
        self.assertEqual(format_match_score("bad"), "未提供")

    def test_engine_codes_are_translated_without_hiding_unknown_states(self):
        """Raw engine codes must be readable while unknown values remain explicit."""
        self.assertEqual(intent_label("regulation_fact"), "监管制度问答")
        self.assertEqual(consistency_label("supported"), "证据一致")
        self.assertEqual(backend_label("extractive"), "本地证据抽取")
        self.assertEqual(backend_label("deterministic_extractive"), "本地证据抽取")
        self.assertEqual(backend_label("llm_error_fallback"), "外部模型失败后本地回退")
        self.assertEqual(intent_label("future_intent"), "待核验（future_intent）")

    def test_refusal_cannot_promote_retrieval_candidates_to_answer_evidence(self):
        payload = {
            "status": "out_of_scope",
            "citations": [{"source_title": "无关资料"}],
        }

        self.assertEqual(citations_for_display(payload), [])
        self.assertEqual(
            citations_for_display(
                {"status": "answered", "citations": [{"source_title": "实际采用证据"}]}
            ),
            [{"source_title": "实际采用证据"}],
        )


if __name__ == "__main__":
    unittest.main()
