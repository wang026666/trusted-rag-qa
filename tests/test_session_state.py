import pytest

from app.session_state import (
    initialize_session,
    navigate,
    record_answer,
    selected_entry,
    select_history,
    selected_result,
)


def test_initialize_session_sets_nonpersistent_defaults_once():
    """Reruns must preserve current session history instead of replacing it."""
    state = {}
    initialize_session(state)
    state["qa_history"].append({"id": "qa-0001"})
    initialize_session(state)

    assert state["active_page"] == "dashboard"
    assert state["qa_history"] == [{"id": "qa-0001"}]
    assert state["session_question_count"] == 0


def test_record_answer_appends_session_history_and_selects_it():
    """Submitting an answer must update the session count and selected result together."""
    state = {}
    initialize_session(state)

    entry_id = record_answer(state, "问题A", {"status": "answered", "answer": "答案A"})

    assert entry_id == "qa-0001"
    assert state["session_question_count"] == 1
    assert state["selected_qa_id"] == "qa-0001"
    assert selected_result(state)["answer"] == "答案A"


def test_record_answer_copies_payload_instead_of_linking_mutable_result():
    """A later mutation of the engine payload must not rewrite history."""
    state = {}
    initialize_session(state)
    payload = {"status": "answered", "answer": "原答案", "citations": [{"score": 0.9}]}

    record_answer(state, "问题", payload)
    payload["answer"] = "被篡改"
    payload["citations"][0]["score"] = 0

    assert selected_result(state)["answer"] == "原答案"
    assert selected_result(state)["citations"][0]["score"] == 0.9


def test_navigate_prefills_question_without_answering():
    """A dashboard shortcut must not increment Q&A count before submission."""
    state = {}
    initialize_session(state)

    navigate(state, "trusted_qa", prefill="报表问题")

    assert state["active_page"] == "trusted_qa"
    assert state["question_input"] == "报表问题"
    assert state["qa_history"] == []
    assert state["session_question_count"] == 0


def test_navigate_rejects_unknown_pages():
    """An invalid page key must not leave the app in an unroutable state."""
    state = {}
    initialize_session(state)

    with pytest.raises(ValueError, match="unknown page"):
        navigate(state, "admin_delete")

    assert state["active_page"] == "dashboard"


def test_select_history_switches_current_result_without_changing_count():
    """Reviewing an earlier answer must not count as a new question."""
    state = {}
    initialize_session(state)
    first = record_answer(state, "A", {"answer": "答案A", "status": "answered"})
    record_answer(state, "B", {"answer": "答案B", "status": "answered"})

    select_history(state, first)

    assert selected_result(state)["answer"] == "答案A"
    assert state["session_question_count"] == 2


def test_selected_answer_exposes_only_adopted_citations():
    """The UI must not invent a Top-K list absent from the engine payload."""
    state = {}
    initialize_session(state)
    payload = {
        "status": "answered",
        "answer": "结论",
        "support_coverage": 1.0,
        "citations": [{"source_title": "来源A", "score": 0.91, "evidence": "证据A"}],
    }

    record_answer(state, "问题", payload)

    assert selected_result(state)["citations"] == payload["citations"]
    assert "top_k" not in selected_result(state)


def test_selected_entry_keeps_question_beside_its_payload():
    """Evidence explanation must show the question paired with the selected answer."""
    state = {}
    initialize_session(state)
    record_answer(state, "原问题", {"answer": "原答案", "status": "answered"})

    assert selected_entry(state)["question"] == "原问题"
    assert selected_entry(state)["payload"]["answer"] == "原答案"
