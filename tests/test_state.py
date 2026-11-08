"""Tests for state persistence."""

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from vixguard.config import IST
from vixguard.rules import Regime
from vixguard.state import SCHEMA_VERSION, State


class StateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "state.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_file_is_a_clean_first_run(self):
        state = State.load(self.path)
        self.assertIsNone(state.vix)
        self.assertIsNone(state.regime())

    def test_round_trip(self):
        state = State()
        when = datetime(2026, 11, 9, 10, 30, tzinfo=IST)
        state.record(23.456, Regime(nifty_blocked=True, sensex_blocked=False), when)
        state.last_digest = "2026-11-09"
        state.save(self.path)

        loaded = State.load(self.path)
        self.assertEqual(loaded.vix, 23.46)
        self.assertEqual(loaded.regime(), Regime(True, False))
        self.assertEqual(loaded.updated_at, when.isoformat())
        self.assertEqual(loaded.last_digest, "2026-11-09")

    def test_saved_file_is_versioned(self):
        State().save(self.path)
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(raw["version"], SCHEMA_VERSION)

    def test_corrupt_file_is_ignored(self):
        self.path.write_text("{not json", encoding="utf-8")
        self.assertIsNone(State.load(self.path).regime())

    def test_wrong_version_is_ignored(self):
        self.path.write_text(
            json.dumps(
                {
                    "version": 999,
                    "vix": 25.0,
                    "nifty_blocked": True,
                    "sensex_blocked": False,
                }
            ),
            encoding="utf-8",
        )
        self.assertIsNone(State.load(self.path).regime())

    def test_partial_state_has_no_regime(self):
        self.path.write_text(
            json.dumps({"version": SCHEMA_VERSION, "vix": 25.0}),
            encoding="utf-8",
        )
        state = State.load(self.path)
        self.assertEqual(state.vix, 25.0)
        self.assertIsNone(state.regime())

    def test_save_creates_parent_directory(self):
        nested = Path(self.tmp.name) / "a" / "b" / "state.json"
        State().save(nested)
        self.assertTrue(nested.exists())


if __name__ == "__main__":
    unittest.main()
