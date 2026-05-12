"""
Review Index — lightweight keyword search over NRDB community reviews.

Provides the agent's meta knowledge source for Track A without building
a full graph database or vector store. Reviews contain archetype discussion,
synergy explanations, matchup advice, and meta positioning written by
experienced players.

Internal review schema (what load_reviews returns and search functions expect):

    {
        "id": int,
        "title": str,           # card title the review is about
        "card_code": str,       # NRDB card code (e.g. "01001")
        "user": str,            # reviewer username
        "ruling": str,          # review body text (may contain HTML)
        "votes": int,           # community upvotes
        "comments": [           # threaded comments on the review
            {"user": str, "comment": str, "date_create": str, "date_update": str}
        ],
        "date_create": str,
        "date_update": str,
    }

The fetch_reviews() function normalises raw NRDB API responses into this
schema so the rest of the codebase can rely on a single, stable format.
"""

import json
import logging
import os
import re

import httpx

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
REVIEWS_PATH = os.path.join(DATA_DIR, "reviews.json")

NRDB_REVIEWS_URL = "https://netrunnerdb.com/api/2.0/public/reviews"
NRDB_CARDS_URL = "https://netrunnerdb.com/api/2.0/public/cards"

_FETCH_TIMEOUT = 60  # seconds — the reviews endpoint can be slow


# ---------------------------------------------------------------------------
# Fetching and normalisation
# ---------------------------------------------------------------------------

def _normalize_comment(raw):
    """Normalise a single comment from the NRDB API response."""
    return {
        "user": raw.get("username", raw.get("user_name", raw.get("user", ""))),
        "comment": raw.get("text_html", raw.get("text", raw.get("comment", ""))),
        "date_create": raw.get("date_creation", raw.get("date_create", "")),
        "date_update": raw.get("date_update", ""),
    }


def _normalize_nrdb_review(raw, card_titles=None):
    """Normalise a single review object from the NRDB API response.

    The NRDB v2 API uses field names like ``date_creation``, ``username``,
    and ``text_html``.  Our internal schema uses shorter names (``date_create``,
    ``user``, ``ruling``).  This function bridges the two.

    Parameters
    ----------
    raw : dict
        A single review dict straight from the API.
    card_titles : dict | None
        Optional mapping of card_code -> card_title for enrichment.
    """
    card_code = raw.get("card_code", raw.get("code", ""))

    # Resolve card title: prefer explicit title, then lookup, then fallback.
    title = raw.get("card_title", raw.get("title", ""))
    if not title and card_titles and card_code:
        title = card_titles.get(card_code, "")

    return {
        "id": raw.get("id"),
        "title": title,
        "card_code": str(card_code) if card_code else "",
        "user": raw.get("username", raw.get("user_name", raw.get("user", ""))),
        "ruling": raw.get("text_html", raw.get("text", raw.get("ruling", ""))),
        "votes": raw.get("vote_count", raw.get("votes", 0)),
        "comments": [
            _normalize_comment(c) for c in raw.get("comments", [])
        ],
        "date_create": raw.get("date_creation", raw.get("date_create", "")),
        "date_update": raw.get("date_update", ""),
    }


def _fetch_card_titles(timeout=_FETCH_TIMEOUT):
    """Fetch card_code -> title mapping from NRDB for review enrichment.

    Returns an empty dict on failure so callers can proceed without titles.
    """
    try:
        resp = httpx.get(NRDB_CARDS_URL, timeout=timeout)
        resp.raise_for_status()
        cards = resp.json().get("data", [])
        return {c["code"]: c.get("title", "") for c in cards if "code" in c}
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        logger.warning("Could not fetch card titles for review enrichment: %s", exc)
        return {}


def fetch_reviews(path=REVIEWS_PATH, *, force=False, timeout=_FETCH_TIMEOUT):
    """Fetch all reviews from the NRDB API and cache them to *path*.

    Parameters
    ----------
    path : str
        Where to write the cached JSON file.
    force : bool
        If True, re-fetch even when a cached file already exists.
    timeout : int
        HTTP request timeout in seconds.

    Returns
    -------
    list[dict]
        Normalised review dicts in our internal schema.

    Raises
    ------
    httpx.HTTPStatusError
        On 4xx / 5xx responses from the NRDB API.
    httpx.TimeoutException
        If the request exceeds *timeout*.
    """
    if not force and os.path.exists(path):
        logger.info("Using cached reviews at %s", path)
        return load_reviews(path)

    logger.info("Fetching reviews from %s ...", NRDB_REVIEWS_URL)
    resp = httpx.get(NRDB_REVIEWS_URL, timeout=timeout)
    resp.raise_for_status()

    raw_reviews = resp.json().get("data", [])
    logger.info("Received %d raw reviews", len(raw_reviews))

    # Fetch card titles so we can attach human-readable names to reviews
    card_titles = _fetch_card_titles(timeout=timeout)

    reviews = [_normalize_nrdb_review(r, card_titles) for r in raw_reviews]

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(reviews, f, indent=2)
    logger.info("Cached %d reviews to %s", len(reviews), path)

    return reviews


def load_reviews(path=REVIEWS_PATH):
    """Load reviews from the cached JSON file.

    Returns an empty list if the file does not exist — the agent should
    still work (with degraded commentary) when reviews haven't been fetched.
    """
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


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    force = "--force" in sys.argv
    reviews = fetch_reviews(force=force)
    print(f"Reviews: {len(reviews)} cached at {REVIEWS_PATH}")
