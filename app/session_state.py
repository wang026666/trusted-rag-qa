"""Pure state transitions for Streamlit's session-scoped UI state."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, MutableMapping


PAGE_KEYS = frozenset({"dashboard", "trusted_qa", "report_analysis", "evidence", "knowledge_base"})


def initialize_session(state: MutableMapping[str, Any]) -> None:
    state.setdefault("active_page", "dashboard")
    state.setdefault("question_input", "")
    state.setdefault("qa_history", [])
    state.setdefault("selected_qa_id", None)
    state.setdefault("session_question_count", 0)


def navigate(state: MutableMapping[str, Any], page: str, prefill: str | None = None) -> None:
    if page not in PAGE_KEYS:
        raise ValueError(f"unknown page: {page}")
    state["active_page"] = page
    if prefill is not None:
        state["question_input"] = prefill


def record_answer(state: MutableMapping[str, Any], question: str, payload: dict[str, Any]) -> str:
    sequence = int(state.get("session_question_count", 0)) + 1
    entry_id = f"qa-{sequence:04d}"
    entry = {
        "id": entry_id,
        "sequence": sequence,
        "question": str(question),
        "status": str(payload.get("status") or "unknown"),
        "payload": deepcopy(payload),
    }
    history = state.setdefault("qa_history", [])
    history.append(entry)
    state["session_question_count"] = sequence
    state["selected_qa_id"] = entry_id
    return entry_id


def select_history(state: MutableMapping[str, Any], entry_id: str) -> None:
    history = state.get("qa_history") or []
    if not any(entry.get("id") == entry_id for entry in history):
        raise ValueError(f"unknown history entry: {entry_id}")
    state["selected_qa_id"] = entry_id


def selected_entry(state: MutableMapping[str, Any]) -> dict[str, Any] | None:
    selected_id = state.get("selected_qa_id")
    if not selected_id:
        return None
    for entry in reversed(state.get("qa_history") or []):
        if entry.get("id") == selected_id:
            return entry if isinstance(entry, dict) else None
    return None


def selected_result(state: MutableMapping[str, Any]) -> dict[str, Any] | None:
    entry = selected_entry(state)
    if not entry:
        return None
    payload = entry.get("payload")
    return payload if isinstance(payload, dict) else None
