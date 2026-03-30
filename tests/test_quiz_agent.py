"""Tests for src/quiz_agent.py — concept-based quiz agent with agent behaviors."""

import sqlite3
from unittest.mock import patch

import pytest

from tests.conftest import (
    SAMPLE_CARDS, SAMPLE_REVIEWS, SAMPLE_CONCEPTS,
    _insert_cards, _insert_decklists, SAMPLE_DECKLISTS,
)
from src.card_data import init_db, compute_meta_stats


def _make_agent(populated_db, concepts=None, memory=None, reviews=None):
    """Build a QuizAgent with test data injected."""
    from src.quiz_agent import QuizAgent

    with patch.object(QuizAgent, "__init__", lambda self, **kw: None):
        agent = QuizAgent.__new__(QuizAgent)

    agent.db = populated_db
    agent.catalog = concepts or SAMPLE_CONCEPTS.copy()
    agent.memory = memory or {"concepts": {}, "sessions": [], "version": 2}
    agent.reviews = reviews if reviews is not None else SAMPLE_REVIEWS.copy()
    agent.current_question = None
    agent.current_concept = None
    agent.score = {"correct": 0, "wrong": 0}
    agent.session_concepts = []
    agent.session_concept_idx = 0
    agent.session_tracker = []
    agent.session_started = False
    return agent


@pytest.fixture()
def agent(populated_db):
    compute_meta_stats(populated_db)
    return _make_agent(populated_db)


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------

class TestStartSession:
    def test_returns_session_plan(self, agent):
        msg = agent.start_session()
        assert "Session Plan" in msg or "Meta Runner" in msg

    def test_lists_concepts(self, agent):
        msg = agent.start_session()
        # Should mention at least one concept
        assert any(c["name"] in msg for c in SAMPLE_CONCEPTS.values())

    def test_marks_untested_as_new(self, agent):
        msg = agent.start_session()
        assert "new" in msg.lower()

    def test_sets_session_started(self, agent):
        agent.start_session()
        assert agent.session_started is True

    def test_selects_concepts_for_session(self, agent):
        agent.start_session()
        assert len(agent.session_concepts) > 0


# ---------------------------------------------------------------------------
# Question generation
# ---------------------------------------------------------------------------

class TestQuestionGeneration:
    def test_generates_concept_question(self, agent):
        agent.start_session()
        q = agent._generate_question()
        assert q["type"] == "concept"
        assert "concept_id" in q
        assert "question" in q

    def test_question_from_catalog(self, agent):
        agent.start_session()
        q = agent._generate_question()
        assert q["concept_id"] in agent.catalog

    def test_question_has_concept_name(self, agent):
        agent.start_session()
        q = agent._generate_question()
        assert q["concept_name"] == agent.catalog[q["concept_id"]]["name"]


# ---------------------------------------------------------------------------
# Message handling
# ---------------------------------------------------------------------------

class TestHandleMessage:
    def test_help_command(self, agent):
        resp = agent.handle_message("help")
        assert "Commands:" in resp

    def test_score_no_questions(self, agent):
        resp = agent.handle_message("score")
        assert "No questions answered" in resp

    def test_quiz_starts_question(self, agent):
        agent.start_session()
        resp = agent.handle_message("quiz")
        assert "🃏" in resp
        assert agent.current_question is not None

    def test_plan_command(self, agent):
        resp = agent.handle_message("plan")
        assert "Meta Runner" in resp or "Session Plan" in resp

    def test_concepts_command(self, agent):
        resp = agent.handle_message("concepts")
        assert "Catalog" in resp

    def test_self_eval_grade_processes(self, agent):
        agent.start_session()
        agent.handle_message("quiz")
        assert agent.current_question is not None
        resp = agent.handle_message("4")
        assert agent.current_question is None
        assert "Score:" in resp

    def test_answer_text_prompts_self_eval(self, agent):
        agent.start_session()
        agent.handle_message("quiz")
        resp = agent.handle_message("glacier builds tall servers with expensive ice")
        assert "self-evaluate" in resp.lower() or "Self-evaluate" in resp

    def test_quit_returns_farewell(self, agent):
        resp = agent.handle_message("quit")
        assert "Thanks" in resp


# ---------------------------------------------------------------------------
# SM-2 integration
# ---------------------------------------------------------------------------

class TestSM2Integration:
    def test_grade_updates_memory(self, agent):
        agent.start_session()
        agent.handle_message("quiz")
        concept_id = agent.current_question["concept_id"]
        agent.handle_message("4")  # grade: good
        assert concept_id in agent.memory["concepts"]
        assert agent.memory["concepts"][concept_id]["times_tested"] == 1

    def test_wrong_grade_shows_description(self, agent):
        agent.start_session()
        agent.handle_message("quiz")
        resp = agent.handle_message("0")  # grade: wrong
        assert "key idea" in resp.lower() or "🔄" in resp


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

class TestScoring:
    def test_correct_increments_on_good_grade(self, agent):
        agent.start_session()
        agent.handle_message("quiz")
        agent.handle_message("4")
        assert agent.score["correct"] == 1

    def test_wrong_increments_on_bad_grade(self, agent):
        agent.start_session()
        agent.handle_message("quiz")
        agent.handle_message("0")
        assert agent.score["wrong"] == 1

    def test_score_display_after_answers(self, agent):
        agent.score = {"correct": 3, "wrong": 1}
        resp = agent.handle_message("score")
        assert "3/4" in resp
        assert "75%" in resp


# ---------------------------------------------------------------------------
# Initiative — course correction
# ---------------------------------------------------------------------------

class TestCourseCorrection:
    def test_no_correction_under_3_answers(self, agent):
        agent.session_tracker = [{"concept_id": "glacier", "grade": 0}]
        assert agent._check_course_correction() is None

    def test_correction_on_3_wrong(self, agent):
        agent.session_tracker = [
            {"concept_id": "glacier", "grade": 0},
            {"concept_id": "rush", "grade": 2},
            {"concept_id": "tempo", "grade": 1},
        ]
        result = agent._check_course_correction()
        assert result is not None
        assert "shift" in result.lower() or "tough" in result.lower()

    def test_correction_on_3_easy(self, agent):
        agent.session_tracker = [
            {"concept_id": "glacier", "grade": 5},
            {"concept_id": "rush", "grade": 5},
            {"concept_id": "tempo", "grade": 5},
        ]
        result = agent._check_course_correction()
        assert result is not None
        assert "harder" in result.lower()

    def test_no_correction_on_mixed(self, agent):
        agent.session_tracker = [
            {"concept_id": "glacier", "grade": 0},
            {"concept_id": "rush", "grade": 4},
            {"concept_id": "tempo", "grade": 5},
        ]
        assert agent._check_course_correction() is None
