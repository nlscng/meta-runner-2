"""
Meta Concepts — the unit of learning for meta-runner v2.

Instead of quizzing on individual card facts ("what does Card X do?"),
meta-runner v2 teaches metagame concepts: archetypes, matchups,
synergy patterns, and strategic principles.

SM-2 schedules concept review. The concepts catalog defines the
concept space the entire system operates on.
"""

import json
import os
from datetime import datetime, timezone

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
CONCEPTS_CATALOG_PATH = os.path.join(DATA_DIR, "meta_concepts.json")
CONCEPT_MEMORY_PATH = os.path.join(DATA_DIR, "concept_memory.json")


# ---------------------------------------------------------------------------
# Concepts catalog — defines the concept space
# ---------------------------------------------------------------------------

DEFAULT_CONCEPTS = {
    "glacier": {
        "name": "Glacier",
        "side": "corp",
        "category": "archetype",
        "description": "Build tall, taxing servers with expensive ice. Score agendas behind layered defenses. Win by making every run cost more than the runner can sustain.",
        "key_cards": [],
        "sample_questions": [
            "Why does glacier prefer expensive, multi-sub ice over cheap end-the-run ice?",
            "What runner strategy is strongest against glacier?",
            "Why is glacier weaker in metas with efficient AI breakers?",
        ],
    },
    "rush": {
        "name": "Rush",
        "side": "corp",
        "category": "archetype",
        "description": "Score agendas quickly before the runner sets up their rig. Use cheap, taxing ice and fast-advance tools to close the game early.",
        "key_cards": [],
        "sample_questions": [
            "What makes a corp deck 'rush' vs 'glacier'?",
            "Why do rush decks prefer cheap ice?",
            "What runner cards punish a rush strategy?",
        ],
    },
    "fast-advance": {
        "name": "Fast Advance",
        "side": "corp",
        "category": "archetype",
        "description": "Score agendas from hand in a single turn using tools that advance or score without needing to protect a remote server over multiple turns.",
        "key_cards": [],
        "sample_questions": [
            "What's the fundamental advantage of scoring from hand?",
            "How does fast advance reduce the runner's scoring window?",
            "Name a card or combo that enables fast advance.",
        ],
    },
    "asset-spam": {
        "name": "Asset Spam",
        "side": "corp",
        "category": "archetype",
        "description": "Flood the board with assets and upgrades, overwhelming the runner's ability to trash them all. Win through economic attrition.",
        "key_cards": [],
        "sample_questions": [
            "Why is click compression central to asset spam's strategy?",
            "What runner response is most effective against asset spam?",
            "Why does asset spam care about trash costs?",
        ],
    },
    "kill": {
        "name": "Kill / Flatline",
        "side": "corp",
        "category": "archetype",
        "description": "Win by dealing lethal damage to the runner (net, meat, or brain) rather than scoring 7 agenda points. Often uses traps, punitive operations, or combo kills.",
        "key_cards": [],
        "sample_questions": [
            "What should a runner check before running against a suspected kill deck?",
            "Why do kill decks often include never-advance bluffs?",
            "How does the runner's hand size affect kill deck viability?",
        ],
    },
    "aggro-runner": {
        "name": "Aggro / Tempo Runner",
        "side": "runner",
        "category": "archetype",
        "description": "Apply early pressure with cheap breakers and run events. Deny the corp time to set up. Trade efficiency for speed.",
        "key_cards": [],
        "sample_questions": [
            "Why do aggro runners prioritize cheap install costs?",
            "What corp strategy is most vulnerable to early aggression?",
            "When should an aggro runner slow down and build a rig?",
        ],
    },
    "econ-denial": {
        "name": "Economic Denial",
        "side": "runner",
        "category": "archetype",
        "description": "Attack the corp's credit pool to prevent them from rezzing ice, advancing agendas, or executing their game plan.",
        "key_cards": [],
        "sample_questions": [
            "Why is denying corp credits more effective than gaining your own in some matchups?",
            "Name a card that directly attacks corp economy.",
            "What makes econ denial risky as a primary strategy?",
        ],
    },
    "deep-dig": {
        "name": "Deep Dig / Multi-access",
        "side": "runner",
        "category": "archetype",
        "description": "Win by accessing multiple cards from centrals per run. Build toward a big turn where you see many cards from R&D or HQ at once.",
        "key_cards": [],
        "sample_questions": [
            "Why is multi-access on R&D stronger than repeated single accesses?",
            "How does the corp defend against deep dig strategies?",
            "What's the trade-off between building multi-access and applying early pressure?",
        ],
    },
    "ice-economics": {
        "name": "Ice Economics",
        "side": "corp",
        "category": "strategic-principle",
        "description": "The economic balance between rez cost (what corp pays) and break cost (what runner pays). Glacier works when break cost exceeds rez cost over many runs.",
        "key_cards": [],
        "sample_questions": [
            "Why does ice with multiple subroutines tend to be more taxing?",
            "How do fixed-strength breakers change ice economics?",
            "Why is ice that costs 1 to break often worse than ice that costs 4, even if it ends the run?",
        ],
    },
    "scoring-windows": {
        "name": "Scoring Windows",
        "side": "corp",
        "category": "strategic-principle",
        "description": "The concept that corps score agendas during moments when the runner can't (or won't) contest the remote — either because they lack the tools, credits, or information.",
        "key_cards": [],
        "sample_questions": [
            "What creates a scoring window for the corp?",
            "Why is the start of the game often the best scoring window?",
            "How does the runner close scoring windows?",
        ],
    },
    "tempo": {
        "name": "Tempo",
        "side": "neutral",
        "category": "strategic-principle",
        "description": "The pace of the game — who is spending their clicks and credits efficiently. Tempo advantage means getting more done per turn than your opponent.",
        "key_cards": [],
        "sample_questions": [
            "Why is installing a card without clicking to draw it first a tempo advantage?",
            "How do operations that combine draw + credits provide tempo?",
            "When should a player sacrifice tempo for long-term position?",
        ],
    },
    "runner-rig-progression": {
        "name": "Rig Progression",
        "side": "runner",
        "category": "strategic-principle",
        "description": "The phases of assembling a breaker suite — from face-checking with no breakers, to partial rig, to fully set up. Each phase changes what servers are safe to run.",
        "key_cards": [],
        "sample_questions": [
            "Why is the 'no breakers' phase the most dangerous for the runner?",
            "What does the corp do differently against a fully-rigged runner vs an incomplete rig?",
            "Why do some runners skip traditional breaker suites entirely?",
        ],
    },
    "bluffing-and-reading": {
        "name": "Bluffing and Reading",
        "side": "neutral",
        "category": "strategic-principle",
        "description": "Netrunner's hidden information creates constant bluffing — is that installed card an agenda or a trap? Reading means inferring what the opponent has based on their actions.",
        "key_cards": [],
        "sample_questions": [
            "What information does installing a card in a new remote without ice give the runner?",
            "Why do experienced players track corp credit totals when deciding whether to run?",
            "How does the presence of traps in a meta change runner behavior even when no traps are installed?",
        ],
    },
    "matchup-glacier-vs-aggro": {
        "name": "Glacier vs Aggro Matchup",
        "side": "neutral",
        "category": "matchup",
        "description": "The classic tension: glacier wants time to build; aggro wants to end the game before defenses come online. The race between setup speed and run pressure.",
        "key_cards": [],
        "sample_questions": [
            "Why does the aggro runner want to keep the corp poor in this matchup?",
            "At what point does the glacier corp stabilize against aggro?",
            "What signals tell the aggro runner it's too late to keep pressuring?",
        ],
    },
    "matchup-kill-vs-careful": {
        "name": "Kill vs Careful Runner Matchup",
        "side": "neutral",
        "category": "matchup",
        "description": "Kill decks punish aggressive runners; careful runners trade tempo for safety. The dynamic changes based on how well the runner can read the corp's plan.",
        "key_cards": [],
        "sample_questions": [
            "Why do runners keep a full hand against suspected kill decks?",
            "What's the risk of playing too cautiously against a kill deck that's actually a fast advance deck?",
            "How does the runner determine if the corp is on a kill plan?",
        ],
    },
    "meta-shift-awareness": {
        "name": "Meta Shift Awareness",
        "side": "neutral",
        "category": "meta-knowledge",
        "description": "Understanding how and why the competitive landscape changes — ban lists, new card releases, tournament results, and community adaptation all shift which decks are strong.",
        "key_cards": [],
        "sample_questions": [
            "Why can a card go from unplayed to dominant without being changed?",
            "How do ban lists reshape the meta beyond just removing specific cards?",
            "What's the difference between a card being 'bad' and a card being 'not in the meta'?",
        ],
    },
    "deckbuilding-influence": {
        "name": "Influence and Deckbuilding",
        "side": "neutral",
        "category": "meta-knowledge",
        "description": "The influence system forces trade-offs when including out-of-faction cards. Understanding influence economy is key to building competitive decks.",
        "key_cards": [],
        "sample_questions": [
            "Why do players spend influence on economy cards from other factions?",
            "What makes a high-influence card worth the splash?",
            "How does influence limit the diversity of archetypes within a faction?",
        ],
    },
}


