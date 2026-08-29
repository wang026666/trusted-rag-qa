import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest


APP_PATH = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"


def _run_app() -> AppTest:
    return AppTest.from_file(str(APP_PATH), default_timeout=30).run()


def _markdown_text(app: AppTest) -> str:
    return "\n".join(str(item.value) for item in app.markdown)


def _button(app: AppTest, label: str):
    return next(item for item in app.button if item.label == label)


class BankingPlatformAppTests(unittest.TestCase):
    def test_default_route_is_the_regulatory_dashboard_with_five_page_navigation(self):
        app = _run_app()

        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["active_page"], "dashboard")
        button_labels = {item.label for item in app.button}
        self.assertTrue(
            {
                "监管驾驶舱",
                "可信RAG问答",
                "监管报表分析",
                "可信解释",
                "知识库管理",
            }.issubset(button_labels)
        )
        self.assertIn("银行可信RAG监管智能分析平台", _markdown_text(app))

    def test_each_primary_navigation_item_opens_its_page(self):
        expected = {
            "可信RAG问答": ("trusted_qa", "可信RAG智能问答"),
            "监管报表分析": ("report_analysis", "监管统计报表分析"),
            "可信解释": ("evidence", "可信解释"),
            "知识库管理": ("knowledge_base", "知识库管理"),
        }

        for label, (page_key, page_title) in expected.items():
            with self.subTest(label=label):
                app = _run_app()
                _button(app, label).click().run(timeout=30)
                self.assertFalse(app.exception)
                self.assertEqual(app.session_state["active_page"], page_key)
                self.assertIn(page_title, _markdown_text(app))

    def test_dashboard_quick_question_prefills_the_qa_workspace(self):
        question = "商业银行应当制定什么账簿划分政策？"
        app = _run_app()

        _button(app, question).click().run(timeout=30)

        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["active_page"], "trusted_qa")
        self.assertEqual(app.session_state["question_input"], question)

    def test_selected_answer_survives_a_streamlit_rerun(self):
        app = _run_app()
        app.session_state["active_page"] = "trusted_qa"
        app.session_state["qa_history"] = [
            {
                "id": "qa-0001",
                "sequence": 1,
                "question": "测试问题",
                "status": "answered",
                "payload": {
                    "status": "answered",
                    "answer": "这是一条可核验回答。",
                    "confidence": "high",
                    "intent": "regulation_fact",
                    "support_coverage": 1.0,
                    "consistency_status": "not_applicable",
                    "generation_backend": "deterministic_extractive",
                    "citations": [],
                },
            }
        ]
        app.session_state["selected_qa_id"] = "qa-0001"
        app.session_state["session_question_count"] = 1

        app.run(timeout=30)
        self.assertIn("这是一条可核验回答。", _markdown_text(app))
        app.run(timeout=30)

        self.assertFalse(app.exception)
        self.assertIn("这是一条可核验回答。", _markdown_text(app))

    def test_refusal_never_exposes_unrelated_retrieval_as_answer_evidence(self):
        app = _run_app()
        app.session_state["active_page"] = "trusted_qa"
        app.session_state["qa_history"] = [
            {
                "id": "qa-0001",
                "sequence": 1,
                "question": "资料库外问题",
                "status": "out_of_scope",
                "payload": {
                    "status": "out_of_scope",
                    "answer": "现有资料不足以回答。",
                    "confidence": "low",
                    "intent": "out_of_scope",
                    "support_coverage": 0.0,
                    "consistency_status": "not_applicable",
                    "generation_backend": "refusal",
                    "citations": [
                        {
                            "source_title": "不应展示的无关资料",
                            "evidence": "无关检索片段",
                            "score": 99.0,
                        }
                    ],
                },
            }
        ]
        app.session_state["selected_qa_id"] = "qa-0001"

        app.run(timeout=30)
        rendered = _markdown_text(app) + "\n" + "\n".join(str(item.value) for item in app.info)

        self.assertFalse(app.exception)
        self.assertNotIn("不应展示的无关资料", rendered)
        self.assertIn("本次回答未形成可引用证据", rendered)

    def test_evidence_page_has_an_explicit_empty_state_before_any_query(self):
        app = _run_app()
        _button(app, "可信解释").click().run(timeout=30)

        self.assertFalse(app.exception)
        self.assertIn("尚无可解释回答", _markdown_text(app))

    def test_report_upload_can_be_cleared_from_the_current_session(self):
        """Leaving an upload without a clear action must not retain it for the whole session."""
        app = _run_app()
        _button(app, "监管报表分析").click().run(timeout=30)
        app.session_state["uploaded_report_meta"] = {"filename": "private.xlsx"}

        self.assertIn("清除本次上传", {item.label for item in app.button})
        _button(app, "清除本次上传").click().run(timeout=30)

        self.assertFalse(app.exception)
        self.assertNotIn("uploaded_report_meta", app.session_state)


if __name__ == "__main__":
    unittest.main()
