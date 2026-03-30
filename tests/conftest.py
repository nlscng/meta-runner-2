"""Shared fixtures for meta-runner-2 tests.

Provides an in-memory SQLite database pre-populated with deterministic card
and decklist data, plus sample concept catalog and memory structures.
Tests never need network access.
"""

import json
import sqlite3

import pytest

# ---------------------------------------------------------------------------
# Canonical test data — cards and decklists (carried from v1)
# ---------------------------------------------------------------------------

SAMPLE_CARDS = [
    {
        "code": "01001",
        "title": "Sure Gamble",
        "stripped_text": "Gain 9 credits.",
        "type_code": "event",
        "side_code": "runner",
        "faction_code": "anarch",
        "pack_code": "core",
        "keywords": "",
        "cost": 5,
        "strength": None,
        "agenda_points": None,
        "influence_cost": 0,
        "deck_limit": 3,
        "uniqueness": 0,
    },
    {
        "code": "01002",
        "title": "Diesel",
        "stripped_text": "Draw 3 cards.",
        "type_code": "event",
        "side_code": "runner",
        "faction_code": "shaper",
        "pack_code": "core",
        "keywords": "",
        "cost": 0,
        "strength": None,
        "agenda_points": None,
        "influence_cost": 1,
        "deck_limit": 3,
        "uniqueness": 0,
    },
    {
        "code": "01003",
        "title": "Corroder",
        "stripped_text": "1 credit: +1 strength.\nInterface -> 1 credit: Break 1 barrier subroutine.",
        "type_code": "program",
        "side_code": "runner",
        "faction_code": "anarch",
        "pack_code": "core",
        "keywords": "Icebreaker - Fracter",
        "cost": 2,
        "strength": 2,
        "agenda_points": None,
        "influence_cost": 2,
        "deck_limit": 3,
        "uniqueness": 0,
    },
    {
        "code": "01004",
        "title": "Hedge Fund",
        "stripped_text": "Gain 9 credits.",
        "type_code": "operation",
        "side_code": "corp",
        "faction_code": "haas-bioroid",
        "pack_code": "core",
        "keywords": "Transaction",
        "cost": 5,
        "strength": None,
        "agenda_points": None,
        "influence_cost": 0,
        "deck_limit": 3,
        "uniqueness": 0,
    },
    {
        "code": "01005",
        "title": "Ice Wall",
        "stripped_text": "Subroutine End the run.",
        "type_code": "ice",
        "side_code": "corp",
        "faction_code": "weyland-consortium",
        "pack_code": "core",
        "keywords": "Barrier",
        "cost": 1,
        "strength": 1,
        "agenda_points": None,
        "influence_cost": 1,
        "deck_limit": 3,
        "uniqueness": 0,
    },
    {
        "code": "01006",
        "title": "Astroscript Pilot Program",
        "stripped_text": "When you score Astroscript Pilot Program, place 1 agenda counter on it.",
        "type_code": "agenda",
        "side_code": "corp",
        "faction_code": "nbn",
        "pack_code": "core",
        "keywords": "",
        "cost": None,
        "strength": None,
        "agenda_points": 2,
        "influence_cost": None,
        "deck_limit": 3,
        "uniqueness": 0,
    },
    {
        "code": "01007",
        "title": "Desperado",
        "stripped_text": "+1 MU. Whenever you make a successful run, gain 1 credit.",
        "type_code": "hardware",
        "side_code": "runner",
        "faction_code": "criminal",
        "pack_code": "core",
        "keywords": "Console",
        "cost": 3,
        "strength": None,
        "agenda_points": None,
        "influence_cost": 3,
        "deck_limit": 1,
        "uniqueness": 1,
    },
    {
        "code": "01008",
        "title": "Kati Jones",
        "stripped_text": "Click: Place 3 credits on Kati Jones.",
        "type_code": "resource",
        "side_code": "runner",
        "faction_code": "criminal",
        "pack_code": "core",
        "keywords": "Connection",
        "cost": 2,
        "strength": None,
        "agenda_points": None,
        "influence_cost": 2,
        "deck_limit": 1,
        "uniqueness": 1,
    },
]

SAMPLE_DECKLISTS = [
    {
        "id": 1,
        "uuid": "deck-1",
        "name": "Tournament Anarch",
        "description": "Strong anarch build",
        "user_name": "testplayer1",
        "date_creation": "2024-01-01",
        "tournament_badge": 1,
        "cards": {"01001": 3, "01003": 2, "01007": 1},
    },
    {
        "id": 2,
        "uuid": "deck-2",
        "name": "Casual Shaper",
        "description": "Fun deck",
        "user_name": "testplayer2",
        "date_creation": "2024-01-05",
        "tournament_badge": 0,
        "cards": {"01001": 3, "01002": 3, "01003": 1},
    },
    {
        "id": 3,
        "uuid": "deck-3",
        "name": "Corp Rush",
        "description": "Fast advance corp",
        "user_name": "testplayer1",
        "date_creation": "2024-01-10",
        "tournament_badge": 1,
        "cards": {"01004": 3, "01005": 3, "01006": 3},
    },
    {
        "id": 4,
        "uuid": "deck-4",
        "name": "NBN Glacier",
        "description": "Slow and steady",
        "user_name": "testplayer3",
        "date_creation": "2024-01-15",
        "tournament_badge": 0,
        "cards": {"01004": 3, "01006": 2},
    },
]

