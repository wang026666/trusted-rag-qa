import tempfile
import unittest
from pathlib import Path

from src.reranker.scorer import EvidenceReranker
from src.retriever.bm25 import BM25Index
from src.retriever.hybrid import HybridRetriever
from src.retriever.vector import SparseVectorIndex


class HybridRetrievalTests(unittest.TestCase):
    def test_hybrid_retriever_passes_question_profile_to_reranker(self):
        class RecordingReranker:
            def __init__(self):
                self.profiles = []

            def rerank(self, query, evidence, profile=""):
                self.profiles.append(profile)
                return evidence

        chunks = [{"chunk_id": "a", "text": "消费金融公司管理办法", "score": 1.0}]
        reranker = RecordingReranker()
        retriever = HybridRetriever(BM25Index(chunks), reranker=reranker)

        retriever.search("消费金融公司管理办法", top_k=1, profile="multi_fact")

        self.assertEqual(reranker.profiles, ["multi_fact"])

    def test_sparse_vector_index_returns_cosine_scores(self):
        chunks = [
            {"chunk_id": "a", "text": "资本充足率 风险加权资产", "source_title": "资本办法"},
            {"chunk_id": "b", "text": "保险公司 偿付能力 报告", "source_title": "保险规则"},
        ]
        index = SparseVectorIndex(chunks)

        results = index.search("资本充足率", top_k=1)

        self.assertEqual(results[0]["chunk_id"], "a")
        self.assertGreater(results[0]["vector_score"], 0)

    def test_sparse_vector_index_scores_all_matching_candidates_before_top_k(self):
        """A high-id document must not disappear merely because the query is broad."""
        chunks = [
            {
                "chunk_id": f"background-{index}",
                "text": f"银行 常规资料 {index}",
                "source_title": "背景资料",
            }
            for index in range(1201)
        ]
        chunks.append(
            {
                "chunk_id": "target",
                "text": "银行 资本充足率 制度",
                "source_title": "目标制度",
            }
        )
        index = SparseVectorIndex(chunks)

        results = index.search("银行 资本充足率 制度", top_k=1)

        self.assertEqual(results[0]["chunk_id"], "target")

    def test_hybrid_retriever_fuses_bm25_vector_and_rerank_scores(self):
        chunks = [
            {
                "chunk_id": "target",
                "text": "商业银行应当建立资本充足率管理制度。",
                "source_title": "商业银行资本管理办法",
                "file_label": "商业银行资本管理办法.pdf",
            },
            {
                "chunk_id": "noise",
                "text": "保险公司偿付能力监管规则。",
                "source_title": "保险公司规则",
                "file_label": "保险公司规则.pdf",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            index_dir = Path(tmp)
            BM25Index(chunks).save(index_dir / "bm25_index.json")
            SparseVectorIndex(chunks).save(index_dir / "vector_index.json")
            retriever = HybridRetriever.from_index_dir(index_dir)

            results = retriever.search("商业银行资本充足率", top_k=1)

        self.assertEqual(results[0]["chunk_id"], "target")
        self.assertIn("bm25_score", results[0])
        self.assertIn("vector_score", results[0])
        self.assertIn("rerank_score", results[0])

    def test_hybrid_retriever_shares_static_corpus_between_local_indexes(self):
        chunks = [
            {"chunk_id": "a", "text": "商业银行资本充足率", "source_title": "资本办法"},
            {"chunk_id": "b", "text": "银行业风险暴露", "source_title": "风险办法"},
        ]
        retriever = HybridRetriever(BM25Index(chunks), SparseVectorIndex([dict(item) for item in chunks]))

        self.assertIs(retriever.bm25.documents, retriever.vector.documents)
        self.assertIs(retriever.bm25.doc_freqs, retriever.vector.doc_freqs)
        self.assertIs(retriever.bm25.postings, retriever.vector.postings)
        self.assertFalse(hasattr(retriever.bm25, "doc_tokens"))
        self.assertFalse(hasattr(retriever.vector, "doc_tokens"))

    def test_reranker_prefers_current_row_over_context_only_match(self):
        evidence = [
            {
                "chunk_id": "context-only",
                "text": "第8行：B列=损失类贷款余额；C列=1；H列=2；上文表头/相邻行：B列=可疑类贷款余额；C列=4502.47；H列=43.68",
                "score": 100.0,
            },
            {
                "chunk_id": "current-row",
                "text": "第7行：B列=可疑类贷款余额；C列=4502.47；H列=43.68；上文表头/相邻行：A列=机构；C列=大型商业银行；H列=外资银行",
                "score": 90.0,
            },
        ]

        reranked = EvidenceReranker().rerank("可疑类贷款余额 大型商业银行 外资银行", evidence)

        self.assertEqual(reranked[0]["chunk_id"], "current-row")
        self.assertGreater(reranked[0]["rerank_score"], reranked[1]["rerank_score"])
