"""
Card Data Layer — fetches and stores Netrunner card data from NetrunnerDB v2 API.

Carried forward from meta-runner v1 with minor cleanup.
The card database is the foundation both quiz types (v1 fact-based and v2 concept-based) build on.
"""

import httpx
import sqlite3
import json
import os
from datetime import datetime, timedelta, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "netrunner.db")
NRDB_BASE = "https://netrunnerdb.com/api/2.0/public"


def get_db(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(conn):
    """Create tables for card data and meta stats."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS cards (
            code TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            stripped_text TEXT,
            type_code TEXT,
            side_code TEXT,
            faction_code TEXT,
            pack_code TEXT,
            keywords TEXT,
            cost INTEGER,
            strength INTEGER,
            agenda_points INTEGER,
            influence_cost INTEGER,
            deck_limit INTEGER,
            uniqueness INTEGER DEFAULT 0,
            image_url TEXT,
            raw_json TEXT,
            fetched_at TEXT
        );

        CREATE TABLE IF NOT EXISTS decklists (
            id INTEGER PRIMARY KEY,
            uuid TEXT,
            name TEXT,
            description TEXT,
            user_name TEXT,
            date_creation TEXT,
            tournament_badge INTEGER DEFAULT 0,
            cards_json TEXT,
            mwl_code TEXT,
            fetched_at TEXT
        );

        CREATE TABLE IF NOT EXISTS card_meta_stats (
            card_code TEXT PRIMARY KEY,
            card_title TEXT,
            tournament_deck_count INTEGER DEFAULT 0,
            total_deck_count INTEGER DEFAULT 0,
            avg_copies REAL DEFAULT 0,
            last_computed TEXT,
            FOREIGN KEY (card_code) REFERENCES cards(code)
        );

        CREATE INDEX IF NOT EXISTS idx_cards_faction ON cards(faction_code);
        CREATE INDEX IF NOT EXISTS idx_cards_type ON cards(type_code);
        CREATE INDEX IF NOT EXISTS idx_cards_side ON cards(side_code);
        CREATE INDEX IF NOT EXISTS idx_decklists_tournament ON decklists(tournament_badge);
    """)
    conn.commit()


def fetch_all_cards(conn):
    """Fetch all cards from NRDB v2 API and store in SQLite."""
    print("Fetching cards from NetrunnerDB v2 API...")
    resp = httpx.get(f"{NRDB_BASE}/cards", timeout=30)
    resp.raise_for_status()
    data = resp.json()

    image_template = data.get("imageUrlTemplate", "")
    cards = data["data"]
    print(f"  Got {len(cards)} cards total")

    inserted = 0
    for card in cards:
        image_url = image_template.replace("{code}", card["code"]) if image_template else ""
        conn.execute("""
            INSERT OR REPLACE INTO cards
            (code, title, stripped_text, type_code, side_code, faction_code,
             pack_code, keywords, cost, strength, agenda_points, influence_cost,
             deck_limit, uniqueness, image_url, raw_json, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            card["code"],
            card.get("title", ""),
            card.get("stripped_text", ""),
            card.get("type_code", ""),
            card.get("side_code", ""),
            card.get("faction_code", ""),
            card.get("pack_code", ""),
            card.get("keywords", ""),
            card.get("cost"),
            card.get("strength"),
            card.get("agenda_points"),
            card.get("faction_cost"),
            card.get("deck_limit"),
            1 if card.get("uniqueness") else 0,
            image_url,
            json.dumps(card),
            datetime.now(timezone.utc).isoformat(),
        ))
        inserted += 1

    conn.commit()
    print(f"  Stored {inserted} cards in database")
    return inserted


def fetch_decklists_for_date(client, date_str):
    """Fetch published decklists for a specific date."""
    resp = client.get(f"{NRDB_BASE}/decklists/by_date/{date_str}", timeout=30)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    return resp.json().get("data", [])


def fetch_recent_decklists(conn, days=90):
    """Fetch decklists from the last N days."""
    print(f"Fetching decklists from the last {days} days...")
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=days)

    total_decklists = 0
    tournament_decklists = 0

    with httpx.Client() as client:
        current = start_date
        while current <= end_date:
            date_str = current.strftime("%Y-%m-%d")
            try:
                decklists = fetch_decklists_for_date(client, date_str)
                for dl in decklists:
                    has_badge = 1 if dl.get("tournament_badge") else 0
                    conn.execute("""
                        INSERT OR REPLACE INTO decklists
                        (id, uuid, name, description, user_name, date_creation,
                         tournament_badge, cards_json, mwl_code, fetched_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        dl["id"],
                        dl.get("uuid", ""),
                        dl.get("name", ""),
                        dl.get("description", ""),
                        dl.get("user_name", ""),
                        dl.get("date_creation", ""),
                        has_badge,
                        json.dumps(dl.get("cards", {})),
                        dl.get("mwl_code", ""),
                        datetime.now(timezone.utc).isoformat(),
                    ))
                    total_decklists += 1
                    if has_badge:
                        tournament_decklists += 1
            except Exception as e:
                print(f"  Warning: failed to fetch {date_str}: {e}")
            current += timedelta(days=1)

            if total_decklists % 100 == 0 and total_decklists > 0:
                conn.commit()

    conn.commit()
    print(f"  Stored {total_decklists} decklists ({tournament_decklists} tournament)")
    return total_decklists, tournament_decklists


