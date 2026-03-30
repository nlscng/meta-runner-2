"""
Review Index — lightweight keyword search over NRDB community reviews.

Provides the agent's meta knowledge source for Track A without building
a full graph database or vector store. Reviews contain archetype discussion,
synergy explanations, matchup advice, and meta positioning written by
experienced players.
"""

import json
import os
import re

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
REVIEWS_PATH = os.path.join(DATA_DIR, "reviews.json")


def load_reviews(path=REVIEWS_PATH):
    """Load reviews from the cached JSON file."""
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def _extract_card_mentions(text):
    """Extract card codes mentioned via NRDB links in review/comment HTML."""
    return re.findall(r'/en/card/(\d{5})', text)


def _normalize(text):
    """Strip HTML tags and lowercase for search."""
    clean = re.sub(r'<[^>]+>', '', text)
    clean = re.sub(r'\s+', ' ', clean)
    return clean.lower().strip()


def search_reviews(reviews, query, limit=5):
    """Keyword search over reviews. Returns matching reviews sorted by vote count.

    Searches review text, comments, and card title.
    """
    terms = query.lower().split()
    results = []

    for review in reviews:
        text = _normalize(review.get("ruling", "") + " " + review.get("title", ""))
        # Include comment text in search
        comments_text = " ".join(
            _normalize(c.get("comment", ""))
            for c in review.get("comments", [])
        )
        full_text = text + " " + comments_text

        # Score: how many query terms appear
        score = sum(1 for t in terms if t in full_text)
        if score > 0:
            results.append((score, review.get("votes", 0), review))

    # Sort by match score, then by votes
    results.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [r[2] for r in results[:limit]]


def get_reviews_for_card(reviews, card_title):
    """Get reviews that are specifically about a card (by title match)."""
    title_lower = card_title.lower()
    return [r for r in reviews if r.get("title", "").lower() == title_lower]


def get_reviews_mentioning_card(reviews, card_code):
    """Get reviews that mention a specific card code in their text."""
    results = []
    for review in reviews:
        text = review.get("ruling", "")
        comments = " ".join(c.get("comment", "") for c in review.get("comments", []))
        if card_code in _extract_card_mentions(text + " " + comments):
            results.append(review)
    return results
