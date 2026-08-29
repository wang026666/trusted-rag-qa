import unittest

from src.generator.answerer import answer_question
from src.generator.question_type import classify_question
from src.retriever.bm25 import BM25Index


class RetrievalAnsweringTests(unittest.TestCase):
    def test_bm25_retrieves_evidence_with_metadata(self):
        chunks = [
            {
                "chunk_id": "doc1::p1",
                "doc_id": "doc1",
                "text": "商业银行应当制定清晰的银行账簿和交易账簿划分政策。",
                "source_title": "账簿划分和名词解释",
                "file_path": "a.docx",
                "page": "",
                "section": "三、账簿划分及转换的管理",
            },
            {
                "chunk_id": "doc2::p1",
                "doc_id": "doc2",
                "text": "保险公司偿付能力报告应当按照监管规则编报。",
                "source_title": "偿付能力报告",
                "file_path": "b.pdf",
                "page": "2",
                "section": "",
            },
        ]
        index = BM25Index(chunks)

        results = index.search("银行账簿 交易账簿 划分政策", top_k=1)

        self.assertEqual(results[0]["chunk_id"], "doc1::p1")
        self.assertGreater(results[0]["score"], 0)
        self.assertEqual(results[0]["source_title"], "账簿划分和名词解释")

    def test_bm25_indexes_source_title_and_file_label(self):
        chunks = [
            {
                "chunk_id": "doc1::p1",
                "doc_id": "doc1",
                "text": "本段只包含普通正文。",
                "source_title": "知识产权金融生态综合试点工作方案",
                "file_label": "知识产权金融生态综合试点工作方案.pdf",
                "file_path": "a.pdf",
            },
            {
                "chunk_id": "doc2::p1",
                "doc_id": "doc2",
                "text": "本段包含金融生态但不是目标文件。",
                "source_title": "其他文件",
                "file_label": "其他文件.pdf",
                "file_path": "b.pdf",
            },
        ]
        index = BM25Index(chunks)

        results = index.search("根据《知识产权金融生态综合试点工作方案》下列哪项正确", top_k=1)

        self.assertEqual(results[0]["chunk_id"], "doc1::p1")

    def test_bm25_exact_source_title_beats_similar_month_report(self):
        chunks = [
            {
                "chunk_id": "noise::row",
                "text": " ".join(["稀有干扰词 公司本级 合计 健康险"] * 100),
                "source_title": "无关高频报表",
                "file_label": "无关高频报表.xls",
            },
            {
                "chunk_id": "sep::row",
                "text": "公司本级 合计 健康险",
                "source_title": "2024年9月全国各地区原保险保费收入情况表",
                "file_label": "2024年9月全国各地区原保险保费收入情况表.xlsx",
            },
            {
                "chunk_id": "dec::row",
                "text": " ".join(["公司本级 合计 健康险"] * 40),
                "source_title": "2024年12月全国各地区原保险保费收入情况表",
                "file_label": "2024年12月全国各地区原保险保费收入情况表.xls",
            },
        ]
        index = BM25Index(chunks)

        results = index.search(
            "2024年9月全国各地区原保险保费收入情况表 公司本级 健康险 稀有干扰词",
            top_k=1,
            max_candidates=1,
        )

        self.assertEqual(results[0]["chunk_id"], "sep::row")

    def test_bm25_finds_forced_metadata_candidates(self):
        chunks = [
            {
                "chunk_id": "target",
                "text": "普通正文",
                "source_title": "2024年9月全国各地区原保险保费收入情况表",
                "file_label": "2024年9月全国各地区原保险保费收入情况表.xlsx",
            }
        ]
        index = BM25Index(chunks)

        candidates = index._forced_metadata_candidates("2024年9月全国各地区原保险保费收入情况表 公司本级")

        self.assertEqual(candidates, {0})

    def test_answer_question_returns_cited_answer_when_evidence_exists(self):
        result = answer_question(
            "商业银行应当制定什么账簿政策？",
            [
                {
                    "chunk_id": "doc1::p1",
                    "text": "商业银行应当制定清晰的银行账簿和交易账簿划分政策。",
                    "source_title": "账簿划分和名词解释",
                    "file_path": "a.docx",
                    "page": "",
                    "section": "三、账簿划分及转换的管理",
                    "score": 3.2,
                }
            ],
            min_score=0.1,
        )

        self.assertTrue(result["answer"].startswith("根据检索证据"))
        self.assertEqual(result["citations"][0]["source_title"], "账簿划分和名词解释")
        self.assertEqual(result["confidence"], "medium")

    def test_single_fact_extractive_answer_uses_only_top_evidence(self):
        result = answer_question(
            "商业银行应当制定什么账簿划分政策？",
            [
                {
                    "chunk_id": "relevant",
                    "text": "商业银行应当制定清晰的银行账簿和交易账簿划分政策和程序。",
                    "source_title": "账簿划分和名词解释",
                    "score": 30.0,
                },
                {
                    "chunk_id": "distractor",
                    "text": "商业银行应当评估信用风险参数压力测试的审慎性。",
                    "source_title": "商业银行风险评估标准",
                    "score": 29.0,
                },
            ],
            min_score=0.1,
        )

        self.assertIn("账簿划分政策", result["answer"])
        self.assertNotIn("风险参数压力测试", result["answer"])
        self.assertEqual([item["chunk_id"] for item in result["citations"]], ["relevant"])

    def test_multi_fact_extractive_answer_keeps_multiple_evidence_items(self):
        result = answer_question(
            "请分别说明资本充足率和杠杆率要求。",
            [
                {"chunk_id": "capital", "text": "资本充足率不得低于8%。", "score": 30.0},
                {"chunk_id": "leverage", "text": "杠杆率不得低于4%。", "score": 29.0},
            ],
            min_score=0.1,
            min_coverage=0.0,
        )

        self.assertIn("8%", result["answer"])
        self.assertIn("4%", result["answer"])
        self.assertEqual(len(result["citations"]), 2)

    def test_answer_question_refuses_when_evidence_is_missing(self):
        result = answer_question("资料库外的问题", [], min_score=0.1)

        self.assertEqual(result["answer"], "不足以根据资料回答。")
        self.assertEqual(result["citations"], [])
        self.assertEqual(result["confidence"], "low")

    def test_answer_question_refuses_when_key_question_terms_are_not_supported(self):
        result = answer_question(
            "火星银行的客户猫粮贷款政策是什么？",
            [
                {
                    "chunk_id": "doc1::p1",
                    "text": "商业银行可以披露贷款客户数和风险政策。",
                    "source_title": "商业银行资本管理办法",
                    "file_path": "a.docx",
                    "score": 30,
                }
            ],
            min_score=0.1,
        )

        self.assertEqual(result["answer"], "不足以根据资料回答。")
        self.assertEqual(result["confidence"], "low")

    def test_extractive_answer_centers_long_evidence_on_question_terms(self):
        result = answer_question(
            "现场检查对食宿和交通工具分别有什么要求？",
            [
                {
                    "chunk_id": "inspection",
                    "text": "公告背景。" * 100
                    + "不准无偿由被检查单位安排食宿，"
                    + "不准无偿使用被检查单位的交通工具。",
                    "score": 30.0,
                }
            ],
            min_score=0.1,
            min_coverage=0.0,
        )

        self.assertIn("不准无偿由被检查单位安排食宿", result["answer"])
        self.assertIn("不准无偿使用被检查单位的交通工具", result["answer"])

    def test_answer_evidence_selection_skips_title_only_stub(self):
        result = answer_question(
            "反洗钱工作季度报告应在什么时限内报送？",
            [
                {"chunk_id": "title", "text": "合并的监管报告事项", "score": 61.0},
                {"chunk_id": "header", "text": "监管报告事项表", "score": 60.5},
                {
                    "chunk_id": "deadline",
                    "text": "反洗钱工作季度报告应当于每季度结束后10个工作日内报送。",
                    "score": 60.0,
                },
            ],
            min_score=0.1,
            min_coverage=0.0,
        )

        self.assertIn("10个工作日", result["answer"])
        self.assertEqual([item["chunk_id"] for item in result["citations"]], ["deadline"])

    def test_quoted_source_title_outweighs_numeric_distractor(self):
        result = answer_question(
            "《现场检查公告》规定最少需要几名检查人员？",
            [
                {
                    "chunk_id": "notice",
                    "text": "现场检查公告：现场检查不得少于两人。",
                    "score": 80.0,
                },
                {
                    "chunk_id": "annual-report",
                    "text": "全面强化现场检查，共派出2586个检查组。",
                    "score": 30.0,
                },
            ],
            min_score=0.1,
            min_coverage=0.0,
        )

        self.assertIn("不得少于两人", result["answer"])
        self.assertEqual([item["chunk_id"] for item in result["citations"]], ["notice"])

    def test_answer_question_refuses_explicit_unpublished_future_value(self):
        result = answer_question(
            "未公布的2030年商业银行核心一级资本充足率新监管下限是多少？",
            [
                {
                    "chunk_id": "historical",
                    "text": "2023年商业银行核心一级资本充足率为10.5%。",
                    "score": 70.0,
                }
            ],
            min_score=0.1,
            min_coverage=0.0,
        )

        self.assertEqual(result["answer"], "不足以根据资料回答。")
        self.assertEqual(result["generation_backend"], "refusal")

    def test_classify_question_distinguishes_core_competition_types(self):
        self.assertEqual(classify_question("这个指标从一季度到四季度变化多少？"), "指标计算类问题")
        self.assertEqual(classify_question("这张报表的填报规则是什么？"), "填报规则类问题")
        self.assertEqual(classify_question("请定位该条款的来源文件和页码"), "来源定位类问题")
        self.assertEqual(classify_question("资本充足率的监管口径是什么？"), "统计报表口径类问题")
        self.assertEqual(classify_question("商业银行资本管理办法如何规定风险管理？"), "制度解释类问题")
