"""
Web UI for Meta Runner v2 — Gradio-based browser interface.

Provides a chat interface for the meta learning agent with a side panel
for displaying Netrunner card images and deck lists.

Run with: uv run python -m src.web_ui
"""

import html as html_mod
import gradio as gr
import sqlite3
import json

from src.card_data import get_db, init_db, DB_PATH
from src.image_cache import get_image_cache
from src.meta_concepts import (
    load_concepts_catalog,
    load_concept_memory,
    save_concept_memory,
    get_concept_state,
    sm2_update,
    select_next_concepts,
    DEFAULT_CONCEPTS,
)
from src.review_index import load_reviews, search_reviews

NRDB_CARD_URL = "https://netrunnerdb.com/en/card/{code}"


class WebAgent:
    """Quiz agent adapted for the Gradio web interface.

    Manages state per session: concept memory, session plan, current question,
    and score. Produces (response_text, card_html) tuples so the UI can
    update both the chat and the card display panel.
    """

    def __init__(self):
        self.db = get_db()
        init_db(self.db)
        self.catalog = load_concepts_catalog()
        self.memory = load_concept_memory()
        self.reviews = load_reviews()
        self.image_cache = get_image_cache()
        self.current_question = None
        self.current_concept = None
        self.score = {"correct": 0, "wrong": 0}
        self.session_concepts = []
        self.session_concept_idx = 0
        self.session_tracker = []
        self._awaiting_grade = False

    # ------------------------------------------------------------------
    # Card display helpers
    # ------------------------------------------------------------------

    def _card_html(self, code):
        """Render a single card as HTML with image and link."""
        row = self.db.execute(
            "SELECT title, faction_code, type_code, stripped_text, cost, strength "
            "FROM cards WHERE code = ?",
            (code,),
        ).fetchone()
        if not row:
            return ""

        img_url = self.image_cache.get_url(code)
        card_url = NRDB_CARD_URL.format(code=code)
        title = html_mod.escape(row["title"])
        faction = html_mod.escape(row["faction_code"] or "")
        card_type = html_mod.escape(row["type_code"] or "")
        text = html_mod.escape(row["stripped_text"] or "")
        cost = row["cost"]
        strength = row["strength"]

        stats = []
        if cost is not None:
            stats.append(f"Cost: {cost}")
        if strength is not None:
            stats.append(f"Str: {strength}")
        stats_str = " · ".join(stats)

        return f"""
        <div style="text-align:center; padding:10px;">
            <a href="{card_url}" target="_blank">
                <img src="{img_url}" alt="{title}"
                     style="max-width:300px; border-radius:10px;
                            box-shadow:0 2px 8px rgba(0,0,0,0.3);" />
            </a>
            <div style="margin-top:8px;">
                <strong>{title}</strong><br/>
                <span style="color:#888;">{faction} · {card_type}</span><br/>
                <span style="color:#aaa; font-size:0.9em;">{stats_str}</span>
            </div>
        </div>
        """

    def _deck_html(self, card_codes_with_copies):
        """Render a deck list as an HTML table with card images on hover."""
        if not card_codes_with_copies:
            return ""

        rows_html = ""
        for code, copies in sorted(card_codes_with_copies.items()):
            card = self.db.execute(
                "SELECT title, type_code, faction_code FROM cards WHERE code = ?",
                (code,),
            ).fetchone()
            if not card:
                continue
            img_url = self.image_cache.get_url(code)
            card_url = NRDB_CARD_URL.format(code=code)
            card_title = html_mod.escape(card["title"])
            card_type = html_mod.escape(card["type_code"] or "")
            card_faction = html_mod.escape(card["faction_code"] or "")
            rows_html += f"""
            <tr>
                <td style="padding:4px 8px;">{copies}x</td>
                <td style="padding:4px 8px;">
                    <a href="{card_url}" target="_blank"
                       style="color:#4fc3f7; text-decoration:none;">{card_title}</a>
                </td>
                <td style="padding:4px 8px; color:#888;">{card_type}</td>
                <td style="padding:4px 8px; color:#888;">{card_faction}</td>
            </tr>"""

        return f"""
        <table style="width:100%; border-collapse:collapse; font-size:0.9em;">
            <thead>
                <tr style="border-bottom:1px solid #444;">
                    <th style="padding:4px 8px; text-align:left;">#</th>
                    <th style="padding:4px 8px; text-align:left;">Card</th>
                    <th style="padding:4px 8px; text-align:left;">Type</th>
                    <th style="padding:4px 8px; text-align:left;">Faction</th>
                </tr>
            </thead>
            <tbody>{rows_html}</tbody>
        </table>
        """

    def _concept_key_cards_html(self, concept_id):
        """Show key cards for the current concept."""
        concept = self.catalog.get(concept_id, {})
        key_cards = concept.get("key_cards", [])
        if not key_cards:
            return "<p style='color:#888; text-align:center;'>No key cards for this concept yet.</p>"
        html_parts = [self._card_html(code) for code in key_cards[:3]]
        return "\n".join(html_parts)

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def start_session(self):
        """Plan the session and return (message, card_html)."""
        self.session_concepts = select_next_concepts(
            self.memory, self.catalog, target=4
        )
        self.session_concept_idx = 0

        lines = ["📋 **Session Plan:**\n"]
        if not self.session_concepts:
            lines.append("All caught up! Type `quiz` for a random question.")
            return "\n".join(lines), ""

        today = _today()
        for cid in self.session_concepts:
            concept = self.catalog.get(cid, {})
            state = self.memory["concepts"].get(cid)
            name = concept.get("name", cid)

            if state is None:
                reason = "🆕 new"
            elif state.get("next_review") and state["next_review"] <= today:
                reason = "📅 overdue"
            elif state.get("times_tested", 0) >= 3:
                acc = state["times_correct"] / state["times_tested"] * 100
                reason = f"⚠️ weak ({acc:.0f}%)" if acc < 60 else f"💪 reinforce ({acc:.0f}%)"
            else:
                reason = "📖 continuing"

            lines.append(f"• **{name}** — {reason}")

        lines.append("\nType **quiz** to start!")
        return "\n".join(lines), ""

    # ------------------------------------------------------------------
    # Message handler
    # ------------------------------------------------------------------

    def respond(self, user_msg, chat_history):
        """Process user message. Returns (chat_history, card_html)."""
        text = user_msg.strip()
        cmd = text.lower()

        if cmd in ["quit", "exit", "q"]:
            reply, card_html = self._end_session()
        elif cmd in ["help", "h", "?"]:
            reply = (
                "🃏 **Meta Runner v2**\n\n"
                "• **quiz / next** — New concept question\n"
                "• **plan** — Show session plan\n"
                "• **concepts** — List all concepts with progress\n"
                "• **card `<name>`** — Show a card image\n"
                "• **score** — Current score\n"
                "• **help** — This message\n"
                "• **quit** — End session"
            )
            card_html = ""
        elif cmd in ["score", "s"]:
            reply = self._show_score()
            card_html = ""
        elif cmd in ["plan"]:
            reply, card_html = self.start_session()
        elif cmd in ["concepts"]:
            reply = self._show_concepts()
            card_html = ""
        elif cmd.startswith("card "):
            reply, card_html = self._show_card(text[5:].strip())
        elif cmd in ["quiz", "next", "n"]:
            reply, card_html = self._new_question()
        elif self._awaiting_grade and cmd in ["0", "1", "2", "3", "4", "5"]:
            reply, card_html = self._process_grade(int(cmd))
        elif self.current_question and not self._awaiting_grade:
            # User gave a free-text answer — show key idea and ask for grade
            self._awaiting_grade = True
            reply = (
                f"📝 Your answer noted. Now self-evaluate:\n\n"
                f"**0** = didn't know · **3** = hard · **4** = good · **5** = easy\n\n"
                f"💡 Key idea: {self.current_question['description']}"
            )
            card_html = self._concept_key_cards_html(self.current_question["concept_id"])
        else:
            reply, card_html = self._new_question()

        chat_history = chat_history + [
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": reply},
        ]
        return chat_history, card_html

    def _new_question(self):
        """Generate a new concept question."""
        concept_id = self._select_concept()
        if concept_id is None:
            return "No concepts available. Run `uv run python -m src.card_data` to set up.", ""
        self.current_concept = concept_id
        concept = self.catalog.get(concept_id, {})

        import random
        sample_qs = concept.get("sample_questions", [])
        question_text = random.choice(sample_qs) if sample_qs else f"Explain: {concept.get('name', concept_id)}"

        self.current_question = {
            "type": "concept",
            "concept_id": concept_id,
            "concept_name": concept.get("name", concept_id),
            "question": question_text,
            "category": concept.get("category", ""),
            "description": concept.get("description", ""),
        }
        self._awaiting_grade = False

        reply = (
            f"🃏 **[{self.current_question['category']}] {self.current_question['concept_name']}**\n\n"
            f"{self.current_question['question']}\n\n"
            f"*Answer in your own words, then self-evaluate (0-5).*"
        )
        card_html = self._concept_key_cards_html(concept_id)
        return reply, card_html

    def _process_grade(self, grade):
        """Process self-evaluation grade and update SM-2."""
        question = self.current_question
        concept_id = question["concept_id"]

        state = get_concept_state(self.memory, concept_id)
        new_state = sm2_update(state, grade)
        self.memory["concepts"][concept_id] = new_state
        save_concept_memory(self.memory)

        self.session_tracker.append({"concept_id": concept_id, "grade": grade})

        lines = []
        if grade >= 4:
            lines.append("✅ Strong understanding!")
            self.score["correct"] += 1
        elif grade == 3:
            lines.append("📝 Partial — we'll revisit this.")
            self.score["correct"] += 1
        else:
            lines.append("🔄 Let's build this up. Here's the key idea:")
            lines.append(f"\n💡 {question['description']}")
            self.score["wrong"] += 1

        # Meta commentary from reviews
        commentary = self._get_meta_commentary(question)
        if commentary:
            lines.append(f"\n📚 *{commentary}*")

        # Course correction
        correction = self._check_course_correction()
        if correction:
            lines.append(f"\n🔀 {correction}")

        # Advance concept
        if self.session_concepts and self.session_concept_idx < len(self.session_concepts):
            self.session_concept_idx += 1

        total = self.score["correct"] + self.score["wrong"]
        if total > 0:
            pct = self.score["correct"] / total * 100
            lines.append(f"\nScore: {self.score['correct']}/{total} ({pct:.0f}%)")

        self.current_question = None
        self._awaiting_grade = False
        return "\n".join(lines), ""

    def _select_concept(self):
        import random
        if self.session_concepts and self.session_concept_idx < len(self.session_concepts):
            return self.session_concepts[self.session_concept_idx]
        if not self.catalog:
            return None
        return random.choice(list(self.catalog.keys()))

    def _get_meta_commentary(self, question):
        if not self.reviews:
            return None
        import re
        concept = self.catalog.get(question.get("concept_id", ""), {})
        results = search_reviews(self.reviews, concept.get("name", ""), limit=1)
        if results:
            review = results[0]
            text = review.get("ruling", "")
            clean = re.sub(r'<[^>]+>', '', text)
            clean = re.sub(r'\s+', ' ', clean).strip()
            if len(clean) > 200:
                clean = clean[:200] + "..."
            if clean:
                return f'Community on {review.get("title", "?")}: "{clean}"'
        return None

    def _check_course_correction(self):
        if len(self.session_tracker) < 3:
            return None
        recent = [a["grade"] for a in self.session_tracker[-3:]]
        if all(g < 3 for g in recent):
            return "Three tough ones in a row — shifting to something more comfortable."
        if all(g >= 5 for g in recent):
            return "You're cruising — let's push harder."
        return None

    def _show_card(self, query):
        """Look up a card by name and display it."""
        row = self.db.execute(
            "SELECT code FROM cards WHERE LOWER(title) LIKE ? LIMIT 1",
            (f"%{query.lower()}%",),
        ).fetchone()
        if not row:
            return f"No card found matching '{query}'.", ""
        code = row["code"]
        card = self.db.execute("SELECT title FROM cards WHERE code = ?", (code,)).fetchone()
        return f"Showing **{card['title']}**", self._card_html(code)

    def _show_score(self):
        total = self.score["correct"] + self.score["wrong"]
        if total == 0:
            return "No questions answered yet. Type **quiz** to start!"
        pct = self.score["correct"] / total * 100
        return f"Score: {self.score['correct']}/{total} ({pct:.0f}%)"

    def _show_concepts(self):
        lines = ["📚 **Meta Concepts:**\n"]
        by_cat = {}
        for cid, concept in self.catalog.items():
            cat = concept.get("category", "other")
            by_cat.setdefault(cat, []).append((cid, concept))

        for cat, concepts in sorted(by_cat.items()):
            lines.append(f"**{cat}:**")
            for cid, concept in concepts:
                state = self.memory["concepts"].get(cid)
                if state and state.get("times_tested", 0) > 0:
                    acc = state["times_correct"] / state["times_tested"] * 100
                    status = f"{acc:.0f}% ({state['times_tested']}x)"
                else:
                    status = "untested"
                lines.append(f"• {concept['name']} [{status}]")
            lines.append("")
        return "\n".join(lines)

    def _end_session(self):
        total = self.score["correct"] + self.score["wrong"]
        from datetime import datetime, timezone
        self.memory["sessions"].append({
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "concepts_explored": len(set(a["concept_id"] for a in self.session_tracker)),
            "questions_answered": total,
            "accuracy": self.score["correct"] / total if total > 0 else 0,
        })
        save_concept_memory(self.memory)
        return f"Thanks for studying! Final score: {self.score['correct']}/{total}. 👋", ""


