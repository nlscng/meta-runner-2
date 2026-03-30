"""Tests for src/review_index.py — review search and card mention extraction."""

import pytest

from src.review_index import (
    search_reviews,
    get_reviews_for_card,
    get_reviews_mentioning_card,
    _extract_card_mentions,
    _normalize,
)


class TestNormalize:
    def test_strips_html(self):
        assert "hello world" in _normalize("<b>hello</b> <i>world</i>")

    def test_lowercases(self):
        assert _normalize("HELLO") == "hello"

    def test_collapses_whitespace(self):
        assert _normalize("a  b   c") == "a b c"


class TestExtractCardMentions:
    def test_extracts_nrdb_links(self):
        text = 'Use [Corroder](/en/card/01003) against [Ice Wall](/en/card/01005).'
        codes = _extract_card_mentions(text)
        assert "01003" in codes
        assert "01005" in codes

    def test_no_matches_returns_empty(self):
        assert _extract_card_mentions("no cards here") == []


class TestSearchReviews:
    def test_finds_matching_review(self, sample_reviews):
        results = search_reviews(sample_reviews, "glacier")
        assert len(results) > 0
        assert any("Ice Wall" in r.get("title", "") for r in results)

    def test_no_match_returns_empty(self, sample_reviews):
        results = search_reviews(sample_reviews, "xyznonexistent")
        assert results == []

    def test_respects_limit(self, sample_reviews):
        results = search_reviews(sample_reviews, "credits", limit=1)
        assert len(results) <= 1

    def test_sorts_by_relevance(self, sample_reviews):
        results = search_reviews(sample_reviews, "rush cheap ice barrier")
        if len(results) >= 2:
            # First result should match more terms
            assert results[0]["title"] == "Ice Wall"


class TestGetReviewsForCard:
    def test_exact_title_match(self, sample_reviews):
        results = get_reviews_for_card(sample_reviews, "Ice Wall")
        assert len(results) == 1
        assert results[0]["title"] == "Ice Wall"

    def test_case_insensitive(self, sample_reviews):
        results = get_reviews_for_card(sample_reviews, "ice wall")
        assert len(results) == 1

    def test_no_match(self, sample_reviews):
        results = get_reviews_for_card(sample_reviews, "Nonexistent Card")
        assert results == []


class TestGetReviewsMentioningCard:
    def test_finds_reviews_with_card_code_link(self):
        reviews = [
            {
                "title": "Test",
                "ruling": "Pairs well with [Corroder](/en/card/01003)",
                "comments": [],
            }
        ]
        results = get_reviews_mentioning_card(reviews, "01003")
        assert len(results) == 1

    def test_finds_mentions_in_comments(self):
        reviews = [
            {
                "title": "Test",
                "ruling": "Good card",
                "comments": [
                    {"comment": "Works great with [Ice Wall](/en/card/01005)"}
                ],
            }
        ]
        results = get_reviews_mentioning_card(reviews, "01005")
        assert len(results) == 1
