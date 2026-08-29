import unittest

from src.generator.answerer import answer_question, answer_regulation_question
from src.generator.consistency import extract_critical_claims, validate_answer_consistency
from src.generator.query_parser import parse_question


class FakeLLM:
    def __init__(self, answer: str):
        self.answer = answer

    def generate(self, question, evidence, question_type):
        return self.answer


class FailingLLM:
    def generate(self, question, evidence, question_type):
        raise RuntimeError("provider unavailable")


class EvidenceConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.evidence = [
            {
                "chunk_id": "capital::article5",
                "text": (
                    "第五条 商业银行核心一级资本充足率不得低于5％，"
                    "本办法自2024年1月1日起施行。"
                ),
                "source_title": "商业银行资本管理办法",
                "score": 30.0,
            }
        ]

    def test_extracts_high_risk_numbers_dates_and_article_references(self):
        claims = extract_critical_claims(
            "根据第五条，指标不得低于5%，自2024年1月1日起施行。"
        )

        self.assertIn({"type": "article", "value": "第五条"}, claims)
        self.assertIn({"type": "percentage", "value": "5%"}, claims)
        self.assertIn({"type": "date", "value": "2024年1月1日"}, claims)

    def test_accepts_supported_claims_with_equivalent_punctuation_and_numerals(self):
        result = validate_answer_consistency(
            "根据第5条，核心一级资本充足率不得低于5%，自2024年1月1日起施行。[1]",
            self.evidence,
        )

        self.assertEqual(result["status"], "supported")
        self.assertEqual(result["score"], 1.0)
        self.assertEqual(result["unsupported_claims"], [])

    def test_rejects_number_not_present_in_evidence(self):
        result = validate_answer_consistency(
            "核心一级资本充足率不得低于8%。[1]",
            self.evidence,
        )

        self.assertEqual(result["status"], "unsupported")
        self.assertEqual(result["score"], 0.0)
        self.assertEqual(
            result["unsupported_claims"],
            [{"type": "percentage", "value": "8%"}],
        )

    def test_document_number_matching_ignores_surrounding_sentence_words(self):
        result = validate_answer_consistency(
            "依据金规〔2024〕3号执行。",
            [{"text": "金规〔2024〕3号印发后执行。"}],
        )

        self.assertEqual(result["status"], "supported")
        self.assertEqual(result["unsupported_claims"], [])

    def test_answerer_falls_back_when_llm_introduces_unsupported_fact(self):
        result = answer_question(
            "商业银行核心一级资本充足率最低要求是多少？",
            self.evidence,
            min_score=0.1,
            llm=FakeLLM("核心一级资本充足率不得低于8%。[1]"),
        )

        self.assertTrue(result["answer"].startswith("根据检索证据"))
        self.assertEqual(result["generation_backend"], "llm_consistency_fallback")
        self.assertEqual(result["consistency_status"], "unsupported")
        self.assertEqual(
            result["unsupported_claims"],
            [{"type": "percentage", "value": "8%"}],
        )

    def test_answerer_keeps_llm_answer_when_critical_facts_are_supported(self):
        result = answer_question(
            "商业银行核心一级资本充足率最低要求是多少？",
            self.evidence,
            min_score=0.1,
            llm=FakeLLM("核心一级资本充足率不得低于5%。[1]"),
        )

        self.assertEqual(result["answer"], "核心一级资本充足率不得低于5%。[1]")
        self.assertEqual(result["generation_backend"], "llm")
        self.assertEqual(result["consistency_status"], "supported")
        self.assertEqual(result["consistency_score"], 1.0)

    def test_generic_answerer_reports_a_safe_llm_failure_fallback(self):
        """Removing the failure marker must not make a failed LLM look intentionally local."""
        result = answer_question(
            "商业银行核心一级资本充足率最低要求是多少？",
            self.evidence,
            min_score=0.1,
            llm=FailingLLM(),
        )

        self.assertEqual(result["generation_backend"], "llm_error_fallback")
        self.assertEqual(result["generation_error_type"], "RuntimeError")
        self.assertNotIn("llm_error", result)

    def test_regulation_answer_reports_a_safe_llm_failure_fallback(self):
        """The final unified-engine path must expose external-model failure before degrading."""
        result = answer_regulation_question(
            parse_question("商业银行核心一级资本充足率最低要求是多少？"),
            self.evidence,
            min_score=0.1,
            llm=FailingLLM(),
        )

        self.assertEqual(result.generation_backend, "llm_error_fallback")
        self.assertEqual(result.generation_error_type, "RuntimeError")
        self.assertTrue(result.answer.startswith("根据检索证据："))
        self.assertIn("核心一级资本充足率不得低于5％", result.answer)


if __name__ == "__main__":
    unittest.main()