def load_concepts_catalog(path=CONCEPTS_CATALOG_PATH):
    """Load concepts catalog from file, falling back to defaults."""
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return DEFAULT_CONCEPTS.copy()


def save_concepts_catalog(concepts, path=CONCEPTS_CATALOG_PATH):
    """Save concepts catalog to file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(concepts, f, indent=2)


# ---------------------------------------------------------------------------
# Concept memory — SM-2 scheduling over concepts
# ---------------------------------------------------------------------------

def _empty_memory():
    return {
        "concepts": {},
        "sessions": [],
        "version": 2,
    }


def load_concept_memory(path=CONCEPT_MEMORY_PATH):
    """Load the user's concept understanding memory."""
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return _empty_memory()


def save_concept_memory(memory, path=CONCEPT_MEMORY_PATH):
    """Save concept memory to file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(memory, f, indent=2)


def _init_concept_state():
    """Initial SM-2 state for a new concept."""
    return {
        "times_tested": 0,
        "times_correct": 0,
        "ef": 2.5,
        "interval": 0,
        "n": 0,
        "last_seen": None,
        "next_review": None,
    }


def sm2_update(state, grade):
    """Apply SM-2 algorithm to a concept's state.

    grade: 0 (wrong), 3 (hard), 4 (good), 5 (easy)
    Returns updated state dict (does not mutate input).
    """
    s = dict(state)
    s["times_tested"] = s.get("times_tested", 0) + 1

    if grade >= 3:
        s["times_correct"] = s.get("times_correct", 0) + 1
        n = s.get("n", 0)
        if n == 0:
            s["interval"] = 1
        elif n == 1:
            s["interval"] = 6
        else:
            s["interval"] = round(s["interval"] * s["ef"])
        s["n"] = n + 1
    else:
        s["n"] = 0
        s["interval"] = 1

    ef = s["ef"] + (0.1 - (5 - grade) * (0.08 + (5 - grade) * 0.02))
    s["ef"] = max(ef, 1.3)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    s["last_seen"] = today

    from datetime import timedelta
    next_dt = datetime.now(timezone.utc) + timedelta(days=s["interval"])
    s["next_review"] = next_dt.strftime("%Y-%m-%d")

    return s


def get_concept_state(memory, concept_id):
    """Get SM-2 state for a concept, initializing if needed."""
    if concept_id not in memory["concepts"]:
        memory["concepts"][concept_id] = _init_concept_state()
    return memory["concepts"][concept_id]


def select_next_concepts(memory, catalog, target=4):
    """Select concepts to explore this session using SM-2 priority.

    Priority order:
    1. Overdue concepts (next_review <= today)
    2. Weak concepts (accuracy < 60%, tested >= 3 times)
    3. Untested concepts
    4. Strong concepts due for reinforcement
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    overdue = []
    weak = []
    untested = []
    reinforcement = []

    for concept_id in catalog:
        state = memory["concepts"].get(concept_id)
        if state is None:
            untested.append(concept_id)
            continue

        next_review = state.get("next_review")
        times_tested = state.get("times_tested", 0)
        times_correct = state.get("times_correct", 0)
        accuracy = times_correct / times_tested if times_tested > 0 else 0

        if next_review and next_review <= today:
            overdue.append((concept_id, next_review))
        elif times_tested >= 3 and accuracy < 0.6:
            weak.append((concept_id, accuracy))
        else:
            reinforcement.append((concept_id, state.get("interval", 0)))

    # Sort each group
    overdue.sort(key=lambda x: x[1])  # oldest overdue first
    weak.sort(key=lambda x: x[1])     # lowest accuracy first
    reinforcement.sort(key=lambda x: x[1])  # shortest interval first

    selected = []
    for concept_id, _ in overdue:
        if len(selected) >= target:
            break
        selected.append(concept_id)
    for concept_id in untested:
        if len(selected) >= target:
            break
        selected.append(concept_id)
    for concept_id, _ in weak:
        if len(selected) >= target:
            break
        selected.append(concept_id)
    for concept_id, _ in reinforcement:
        if len(selected) >= target:
            break
        selected.append(concept_id)

    return selected
