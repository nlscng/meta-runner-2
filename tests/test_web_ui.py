"""Tests for src/web_ui.py — WebAgent response logic and card display."""

import sqlite3
from unittest.mock import patch

import pytest

from tests.conftest import (
    SAMPLE_CARDS, SAMPLE_REVIEWS, SAMPLE_CONCEPTS,
    _insert_cards, _insert_decklists, SAMPLE_DECKLISTS,
)
from src.card_data import init_db, compute_meta_stats


def _make_web_agent(populated_db, concepts=None, memory=None, reviews=None):
    """Build a WebAgent with test data injected."""
    from src.web_ui import WebAgent
    from src.image_cache import ImageCache

    with patch.object(WebAgent, "__init__", lambda self: None):
        agent = WebAgent.__new__(WebAgent)

    agent.db = populated_db
    agent.catalog = concepts or SAMPLE_CONCEPTS.copy()
    agent.memory = memory or {"concepts": {}, "sessions": [], "version": 2}
    agent.reviews = reviews if reviews is not None else SAMPLE_REVIEWS.copy()
    # Use a stub cache that always returns the remote URL (no network in tests)
    agent.image_cache = _StubImageCache()
    agent.current_question = None
    agent.current_concept = None
    agent.score = {"correct": 0, "wrong": 0}
    agent.session_concepts = []
    agent.session_concept_idx = 0
    agent.session_tracker = []
    agent._awaiting_grade = False
    return agent


class _StubImageCache:
    """Minimal image cache stub that returns remote URLs without network access."""

    def get_url(self, code):
        return f"https://card-images.netrunnerdb.com/v2/large/{code}.jpg"

    def get_image_path(self, code):
        return None


@pytest.fixture()
def web_agent(populated_db):
    compute_meta_stats(populated_db)
    return _make_web_agent(populated_db)


# ---------------------------------------------------------------------------
# Card display
# ---------------------------------------------------------------------------

class TestCardDisplay:
    def test_card_html_renders_image(self, web_agent):
        html = web_agent._card_html("01005")
        assert "Ice Wall" in html
        assert "img" in html
        assert "01005" in html

    def test_card_html_unknown_code_returns_empty(self, web_agent):
        html = web_agent._card_html("99999")
        assert html == ""

    def test_deck_html_renders_table(self, web_agent):
        html = web_agent._deck_html({"01001": 3, "01003": 2})
        assert "Sure Gamble" in html
        assert "Corroder" in html
        assert "3x" in html
        assert "2x" in html

    def test_deck_html_empty_dict(self, web_agent):
        assert web_agent._deck_html({}) == ""


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------

class TestWebSession:
    def test_start_session_returns_plan(self, web_agent):
        msg, card_html = web_agent.start_session()
        assert "Session Plan" in msg
        assert any(c["name"] in msg for c in SAMPLE_CONCEPTS.values())

    def test_start_session_selects_concepts(self, web_agent):
        web_agent.start_session()
        assert len(web_agent.session_concepts) > 0


# ---------------------------------------------------------------------------
# Message handling
# ---------------------------------------------------------------------------

class TestWebRespond:
    def test_help_command(self, web_agent):
        history, card_html = web_agent.respond("help", [])
        assert len(history) == 2
        assert "quiz" in history[-1]["content"].lower()

    def test_quiz_command_generates_question(self, web_agent):
        web_agent.start_session()
        history, card_html = web_agent.respond("quiz", [])
        assert "🃏" in history[-1]["content"]
        assert web_agent.current_question is not None

    def test_answer_then_grade_flow(self, web_agent):
        web_agent.start_session()
        history, _ = web_agent.respond("quiz", [])
        # Answer free-text
        history, _ = web_agent.respond("glacier builds tall servers", history)
        assert web_agent._awaiting_grade is True
        assert "self-evaluate" in history[-1]["content"].lower() or "Self-evaluate" in history[-1]["content"]
        # Grade
        history, _ = web_agent.respond("4", history)
        assert web_agent._awaiting_grade is False
        assert web_agent.current_question is None
        assert web_agent.score["correct"] == 1

    def test_score_command(self, web_agent):
        web_agent.score = {"correct": 2, "wrong": 1}
        history, _ = web_agent.respond("score", [])
        assert "2/3" in history[-1]["content"]

    def test_card_lookup(self, web_agent):
        history, card_html = web_agent.respond("card ice wall", [])
        assert "Ice Wall" in history[-1]["content"]
        assert "img" in card_html

    def test_card_lookup_not_found(self, web_agent):
        history, card_html = web_agent.respond("card xyznonexistent", [])
        assert "No card found" in history[-1]["content"]

    def test_concepts_command(self, web_agent):
        history, _ = web_agent.respond("concepts", [])
        assert "Glacier" in history[-1]["content"]

    def test_quit_saves_session(self, web_agent):
        with patch("src.web_ui.save_concept_memory"):
            history, _ = web_agent.respond("quit", [])
        assert "Thanks" in history[-1]["content"]
        assert len(web_agent.memory["sessions"]) == 1

    def test_empty_input_ignored(self, web_agent):
        # Empty input in on_submit is handled by the UI layer (returns early)
        # but respond itself will treat it as a quiz trigger
        history, _ = web_agent.respond("   ", [])
        assert len(history) == 2  # still produces a response


# ---------------------------------------------------------------------------
# Gradio app construction
# ---------------------------------------------------------------------------

class TestBuildUI:
    def test_build_ui_returns_blocks(self):
        from src.web_ui import build_ui
        with patch("src.web_ui.WebAgent"):
            app = build_ui()
        assert app is not None
