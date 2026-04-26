# Plan: use llm-wiki-anr as the data backbone for meta-runner-2

**Status**: design proposal, not implemented
**Created**: 2026-04-26
**Author**: agent session, recorded for future follow-up
**Origin question**: "How would I make this the backbone of some app, like meta-runner-2, for advanced training of deck building and game playing in ANR?"

---

## TL;DR

There's a sister project — [`llm-wiki-anr`](https://github.com/nlscng) (local
at `/mnt/f/llm-wiki-anr`) — that has independently built a curated, structured
ANR knowledge base (~1,200 wiki pages, source-cited and era-weighted). It is a
much better data backbone for meta-runner-2 than the current direct-to-NRDB
approach. **The corpus is the moat, and it is already mostly built.**

This doc captures the architecture suggestion. It is intentionally not
implementing anything — the user can come back to this and decide if/when to
follow up.

---

## What llm-wiki-anr already has

A markdown wiki under `wiki/` with structured sections, marker-tagged
machine-readable blocks, and provenance tracking. Specifically:

- **Canonical card data** mirrored from NetrunnerDB's GitHub JSON repo and
  REST API — same source of truth NRDB itself uses.
- **Per-card pages** (~860) with: card text, faction, costs, printings,
  NRDB community-review excerpts (with author + date + 👍 count), YouTube
  community discussion snippets (with channel + date + era), and archetype
  backlinks.
- **Identity pages** (~150) — same structure, plus archetype profile.
- **Archetype pages** (~32) — decklist-frequency profiles per identity (core
  cards = 50%+ inclusion, frequent = 30%+), built from a 30-day rolling
  window of NRDB-published decks.
- **Tournament pages** (~75) — championship-class events from
  alwaysberunning.net and tournaments.nullsignal.games (Cobra), with
  decklists linked and finishes recorded.
- **Decklist pages** (~250) — individual decks with comments, author,
  tournament context.
- **Cycle / pack / faction / concept pages** — for context, taxonomy,
  strategic concepts.
- **YouTube source layer** — 121 transcripts from a curated 5-channel
  allowlist (Metropole Grid, Neon Static, YsengrinSC, DullBulb, Vysetron),
  one per-video page each, mined for entity mentions, citations injected
  into card/identity/archetype pages with `channel_weight × era_decay`
  scoring.
- **Meta-era model** — pack release + MWL boundaries auto-detected; every
  time-stamped citation gets a freshness weight (current era = 1.0,
  1 era back = 0.7, 2 = 0.4, 3 = 0.2…). Most card-game tools have no
  concept of "this advice was true in 2023 and is wrong now"; this one does.
- **Synthesis pipeline** that runs after every source refresh: rebuilds
  cross-references, repairs archetype↔card backlinks, audits coherence,
  flags placeholder pages with available signal, surfaces demand for new
  pages. Codified in the wiki's `AGENTS.md` as a mandatory post-refresh
  step.

The pages use stable HTML-comment markers (e.g.
`<!-- youtube-discussion-start -->`, `<!-- archetype-backlinks-start -->`)
so they are extraction-friendly and the synthesis runs are idempotent.

---

## Why it's a better backbone than direct NRDB calls

meta-runner-2 currently treats NRDB as the source of truth and pulls
community reviews per card on demand. That's correct for v1, but it
misses things:

1. **Multi-source synthesis already done.** Wiki pages combine NRDB written
   reviews + YouTube video discussion + tournament-result citations +
   decklist-frequency archetype membership. Pulling from NRDB alone gives
   you only ~20% of that signal.
2. **Era weighting baked in.** Quizzing on "is Drafter strong?" without
   era awareness leads to incorrect answers — Drafter's evaluation has
   shifted across rotations. The wiki's era-decay model gives a principled
   way to weight evidence by recency.
3. **Cross-references precomputed.** "Which cards are most associated with
   glacier?" is one file read away (`wiki/meta/cross-references.md`) — no
   LLM call, no NRDB scraping needed.
4. **Stable, citable URLs.** Every claim in the wiki has a path. Quiz
   feedback can cite `wiki/cards/flood-the-market.md` — verifiable,
   auditable, debuggable. RAG on free-form NRDB review text can't do this.
5. **Coherence is enforced.** The synthesis-audit pipeline keeps
   contradictions surfaced. Direct NRDB pulls have no equivalent.

---

## Suggested architecture

```
                ┌──────────────────────────────────────┐
                │  meta-runner-2 (CLI / Gradio web)    │
                └────────┬───────────────────┬──────────┘
                         │                   │
                  ┌──────▼──────┐    ┌───────▼────────────┐
                  │  Coach LLM  │    │  Game engine       │
                  │  (tool use) │◄──►│  (jinteki.net      │
                  │             │    │   fork; later)     │
                  └──────┬──────┘    └────────────────────┘
                         │
        ┌────────────────┼─────────────────┐
        │                │                 │
   ┌────▼─────┐    ┌─────▼────┐     ┌──────▼──────────┐
   │ Vector   │    │  duckdb  │     │  llm-wiki-anr   │
   │ index    │    │ (cards,  │     │  (markdown,     │
   │ (chunks  │    │  decks,  │     │   citations,    │
   │  from    │    │  tourns) │     │   marker-tagged │
   │  wiki)   │    │          │     │   sections)     │
   └────┬─────┘    └─────┬────┘     └──────┬──────────┘
        │                │                 │
        └────────────────┴─────────────────┘
                         │
                  ┌──────▼─────────────┐
                  │  raw/ + scripts/   │   ← existing refresh pipeline
                  │  + AGENTS.md       │     in llm-wiki-anr
                  └────────────────────┘
```

