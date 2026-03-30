"""Tests for src/meta_concepts.py — SM-2 scheduling, concept selection, catalog/memory I/O."""

import json
import os
import tempfile

import pytest

from src.meta_concepts import (
    sm2_update,
    _init_concept_state,
    select_next_concepts,
    load_concepts_catalog,
    save_concepts_catalog,
    load_concept_memory,
    save_concept_memory,
    DEFAULT_CONCEPTS,
)


class TestSM2Update:
    def test_correct_first_time_sets_interval_1(self):
        state = _init_concept_state()
        new = sm2_update(state, grade=4)
        assert new["interval"] == 1
        assert new["n"] == 1
        assert new["times_tested"] == 1
        assert new["times_correct"] == 1

    def test_correct_second_time_sets_interval_6(self):
        state = _init_concept_state()
        state = sm2_update(state, grade=4)
        state = sm2_update(state, grade=4)
        assert state["interval"] == 6
        assert state["n"] == 2

    def test_correct_third_time_uses_ef_multiplier(self):
        state = _init_concept_state()
        state = sm2_update(state, grade=4)
        state = sm2_update(state, grade=4)
        state = sm2_update(state, grade=4)
        assert state["n"] == 3
        assert state["interval"] == round(6 * state["ef"])

    def test_wrong_resets_n_and_interval(self):
        state = _init_concept_state()
        state = sm2_update(state, grade=4)
        state = sm2_update(state, grade=4)
        assert state["n"] == 2
        state = sm2_update(state, grade=0)
        assert state["n"] == 0
        assert state["interval"] == 1

    def test_wrong_does_not_increment_correct(self):
        state = _init_concept_state()
        state = sm2_update(state, grade=0)
        assert state["times_tested"] == 1
        assert state["times_correct"] == 0

    def test_ef_decreases_on_hard(self):
        state = _init_concept_state()
        original_ef = state["ef"]
        state = sm2_update(state, grade=3)
        assert state["ef"] < original_ef

    def test_ef_increases_on_easy(self):
        state = _init_concept_state()
        original_ef = state["ef"]
        state = sm2_update(state, grade=5)
        assert state["ef"] > original_ef

    def test_ef_never_below_1_3(self):
        state = _init_concept_state()
        for _ in range(20):
            state = sm2_update(state, grade=0)
        assert state["ef"] >= 1.3

    def test_sets_last_seen_and_next_review(self):
        state = _init_concept_state()
        state = sm2_update(state, grade=4)
        assert state["last_seen"] is not None
        assert state["next_review"] is not None

    def test_does_not_mutate_input(self):
        state = _init_concept_state()
        original = dict(state)
        sm2_update(state, grade=4)
        assert state == original


class TestSelectNextConcepts:
    def test_untested_concepts_selected(self, sample_concepts, empty_memory):
        selected = select_next_concepts(empty_memory, sample_concepts, target=3)
        assert len(selected) == 3
        assert set(selected) == set(sample_concepts.keys())

    def test_respects_target_limit(self, sample_concepts, empty_memory):
        selected = select_next_concepts(empty_memory, sample_concepts, target=1)
        assert len(selected) == 1

    def test_overdue_concepts_prioritized(self, sample_concepts, empty_memory):
        empty_memory["concepts"]["glacier"] = {
            "times_tested": 5,
            "times_correct": 4,
            "ef": 2.5,
            "interval": 1,
            "n": 3,
            "last_seen": "2020-01-01",
            "next_review": "2020-01-02",  # long overdue
        }
        selected = select_next_concepts(empty_memory, sample_concepts, target=1)
        assert selected[0] == "glacier"

    def test_weak_concepts_selected_over_reinforcement(self, sample_concepts, empty_memory):
        # Make glacier weak
        empty_memory["concepts"]["glacier"] = {
            "times_tested": 10,
            "times_correct": 2,  # 20% accuracy
            "ef": 1.5,
            "interval": 30,
            "n": 5,
            "last_seen": "2026-03-28",
            "next_review": "2026-04-28",  # not overdue
        }
        # Make rush strong
        empty_memory["concepts"]["rush"] = {
            "times_tested": 10,
            "times_correct": 9,
            "ef": 2.8,
            "interval": 30,
            "n": 5,
            "last_seen": "2026-03-28",
            "next_review": "2026-04-28",
        }
        selected = select_next_concepts(empty_memory, sample_concepts, target=3)
        # glacier (weak) should come before rush (strong reinforcement)
        glacier_idx = selected.index("glacier") if "glacier" in selected else 99
        rush_idx = selected.index("rush") if "rush" in selected else 99
        assert glacier_idx < rush_idx


class TestCatalogIO:
    def test_default_concepts_not_empty(self):
        assert len(DEFAULT_CONCEPTS) > 0

    def test_save_and_load_catalog(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            path = f.name
        try:
            catalog = {"test-concept": {"name": "Test", "side": "corp"}}
            save_concepts_catalog(catalog, path)
            loaded = load_concepts_catalog(path)
            assert loaded == catalog
        finally:
            os.unlink(path)

    def test_load_missing_file_returns_defaults(self):
        loaded = load_concepts_catalog("/tmp/nonexistent_catalog_xyz.json")
        assert loaded == DEFAULT_CONCEPTS


class TestMemoryIO:
    def test_save_and_load_memory(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            path = f.name
        try:
            memory = {"concepts": {"test": {"ef": 2.5}}, "sessions": [], "version": 2}
            save_concept_memory(memory, path)
            loaded = load_concept_memory(path)
            assert loaded == memory
        finally:
            os.unlink(path)

    def test_load_missing_file_returns_empty(self):
        loaded = load_concept_memory("/tmp/nonexistent_memory_xyz.json")
        assert loaded["concepts"] == {}
        assert loaded["sessions"] == []
