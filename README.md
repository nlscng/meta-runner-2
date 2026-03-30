# 🃏 Meta Runner v2

An agentic Netrunner meta learning tool that teaches **metagame concepts** — archetypes, matchups, synergy patterns, and strategic principles — through adaptive quizzing with memory, planning, and initiative.

> Meta Runner v1 taught you *what cards do*. v2 teaches you *why they matter in the meta*.

## What's Different from v1

| | v1 | v2 |
|---|---|---|
| **Unit of learning** | Card facts (`"What does Spin Doctor do?"`) | Meta concepts (`"Why does glacier prefer expensive ice?"`) |
| **Memory** | None — every session starts fresh | SM-2 spaced repetition over concepts across sessions |
| **Planning** | Random questions | Session opens with a personalized plan targeting weak concepts |
| **Initiative** | None | Agent adds meta commentary and mid-session course correction |
| **Meta knowledge** | Card popularity stats | NRDB community reviews as contextual knowledge source |

## Architecture

```
src/
  card_data.py        — Card + decklist data layer (NRDB v2 API → SQLite) [from v1]
  meta_concepts.py    — Concepts catalog, SM-2 scheduling, concept memory
  review_index.py     — Lightweight keyword search over NRDB community reviews
  quiz_agent.py       — CLI agent with memory, planning, and initiative
  web_ui.py           — Gradio browser UI with chat + card image display
data/
  reviews.json        — Cached NRDB reviews (fetched once, gitignored)
  concept_memory.json — User's concept understanding (gitignored)
tests/
  conftest.py         — Shared fixtures with deterministic test data
  test_card_data.py   — Card/decklist storage and meta stats
  test_meta_concepts.py — SM-2 algorithm, concept selection, catalog I/O
  test_review_index.py  — Review search and card mention extraction
  test_quiz_agent.py    — Agent behaviors: session planning, concept questions, course correction
  test_web_ui.py        — Web UI agent response and card display
```

## Setup

**Prerequisites:** Python 3.10+, [uv](https://docs.astral.sh/uv/getting-started/installation/)

```bash
git clone https://github.com/nlscng/meta-runner-2.git
cd meta-runner-2
uv sync

# Fetch card data, decklists, and reviews
uv run python -m src.card_data

# Start the CLI agent
uv run python -m src.quiz_agent

# Or start the web UI (opens in browser at http://localhost:7860)
uv run python -m src.web_ui
```

## Sample Session

```
============================================================
🃏 Meta Runner v2 — Netrunner Meta Learning Agent
============================================================

📋 Session Plan:
  • Glacier — 🆕 new concept
  • Rush — 🆕 new concept
  • Kill / Flatline — 📅 overdue for review
  • Ice Economics — ⚠️ weak (40% accuracy)

Type 'quiz' to start, 'help' for commands.

You> quiz

🃏 [archetype] Glacier

  Why does glacier prefer expensive, multi-sub ice over cheap end-the-run ice?

  (Answer in your own words, then self-evaluate with: 0=wrong, 3=hard, 4=good, 5=easy)

You> because glacier wants each run to cost the runner more credits than they gain

📝 Your answer noted. Now self-evaluate:
  0 = didn't know  |  3 = hard but got it  |  4 = good  |  5 = easy

You> 4

✅ Strong understanding!

  📚 Community insight: From review of Ice Wall: "A cheap barrier that ends the run.
     Glacier decks prefer more taxing ice..."

  Score: 1/1 (100%)
```

## Commands

| Command | What it does |
|---------|-------------|
| `quiz` / `next` | Get a new concept question |
| `plan` | Show/refresh the session plan |
| `concepts` | List all meta concepts with your progress |
| `score` | See your current score |
| `help` | Show available commands |
| `quit` | End the session |

## Running Tests

```bash
uv run pytest -v
```

## Origin

Born from a [Loonshot Framework exploration](https://github.com/nlscng/loonshot-exploration) — building an agentic Netrunner learning tool. See the [meta-runner v2 exploration doc](https://github.com/nlscng/loonshot-exploration/blob/main/explorations/2026-03-10-cycle2-meta-runner-v2.md) for design decisions and the [knowledge graph feasibility study](https://github.com/nlscng/loonshot-exploration/blob/main/journal/2026-03-28.md) for future data enrichment plans.

## Data Sources

- **[NetrunnerDB](https://netrunnerdb.com)** v2 API — card data, decklists, community reviews
- **[AlwaysBeRunning.net](https://alwaysberunning.net)** — tournament data (planned, Track B)
