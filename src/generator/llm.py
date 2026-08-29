from __future__ import annotations

import json
import urllib.error
import urllib.request

from src.generator.answerer import build_citation


def _chat_completions_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


class OpenAICompatibleLLM:
    """Minimal OpenAI-compatible chat client using the standard library."""

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 30.0):
        if not base_url or not api_key or not model:
            raise ValueError("LLM base_url, api_key and model are required.")
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    @staticmethod
    def _format_evidence(evidence: list[dict]) -> str:
        lines = []
        for index, item in enumerate(evidence[:5], start=1):
            citation = build_citation(item)
            location = ", ".join(
                str(value)
                for value in (
                    citation.get("source_title"),
                    citation.get("page"),
                    citation.get("section"),
                    citation.get("sheet_name"),
                    citation.get("row"),
                    citation.get("cell"),
                )
                if value
            )
            lines.append(f"[{index}] {location}\n{citation['evidence']}")
        return "\n\n".join(lines)

    def _messages(self, question: str, evidence: list[dict], question_type: str) -> list[dict]:
        return [
            {
                "role": "system",
                "content": (
                    "你是银行监管制度与统计报表可信 RAG 问答助手。"
                    "只能依据用户提供的证据回答；证据不足时回答“资料不足以回答”。"
                    "回答必须给出引用编号，例如 [1]、[2]，不得编造未出现在证据中的数字、日期、机构或文号。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"问题类型：{question_type}\n"
                    f"问题：{question}\n\n"
                    f"证据：\n{self._format_evidence(evidence)}\n\n"
                    "请给出简洁答案，并在关键结论后标注引用编号。"
                ),
            },
        ]

    def generate(self, question: str, evidence: list[dict], question_type: str) -> str:
        payload = {
            "model": self.model,
            "messages": self._messages(question, evidence, question_type),
            "temperature": 0,
        }
        request = urllib.request.Request(
            _chat_completions_url(self.base_url),
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"LLM request failed: {exc}") from exc
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return str(content).strip()


def create_llm_from_settings(settings):
    provider = (getattr(settings, "llm_provider", "none") or "none").lower()
    if provider in {"", "none", "disabled", "off"}:
        return None
    if provider == "openai_compatible":
        return OpenAICompatibleLLM(
            getattr(settings, "llm_base_url", ""),
            getattr(settings, "llm_api_key", ""),
            getattr(settings, "llm_model", ""),
            timeout=getattr(settings, "llm_timeout", 30.0),
        )
    raise ValueError(f"Unsupported LLM provider: {provider}")
