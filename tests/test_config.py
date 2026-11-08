"""Tests for .env parsing and validation."""

import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from vixguard.config import ConfigError, IST, Settings

MISSING = Path("definitely-not-a-real-env-file.env")


class ConfigTests(unittest.TestCase):
    def test_defaults(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            settings = Settings.from_env(MISSING)
        self.assertEqual(settings.nifty_max_vix, 22.0)
        self.assertEqual(settings.sensex_min_vix, 11.0)
        self.assertEqual(settings.poll_seconds, 300)
        self.assertEqual(settings.chat_ids, ())
        self.assertTrue(settings.daily_digest)

    def test_chat_ids_allow_commas_spaces_and_negative_ids(self):
        env = {"TELEGRAM_CHAT_ID": "123, -100456 789"}
        with mock.patch.dict(os.environ, env, clear=True):
            settings = Settings.from_env(MISSING)
        self.assertEqual(settings.chat_ids, (123, -100456, 789))

    def test_duplicate_chat_ids_are_removed(self):
        env = {"TELEGRAM_CHAT_ID": "5,5,6"}
        with mock.patch.dict(os.environ, env, clear=True):
            settings = Settings.from_env(MISSING)
        self.assertEqual(settings.chat_ids, (5, 6))

    def test_bad_chat_id_is_rejected(self):
        env = {"TELEGRAM_CHAT_ID": "hello"}
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ConfigError):
                Settings.from_env(MISSING)

    def test_threshold_order_is_enforced(self):
        env = {"NIFTY_MAX_VIX": "10", "SENSEX_MIN_VIX": "11"}
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ConfigError):
                Settings.from_env(MISSING)

    def test_bad_number_is_rejected(self):
        with mock.patch.dict(os.environ, {"NIFTY_MAX_VIX": "abc"}, clear=True):
            with self.assertRaises(ConfigError):
                Settings.from_env(MISSING)

    def test_too_fast_polling_is_rejected(self):
        with mock.patch.dict(os.environ, {"POLL_SECONDS": "1"}, clear=True):
            with self.assertRaises(ConfigError):
                Settings.from_env(MISSING)

    def test_bad_market_window_is_rejected(self):
        env = {"MARKET_OPEN": "16:00", "MARKET_CLOSE": "09:00"}
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ConfigError):
                Settings.from_env(MISSING)

    def test_env_file_is_loaded_without_overriding_real_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text(
                "NIFTY_MAX_VIX=25\nPOLL_SECONDS=120\nTELEGRAM_CHAT_ID=42\n",
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {"POLL_SECONDS": "60"}, clear=True):
                settings = Settings.from_env(env_file)
        self.assertEqual(settings.nifty_max_vix, 25.0)
        self.assertEqual(settings.poll_seconds, 60)
        self.assertEqual(settings.chat_ids, (42,))

    def test_market_time_window(self):
        settings = Settings()
        monday = datetime(2026, 11, 9, tzinfo=IST)
        self.assertFalse(settings.is_market_time(monday.replace(hour=9, minute=4)))
        self.assertTrue(settings.is_market_time(monday.replace(hour=9, minute=5)))
        self.assertTrue(settings.is_market_time(monday.replace(hour=15, minute=40)))
        self.assertFalse(settings.is_market_time(monday.replace(hour=15, minute=41)))
        saturday = datetime(2026, 11, 7, 10, 0, tzinfo=IST)
        self.assertFalse(settings.is_market_time(saturday))

    def test_require_telegram_lists_missing_keys(self):
        with self.assertRaises(ConfigError) as ctx:
            Settings().require_telegram()
        self.assertIn("TELEGRAM_BOT_TOKEN", str(ctx.exception))
        self.assertIn("TELEGRAM_CHAT_ID", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