Three layers:

### 1. Storage (already exists in llm-wiki-anr)

- `raw/` — immutable cached source pulls (NRDB, ABR, Cobra, YouTube)
- `wiki/` — synthesized, citation-bearing markdown pages
- `scripts/` — refresh + synthesis pipeline

meta-runner-2 should treat `llm-wiki-anr` as a git-submodule or a sibling
checkout. Don't duplicate the pull infrastructure.

### 2. Indexing (to be built)

- **duckdb** over `raw/api/*.json` and `raw/decklists/index.json` for
  structured queries: "all current-format runner decks with ≥18 ice that
  beat NBN: Reality Plus." A weekend's work; high leverage.
- **Embedding index** over the marker-tagged wiki chunks: chunk per
  `youtube-discussion`, per `community-evaluation`, per `archetype-
  backlinks`, etc. Use a small open-source model (bge-small or e5).
  ~10MB index, ~$0 to host. Retrieval is on typed chunks, weighted by
  the same `channel × era` score the wiki already computes.

### 3. Reasoning surface (to be built)

- LLM with two constrained tools:
  - `lookup(entity)` — fetches structured wiki data + retrieved chunks
    for a card, identity, archetype, or concept
  - `archetype_query(filters)` — e.g., "all archetypes containing
    `Flood the Market` with ≥10 decks in last 30 days"
- Force every assertion to cite a wiki path; reject unsupported claims.
- Two app modes:
  - **Deckbuilder coach** — takes user constraints, retrieves archetype
    data + community discussion, suggests builds, explains tradeoffs.
    Cheapest useful thing because it doesn't need a rules engine. The
    wiki already enables this; an existing session demonstrated it can
    answer "build me a Flood the Market deck" with full citations.
  - **Replay analyst** (later, harder) — takes a Jinteki.net replay,
    walks through it turn-by-turn, identifies decision points, retrieves
    what the wiki/community says about those plays. Needs a rules
    engine to parse game-state.

---

## Suggested order of work

1. **Add llm-wiki-anr as a git submodule** under `data/wiki/` in this repo.
   Pin to a known good commit; bump on demand.
2. **Stand up duckdb over `raw/api/*.json`.** Wrap as `DataBackbone` class
   with typed query methods (`cards_by_pack`, `decks_with_card`,
   `archetype_membership`).
3. **Wire one quiz mode to the wiki.** Replace the current NRDB review
   fetch with a wiki-page read; cite the path back to the user. Lowest-
   risk integration, immediate user-visible quality bump.
4. **Embed the marker-tagged chunks.** Add a retrieval tool the LLM can
   call. This unlocks "what does the community say about X" questions
   beyond exact entity matches.
5. **Build the deckbuilder-coach mode** as a separate command (`build`
   alongside the existing `quiz`). Expect it to be high signal.
6. **Stop here** until you've used these for a few weeks. The replay
   analyst is a much bigger project and shouldn't start until 1–5 are
   load-bearing.

---

## Honest caveats

- **IP**: NSG owns the rules and card text. Linking out + fair-use
  commentary (what the wiki does) is fine. Embedding card text *as your
  product* is a different conversation. Personal/training tool, no
  monetization → low risk. Anything else needs to involve NSG.
- **Maintenance burden**: every rotation/banlist invalidates a chunk of
  advice. The era-decay model handles this gracefully *only if* the
  synthesis pipeline keeps running. Schedule it (cron / GitHub Actions).
- **Small community**: ~5 active YouTube creators, hundreds of active
  tournament players globally. Won't hit "data scarcity" exactly, but
  also won't have the breadth of MTG. The wiki is probably *most* of
  what's worth knowing.
- **The hardest unknown** is representing a mid-game board state to a
  model in a way it can reason about. Open research problem. Defer
  until the simpler pieces (deckbuild, banlist analysis, tier-list
  synthesis) are solid.

---

## When to revisit this doc

- After llm-wiki-anr has been in steady use for a month and the synthesis
  pipeline has run through ≥1 banlist refresh successfully.
- Before starting any meta-runner-2 work that adds new data sources —
  consider whether to add them to llm-wiki-anr first, then read from
  there.
- If you start thinking about the replay analyst.

---

## Source session

The full architecture conversation, including a worked example of the
deckbuilder-coach mode (answering "build a Flood the Market deck in the
current meta") with citations across 4 wiki pages and 2 YouTube sources,
is in the llm-wiki-anr session log on 2026-04-25. That session was the
proof-of-concept that the wiki already enables the coach mode without
any additional indexing infrastructure.
