"""Tests for src/review_index.py — review search, card mention extraction, and fetching."""

import json
import os
import tempfile

import pytest

from src.review_index import (
    fetch_reviews,
    search_reviews,
    get_reviews_for_card,
    get_reviews_mentioning_card,
    _extract_card_mentions,
    _normalize,
    _normalize_nrdb_review,
    _normalize_comment,
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


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

class TestNormalizeNrdbReview:
    """Verify the NRDB API → internal schema mapping."""

    def test_maps_nrdb_field_names(self):
        raw = {
            "id": 42,
            "card_code": "01001",
            "text_html": "<p>Great economy card.</p>",
            "username": "NetDecker",
            "vote_count": 12,
            "comments": [],
            "date_creation": "2024-01-01T00:00:00+00:00",
            "date_update": "2024-01-02T00:00:00+00:00",
        }
        result = _normalize_nrdb_review(raw)
        assert result["id"] == 42
        assert result["card_code"] == "01001"
        assert result["ruling"] == "<p>Great economy card.</p>"
        assert result["user"] == "NetDecker"
        assert result["votes"] == 12
        assert result["date_create"] == "2024-01-01T00:00:00+00:00"

    def test_resolves_title_from_card_titles_dict(self):
        raw = {"id": 1, "card_code": "01001", "text_html": "Good"}
        titles = {"01001": "Sure Gamble", "01002": "Diesel"}
        result = _normalize_nrdb_review(raw, card_titles=titles)
        assert result["title"] == "Sure Gamble"

    def test_prefers_explicit_title_over_lookup(self):
        raw = {"id": 1, "card_code": "01001", "title": "Explicit", "text_html": "x"}
        titles = {"01001": "Sure Gamble"}
        result = _normalize_nrdb_review(raw, card_titles=titles)
        assert result["title"] == "Explicit"

    def test_handles_missing_fields_gracefully(self):
        raw = {"id": 99}
        result = _normalize_nrdb_review(raw)
        assert result["id"] == 99
        assert result["title"] == ""
        assert result["card_code"] == ""
        assert result["user"] == ""
        assert result["ruling"] == ""
        assert result["votes"] == 0
        assert result["comments"] == []

    def test_none_card_code_becomes_empty_string(self):
        raw = {"id": 1, "card_code": None}
        result = _normalize_nrdb_review(raw)
        assert result["card_code"] == ""

    def test_normalises_comments(self):
        raw = {
            "id": 1,
            "comments": [
                {
                    "username": "Commenter",
                    "text_html": "I agree!",
                    "date_creation": "2024-06-01",
                }
            ],
        }
        result = _normalize_nrdb_review(raw)
        assert len(result["comments"]) == 1
        assert result["comments"][0]["user"] == "Commenter"
        assert result["comments"][0]["comment"] == "I agree!"


class TestNormalizeComment:
    def test_maps_nrdb_comment_fields(self):
        raw = {
            "username": "Runner42",
            "text_html": "<p>Nice synergy.</p>",
            "date_creation": "2024-03-15",
        }
        result = _normalize_comment(raw)
        assert result["user"] == "Runner42"
        assert result["comment"] == "<p>Nice synergy.</p>"
        assert result["date_create"] == "2024-03-15"

    def test_falls_back_to_alternate_field_names(self):
        raw = {"user": "OldFormat", "comment": "Legacy text", "date_create": "2023-01-01"}
        result = _normalize_comment(raw)
        assert result["user"] == "OldFormat"
        assert result["comment"] == "Legacy text"


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

class TestFetchReviews:
    def test_returns_cached_file_when_exists(self, tmp_path):
        cached = tmp_path / "reviews.json"
        data = [{"id": 1, "title": "Cached", "ruling": "x"}]
        cached.write_text(json.dumps(data))

        result = fetch_reviews(path=str(cached))
        assert len(result) == 1
        assert result[0]["title"] == "Cached"

    def test_force_refetches_even_with_cache(self, tmp_path, monkeypatch):
        cached = tmp_path / "reviews.json"
        cached.write_text(json.dumps([{"id": 1, "title": "Old"}]))

        # Mock httpx.get to return fresh data
        class MockResponse:
            status_code = 200
            def raise_for_status(self):
                pass
            def json(self):
                return {"data": [
                    {"id": 2, "card_code": "01001", "text_html": "New review",
                     "username": "Tester", "vote_count": 5, "comments": [],
                     "date_creation": "2024-06-01"}
                ]}

        import src.review_index as ri
        monkeypatch.setattr(ri.httpx, "get", lambda *a, **kw: MockResponse())
        monkeypatch.setattr(ri, "_fetch_card_titles", lambda **kw: {"01001": "Sure Gamble"})

        result = fetch_reviews(path=str(cached), force=True)
        assert len(result) == 1
        assert result[0]["title"] == "Sure Gamble"
        assert result[0]["id"] == 2

        # Verify it was written to disk
        on_disk = json.loads(cached.read_text())
        assert len(on_disk) == 1
        assert on_disk[0]["id"] == 2

    def test_raises_on_http_error(self, tmp_path, monkeypatch):
        import httpx as httpx_mod
        import src.review_index as ri

        class MockErrorResponse:
            status_code = 500
            def raise_for_status(self):
                raise httpx_mod.HTTPStatusError(
                    "Server Error",
                    request=httpx_mod.Request("GET", "http://test"),
                    response=self,
                )

        monkeypatch.setattr(ri.httpx, "get", lambda *a, **kw: MockErrorResponse())
        path = str(tmp_path / "reviews.json")
        with pytest.raises(httpx_mod.HTTPStatusError):
            fetch_reviews(path=path, force=True)

    def test_creates_data_directory_if_missing(self, tmp_path, monkeypatch):
        import src.review_index as ri

        class MockResponse:
            status_code = 200
            def raise_for_status(self):
                pass
            def json(self):
                return {"data": []}

        monkeypatch.setattr(ri.httpx, "get", lambda *a, **kw: MockResponse())
        monkeypatch.setattr(ri, "_fetch_card_titles", lambda **kw: {})

        nested_path = str(tmp_path / "sub" / "dir" / "reviews.json")
        result = fetch_reviews(path=nested_path, force=True)
        assert result == []
        assert os.path.exists(nested_path)
