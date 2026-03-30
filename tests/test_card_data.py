"""Tests for src/card_data.py — database schema, queries, and meta stats.

Carried forward from meta-runner v1 with no changes to card data behavior.
"""

import json

import pytest

from src.card_data import init_db, compute_meta_stats
from tests.conftest import SAMPLE_CARDS, SAMPLE_DECKLISTS, _insert_cards, _insert_decklists


class TestInitDB:
    def test_creates_cards_table(self, db_conn):
        tables = {r[0] for r in db_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "cards" in tables

    def test_creates_decklists_table(self, db_conn):
        tables = {r[0] for r in db_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "decklists" in tables

    def test_creates_card_meta_stats_table(self, db_conn):
        tables = {r[0] for r in db_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "card_meta_stats" in tables

    def test_creates_indexes(self, db_conn):
        indexes = {r[0] for r in db_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()}
        assert "idx_cards_faction" in indexes
        assert "idx_cards_type" in indexes
        assert "idx_cards_side" in indexes
        assert "idx_decklists_tournament" in indexes

    def test_idempotent_when_called_twice(self, db_conn):
        init_db(db_conn)
        count = db_conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
        assert count >= 3


class TestCardStorage:
    def test_insert_cards(self, populated_db):
        count = populated_db.execute("SELECT count(*) FROM cards").fetchone()[0]
        assert count == len(SAMPLE_CARDS)

    def test_duplicate_insert_replaces(self, populated_db):
        _insert_cards(populated_db, SAMPLE_CARDS[:2])
        count = populated_db.execute("SELECT count(*) FROM cards").fetchone()[0]
        assert count == len(SAMPLE_CARDS)

    def test_query_by_faction(self, populated_db):
        rows = populated_db.execute(
            "SELECT * FROM cards WHERE faction_code = ?", ("anarch",)
        ).fetchall()
        titles = {r["title"] for r in rows}
        assert titles == {"Sure Gamble", "Corroder"}

    def test_query_by_type(self, populated_db):
        rows = populated_db.execute(
            "SELECT * FROM cards WHERE type_code = ?", ("event",)
        ).fetchall()
        titles = {r["title"] for r in rows}
        assert titles == {"Sure Gamble", "Diesel"}

    def test_query_by_side(self, populated_db):
        rows = populated_db.execute(
            "SELECT * FROM cards WHERE side_code = 'runner'"
        ).fetchall()
        assert all(r["side_code"] == "runner" for r in rows)
        assert len(rows) == 5

    def test_card_fields_stored_correctly(self, populated_db):
        card = populated_db.execute(
            "SELECT * FROM cards WHERE code = '01003'"
        ).fetchone()
        assert card["title"] == "Corroder"
        assert card["type_code"] == "program"
        assert card["cost"] == 2
        assert card["strength"] == 2


class TestDecklistStorage:
    def test_insert_decklists(self, populated_db):
        count = populated_db.execute("SELECT count(*) FROM decklists").fetchone()[0]
        assert count == len(SAMPLE_DECKLISTS)

    def test_tournament_badge_filter(self, populated_db):
        rows = populated_db.execute(
            "SELECT * FROM decklists WHERE tournament_badge = 1"
        ).fetchall()
        assert len(rows) == 2

    def test_cards_json_round_trips(self, populated_db):
        row = populated_db.execute(
            "SELECT cards_json FROM decklists WHERE id = 1"
        ).fetchone()
        cards = json.loads(row["cards_json"])
        assert cards == {"01001": 3, "01003": 2, "01007": 1}


class TestComputeMetaStats:
    def test_returns_number_of_unique_cards(self, populated_db):
        result = compute_meta_stats(populated_db)
        assert result == 7

    def test_total_deck_count(self, populated_db):
        compute_meta_stats(populated_db)
        row = populated_db.execute(
            "SELECT total_deck_count FROM card_meta_stats WHERE card_code = '01001'"
        ).fetchone()
        assert row["total_deck_count"] == 2

    def test_tournament_deck_count(self, populated_db):
        compute_meta_stats(populated_db)
        row = populated_db.execute(
            "SELECT tournament_deck_count FROM card_meta_stats WHERE card_code = '01001'"
        ).fetchone()
        assert row["tournament_deck_count"] == 1

    def test_avg_copies(self, populated_db):
        compute_meta_stats(populated_db)
        row = populated_db.execute(
            "SELECT avg_copies FROM card_meta_stats WHERE card_code = '01003'"
        ).fetchone()
        assert row["avg_copies"] == 1.5

    def test_idempotent_recompute(self, populated_db):
        compute_meta_stats(populated_db)
        compute_meta_stats(populated_db)
        row = populated_db.execute(
            "SELECT total_deck_count FROM card_meta_stats WHERE card_code = '01001'"
        ).fetchone()
        assert row["total_deck_count"] == 2