def _today():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Gradio UI
# ---------------------------------------------------------------------------

def build_ui():
    """Build and return the Gradio Blocks application."""
    agent = WebAgent()

    with gr.Blocks(
        title="Meta Runner v2",
    ) as app:
        gr.Markdown("# 🃏 Meta Runner v2\n*Netrunner metagame learning agent*")

        with gr.Row():
            with gr.Column(scale=3):
                chatbot = gr.Chatbot(
                    label="Meta Runner",
                    height=500,
                )
                msg_input = gr.Textbox(
                    placeholder="Type quiz, help, card <name>, or answer a question...",
                    show_label=False,
                    container=False,
                )

            with gr.Column(scale=1, elem_classes="card-panel"):
                gr.Markdown("### 🎴 Card Display")
                card_display = gr.HTML(
                    value="<p style='color:#888; text-align:center; padding:40px;'>"
                    "Card images appear here when relevant.</p>"
                )

        # Wire up the chat
        def on_submit(user_msg, history):
            if not user_msg.strip():
                return history, "", card_display.value
            history, card_html = agent.respond(user_msg, history or [])
            return history, "", card_html

        msg_input.submit(
            fn=on_submit,
            inputs=[msg_input, chatbot],
            outputs=[chatbot, msg_input, card_display],
        )

        # Auto-start session on load
        def on_load():
            plan_text, _ = agent.start_session()
            return [{"role": "assistant", "content": f"🃏 **Welcome to Meta Runner v2!**\n\n{plan_text}"}]

        app.load(fn=on_load, outputs=[chatbot])

    return app


def main():
    app = build_ui()
    cache_dir = str(get_image_cache().images_dir)
    app.launch(server_name="0.0.0.0", server_port=7860,
               allowed_paths=[cache_dir],
               theme=gr.themes.Soft(primary_hue="blue"))


if __name__ == "__main__":
    main()