# ---------------------------------------------------------------------------
# Sample review data
# ---------------------------------------------------------------------------

SAMPLE_REVIEWS = [
    {
        "id": 1,
        "title": "Ice Wall",
        "user": "TestReviewer",
        "ruling": "A cheap barrier that ends the run. Glacier decks prefer more taxing ice, but Ice Wall is great for rush strategies where you need affordable protection early.",
        "votes": 10,
        "comments": [
            {
                "user": "Commenter1",
                "comment": "Agreed, this is pure rush ice. Glacier wants something with higher break cost.",
                "date_create": "2024-01-01T00:00:00+00:00",
                "date_update": "2024-01-01T00:00:00+00:00",
            }
        ],
        "date_create": "2024-01-01T00:00:00+00:00",
        "date_update": "2024-01-01T00:00:00+00:00",
    },
    {
        "id": 2,
        "title": "Sure Gamble",
        "user": "EconExpert",
        "ruling": "The benchmark economy card. 5 credits in, 9 out, net gain of 4. Every other economy operation should be compared to this baseline.",
        "votes": 15,
        "comments": [],
        "date_create": "2024-01-05T00:00:00+00:00",
        "date_update": "2024-01-05T00:00:00+00:00",
    },
]

# ---------------------------------------------------------------------------
# Sample concepts
# ---------------------------------------------------------------------------

SAMPLE_CONCEPTS = {
    "glacier": {
        "name": "Glacier",
        "side": "corp",
        "category": "archetype",
        "description": "Build tall servers with expensive ice. Score behind layered defenses.",
        "key_cards": ["01005"],
        "sample_questions": [
            "Why does glacier prefer expensive ice?",
            "What runner strategy counters glacier?",
        ],
    },
    "rush": {
        "name": "Rush",
        "side": "corp",
        "category": "archetype",
        "description": "Score fast before the runner sets up. Use cheap ice and speed.",
        "key_cards": ["01005"],
        "sample_questions": [
            "What makes rush different from glacier?",
            "Why do rush decks prefer cheap ice?",
        ],
    },
    "tempo": {
        "name": "Tempo",
        "side": "neutral",
        "category": "strategic-principle",
        "description": "Getting more done per turn than your opponent. Efficiency of clicks and credits.",
        "key_cards": [],
        "sample_questions": [
            "Why is tempo important in Netrunner?",
        ],
    },
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _insert_cards(conn, cards):
    """Insert card rows into an initialised database."""
    for c in cards:
        conn.execute(
            """
            INSERT OR REPLACE INTO cards
            (code, title, stripped_text, type_code, side_code, faction_code,
             pack_code, keywords, cost, strength, agenda_points, influence_cost,
             deck_limit, uniqueness, image_url, raw_json, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                c["code"],
                c["title"],
                c["stripped_text"],
                c["type_code"],
                c["side_code"],
                c["faction_code"],
                c["pack_code"],
                c["keywords"],
                c["cost"],
                c["strength"],
                c["agenda_points"],
                c["influence_cost"],
                c["deck_limit"],
                c["uniqueness"],
                "",
                json.dumps(c),
                "2024-01-01T00:00:00",
            ),
        )
    conn.commit()


def _insert_decklists(conn, decklists):
    """Insert decklist rows into an initialised database."""
    for dl in decklists:
        conn.execute(
            """
            INSERT OR REPLACE INTO decklists
            (id, uuid, name, description, user_name, date_creation,
             tournament_badge, cards_json, mwl_code, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dl["id"],
                dl["uuid"],
                dl["name"],
                dl["description"],
                dl["user_name"],
                dl["date_creation"],
                dl["tournament_badge"],
                json.dumps(dl["cards"]),
                "",
                "2024-01-01T00:00:00",
            ),
        )
    conn.commit()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_conn():
    """In-memory SQLite connection with schema initialised (empty)."""
    from src.card_data import init_db

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()


@pytest.fixture()
def populated_db(db_conn):
    """In-memory database pre-loaded with sample cards and decklists."""
    _insert_cards(db_conn, SAMPLE_CARDS)
    _insert_decklists(db_conn, SAMPLE_DECKLISTS)
    return db_conn


@pytest.fixture()
def sample_reviews():
    """Sample NRDB reviews for testing review search."""
    return SAMPLE_REVIEWS.copy()


@pytest.fixture()
def sample_concepts():
    """Sample meta concepts catalog for testing."""
    return SAMPLE_CONCEPTS.copy()


@pytest.fixture()
def empty_memory():
    """Empty concept memory for testing."""
    return {
        "concepts": {},
        "sessions": [],
        "version": 2,
    }