def fetch_reviews():
    """Fetch all card reviews from NRDB v2 API. Returns list of review dicts."""
    print("Fetching reviews from NetrunnerDB v2 API...")
    resp = httpx.get(f"{NRDB_BASE}/reviews", timeout=60)
    resp.raise_for_status()
    reviews = resp.json().get("data", [])
    print(f"  Got {len(reviews)} reviews")
    return reviews


def compute_meta_stats(conn):
    """Compute card popularity stats from stored decklists."""
    print("Computing meta stats...")

    cursor = conn.execute("SELECT cards_json, tournament_badge FROM decklists")
    rows = cursor.fetchall()

    card_stats = {}

    for row in rows:
        cards = json.loads(row["cards_json"])
        is_tournament = row["tournament_badge"]
        for code, count in cards.items():
            if code not in card_stats:
                card_stats[code] = {"total": 0, "tournament": 0, "copies": []}
            card_stats[code]["total"] += 1
            card_stats[code]["copies"].append(count)
            if is_tournament:
                card_stats[code]["tournament"] += 1

    now = datetime.now(timezone.utc).isoformat()
    for code, stats in card_stats.items():
        title_row = conn.execute("SELECT title FROM cards WHERE code = ?", (code,)).fetchone()
        title = title_row["title"] if title_row else f"Unknown ({code})"
        avg_copies = sum(stats["copies"]) / len(stats["copies"]) if stats["copies"] else 0

        conn.execute("""
            INSERT OR REPLACE INTO card_meta_stats
            (card_code, card_title, tournament_deck_count, total_deck_count, avg_copies, last_computed)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (code, title, stats["tournament"], stats["total"], round(avg_copies, 2), now))

    conn.commit()
    print(f"  Computed stats for {len(card_stats)} cards")
    return len(card_stats)


def main():
    conn = get_db()
    init_db(conn)

    card_count = fetch_all_cards(conn)
    total, tournament = fetch_recent_decklists(conn, days=90)
    stats_count = compute_meta_stats(conn)

    # Fetch and save reviews
    reviews = fetch_reviews()
    reviews_path = os.path.join(os.path.dirname(__file__), "..", "data", "reviews.json")
    os.makedirs(os.path.dirname(reviews_path), exist_ok=True)
    with open(reviews_path, "w") as f:
        json.dump(reviews, f, indent=2)
    print(f"  Saved {len(reviews)} reviews to {reviews_path}")

    print("\n=== Database Summary ===")
    print(f"Cards: {card_count}")
    print(f"Decklists: {total} ({tournament} tournament)")
    print(f"Cards with meta stats: {stats_count}")
    print(f"Reviews: {len(reviews)}")

    conn.close()


if __name__ == "__main__":
    main()
