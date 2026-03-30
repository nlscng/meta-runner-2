"""
Quiz Agent v2 — CLI agent for Netrunner metagame learning.

Teaches meta concepts (archetypes, matchups, strategic principles) through
adaptive quizzing with SM-2 scheduling, session planning, and initiative.

Carries forward v1's quiz engine for card-level questions but wraps them
in concept-level learning with agent behaviors:
  - Memory: tracks concept understanding across sessions
  - Planning: opens each session with a personalized learning plan
  - Initiative: adds meta commentary connecting answers to strategic reasoning
"""

import random
import sqlite3
import json
import os
import re

from src.card_data import get_db, init_db, DB_PATH
from src.meta_concepts import (
    load_concepts_catalog,
    load_concept_memory,
    save_concept_memory,
    get_concept_state,
    sm2_update,
    select_next_concepts,
)
from src.review_index import load_reviews, search_reviews, get_reviews_for_card


class QuizAgent:
    """Netrunner meta learning agent with memory, planning, and initiative."""

    def __init__(self, db_path=DB_PATH):
        self.db = sqlite3.connect(db_path)
        self.db.row_factory = sqlite3.Row
        init_db(self.db)

        self.catalog = load_concepts_catalog()
        self.memory = load_concept_memory()
        self.reviews = load_reviews()

        self.current_question = None
        self.current_concept = None
        self.score = {"correct": 0, "wrong": 0}
        self.session_concepts = []
        self.session_concept_idx = 0
        self.session_tracker = []  # rolling window of recent answers
        self.session_started = False

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def start_session(self):
        """Plan and start a learning session. Returns the opening message."""
        self.session_started = True
        self.session_concepts = select_next_concepts(
            self.memory, self.catalog, target=4
        )
        self.session_concept_idx = 0

        lines = ["=" * 60]
        lines.append("🃏 Meta Runner v2 — Netrunner Meta Learning Agent")
        lines.append("=" * 60)

        if not self.session_concepts:
            lines.append("\nNo concepts to review — all caught up! Type 'quiz' for a random question.")
            return "\n".join(lines)

        lines.append("\n📋 **Session Plan:**")

        for cid in self.session_concepts:
            concept = self.catalog.get(cid, {})
            state = self.memory["concepts"].get(cid)
            name = concept.get("name", cid)

            if state is None:
                reason = "🆕 new concept"
            elif state.get("next_review") and state["next_review"] <= _today():
                reason = "📅 overdue for review"
            elif state.get("times_tested", 0) >= 3:
                acc = state["times_correct"] / state["times_tested"] * 100
                if acc < 60:
                    reason = f"⚠️ weak ({acc:.0f}% accuracy)"
                else:
                    reason = f"💪 reinforcement ({acc:.0f}%)"
            else:
                reason = "📖 continuing"

            lines.append(f"  • {name} — {reason}")

        lines.append("\nType 'quiz' to start, 'help' for commands.")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Question generation — concept-driven
    # ------------------------------------------------------------------

    def _select_concept(self):
        """Pick the next concept to ask about."""
        if self.session_concepts and self.session_concept_idx < len(self.session_concepts):
            cid = self.session_concepts[self.session_concept_idx]
            return cid
        # Fallback: random from catalog
        return random.choice(list(self.catalog.keys()))

    def _generate_question(self):
        """Generate a question for the current concept."""
        concept_id = self._select_concept()
        self.current_concept = concept_id
        concept = self.catalog.get(concept_id, {})

        sample_qs = concept.get("sample_questions", [])
        if sample_qs:
            question_text = random.choice(sample_qs)
        else:
            question_text = f"Explain the key idea behind: {concept.get('name', concept_id)}"

        return {
            "type": "concept",
            "concept_id": concept_id,
            "concept_name": concept.get("name", concept_id),
            "question": question_text,
            "category": concept.get("category", ""),
            "description": concept.get("description", ""),
        }

    # ------------------------------------------------------------------
    # Answer handling
    # ------------------------------------------------------------------

    def _evaluate_concept_answer(self, user_answer, question):
        """Concept answers are self-evaluated. Return None to prompt self-eval."""
        return None

    def _format_concept_result(self, grade, question):
        """Format result after user self-evaluates a concept answer."""
        concept_id = question["concept_id"]
        state = get_concept_state(self.memory, concept_id)
        new_state = sm2_update(state, grade)
        self.memory["concepts"][concept_id] = new_state
        save_concept_memory(self.memory)

        self.session_tracker.append({
            "concept_id": concept_id,
            "grade": grade,
        })

        lines = []
        if grade >= 4:
            lines.append("✅ Strong understanding!")
            self.score["correct"] += 1
        elif grade == 3:
            lines.append("📝 Partial — we'll revisit this.")
            self.score["correct"] += 1
        else:
            lines.append("🔄 Let's build this up. Here's the key idea:")
            lines.append(f"  💡 {question['description']}")
            self.score["wrong"] += 1

        # Initiative: add meta commentary from reviews
        commentary = self._get_meta_commentary(question)
        if commentary:
            lines.append(f"\n  📚 Community insight: {commentary}")

        # Initiative: mid-session course correction
        correction = self._check_course_correction()
        if correction:
            lines.append(f"\n  🔀 {correction}")

        # Advance to next concept
        if self.session_concepts and self.session_concept_idx < len(self.session_concepts):
            self.session_concept_idx += 1

        total = self.score["correct"] + self.score["wrong"]
        if total > 0:
            pct = self.score["correct"] / total * 100
            lines.append(f"\n  Score: {self.score['correct']}/{total} ({pct:.0f}%)")

        return "\n".join(lines)

    def _get_meta_commentary(self, question):
        """Search reviews for relevant meta context to add as commentary."""
        if not self.reviews:
            return None

        concept = self.catalog.get(question.get("concept_id", ""), {})
        search_terms = concept.get("name", "")
        results = search_reviews(self.reviews, search_terms, limit=1)
        if results:
            review = results[0]
            text = review.get("ruling", "")
            # Extract first sentence-ish chunk
            clean = re.sub(r'<[^>]+>', '', text)
            clean = re.sub(r'\s+', ' ', clean).strip()
            if len(clean) > 200:
                clean = clean[:200] + "..."
            if clean:
                return f'From review of {review.get("title", "?")}: "{clean}"'
        return None

    def _check_course_correction(self):
        """Check recent answers for patterns that warrant a course correction."""
        if len(self.session_tracker) < 3:
            return None

        recent = self.session_tracker[-3:]
        recent_grades = [a["grade"] for a in recent]

        # 3 wrong in a row
        if all(g < 3 for g in recent_grades):
            return "Three tough ones in a row. Let's shift to a concept you're more comfortable with."

        # 3 easy in a row
        if all(g >= 5 for g in recent_grades):
            return "You're cruising — let's push into something harder."

        return None

    # ------------------------------------------------------------------
    # Message handling
    # ------------------------------------------------------------------

    def handle_message(self, text):
        """Process a user message and return a response."""
        text = text.strip()
        cmd = text.lower()

        if cmd in ["quit", "exit", "q"]:
            return self._end_session()

        if cmd in ["help", "h", "?"]:
            return self._show_help()

        if cmd in ["score", "s"]:
            return self._show_score()

        if cmd in ["plan"]:
            return self.start_session()

        if cmd in ["concepts"]:
            return self._show_concepts()

        if cmd in ["quiz", "next", "n"]:
            self.current_question = self._generate_question()
            concept_name = self.current_question["concept_name"]
            category = self.current_question["category"]
            return (
                f"🃏 [{category}] **{concept_name}**\n\n"
                f"  {self.current_question['question']}\n\n"
                f"  (Answer in your own words, then self-evaluate with: 0=wrong, 3=hard, 4=good, 5=easy)"
            )

        # Self-evaluation grade
        if self.current_question and cmd in ["0", "1", "2", "3", "4", "5"]:
            grade = int(cmd)
            result = self._format_concept_result(grade, self.current_question)
            self.current_question = None
            return result

        # If there's a current question and input isn't a grade, treat as answer
        if self.current_question:
            return (
                f"📝 Your answer noted. Now self-evaluate:\n"
                f"  0 = didn't know  |  3 = hard but got it  |  4 = good  |  5 = easy\n"
                f"\n  💡 Key idea: {self.current_question['description']}"
            )

        # No current question, not a command — start a new question
        self.current_question = self._generate_question()
        concept_name = self.current_question["concept_name"]
        category = self.current_question["category"]
        return (
            f"🃏 [{category}] **{concept_name}**\n\n"
            f"  {self.current_question['question']}\n\n"
            f"  (Answer in your own words, then self-evaluate with: 0=wrong, 3=hard, 4=good, 5=easy)"
        )

    def _show_help(self):
        return (
            "🃏 **Meta Runner v2** — Netrunner Meta Learning Agent\n\n"
            "Commands:\n"
            "  quiz / next — Get a new concept question\n"
            "  plan       — Show/refresh the session plan\n"
            "  concepts   — List all meta concepts\n"
            "  score      — See your current score\n"
            "  help       — Show this message\n"
            "  quit       — End the session\n\n"
            "After answering a question, self-evaluate:\n"
            "  0 = didn't know  |  3 = hard  |  4 = good  |  5 = easy"
        )

    def _show_score(self):
        total = self.score["correct"] + self.score["wrong"]
        if total == 0:
            return "No questions answered yet. Type 'quiz' to start!"
        pct = self.score["correct"] / total * 100
        return f"Score: {self.score['correct']}/{total} ({pct:.0f}%)"

    def _show_concepts(self):
        lines = ["📚 **Meta Concepts Catalog:**\n"]
        by_category = {}
        for cid, concept in self.catalog.items():
            cat = concept.get("category", "other")
            by_category.setdefault(cat, []).append((cid, concept))

        for cat, concepts in sorted(by_category.items()):
            lines.append(f"**{cat}:**")
            for cid, concept in concepts:
                state = self.memory["concepts"].get(cid)
                if state and state.get("times_tested", 0) > 0:
                    acc = state["times_correct"] / state["times_tested"] * 100
                    status = f"{acc:.0f}% ({state['times_tested']}x)"
                else:
                    status = "untested"
                lines.append(f"  • {concept['name']} [{status}]")
            lines.append("")
        return "\n".join(lines)

    def _end_session(self):
        total = self.score["correct"] + self.score["wrong"]

        # Record session summary
        from datetime import datetime, timezone
        self.memory["sessions"].append({
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "concepts_explored": len(set(a["concept_id"] for a in self.session_tracker)),
            "questions_answered": total,
            "accuracy": self.score["correct"] / total if total > 0 else 0,
            "concepts_tested": [a["concept_id"] for a in self.session_tracker],
        })
        save_concept_memory(self.memory)

        return f"Thanks for studying! Final score: {self.score['correct']}/{total}. See you next time! 👋"


def _today():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def run_cli():
    """Run the meta learning agent as a CLI chatbot."""
    agent = QuizAgent()

    print(agent.start_session())
    print()

    while True:
        try:
            user_input = input("You> ").strip()
            if not user_input:
                continue
            response = agent.handle_message(user_input)
            print(f"\n{response}\n")
            if user_input.lower() in ["quit", "exit", "q"]:
                break
        except (KeyboardInterrupt, EOFError):
            print("\n👋 Bye!")
            break

    agent.db.close()


if __name__ == "__main__":
    run_cli()
