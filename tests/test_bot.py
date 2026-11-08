"""Integration tests for the bot's check flow (no network, no Telegram)."""

import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from vixguard.bot import VixGuardBot
from vixguard.config import IST, Settings
from vixguard.market import Quote
from vixguard.rules import Regime
from vixguard.state import State

NOW = datetime(2026, 11, 9, 10, 0, tzinfo=IST)


class BotFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = Settings(
            telegram_token="123456:test-token",
            chat_ids=(42,),
            state_file=Path(self.tmp.name) / "state.json",
            daily_digest=False,
        )
        self.bot = VixGuardBot(self.settings)
        self.sent = []
        self.bot.broadcast = self._record(self.sent)

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def _record(sent):
        def capture(text):
            sent.append(text)
            return 1

        return capture

    def test_first_reading_establishes_a_baseline(self):
        self.bot.process_quote(Quote(21.0, NOW, "test"), NOW)
        self.assertEqual(self.sent, [])
        self.assertEqual(
            State.load(self.settings.state_file).regime(), Regime(False, False)
        )

    def test_crossing_sends_one_alert_and_is_not_repeated(self):
        self.bot.process_quote(Quote(21.0, NOW, "test"), NOW)
        self.bot.process_quote(Quote(23.0, NOW, "test"), NOW)
        self.assertEqual(len(self.sent), 1)
        self.assertIn("STOP — NIFTY STBT", self.sent[0])

        saved = State.load(self.settings.state_file)
        self.assertEqual(saved.regime(), Regime(True, False))
        self.assertEqual(saved.vix, 23.0)

        # Still above the line: no duplicate alert.
        self.bot.process_quote(Quote(24.0, NOW, "test"), NOW)
        self.assertEqual(len(self.sent), 1)

    def test_resume_after_crossing_back(self):
        self.bot.process_quote(Quote(23.0, NOW, "test"), NOW)
        self.bot.process_quote(Quote(21.5, NOW, "test"), NOW)
        self.assertEqual(len(self.sent), 1)
        self.assertIn("BACK ON — NIFTY STBT", self.sent[0])

    def test_failed_delivery_is_retried(self):
        self.bot.process_quote(Quote(21.0, NOW, "test"), NOW)  # baseline
        self.bot.broadcast = lambda text: 0
        with self.assertLogs("vixguard.bot", level="ERROR"):
            self.bot.process_quote(Quote(23.0, NOW, "test"), NOW)
        self.assertEqual(
            State.load(self.settings.state_file).regime(), Regime(False, False)
        )

        self.bot.broadcast = self._record(self.sent)
        self.bot.process_quote(Quote(23.0, NOW, "test"), NOW)
        self.assertEqual(len(self.sent), 1)
        self.assertIn("STOP — NIFTY STBT", self.sent[0])

    def test_digest_is_sent_once_per_day(self):
        settings = replace(self.settings, daily_digest=True)
        bot = VixGuardBot(settings)
        sent = []
        bot.broadcast = self._record(sent)
        morning = NOW.replace(hour=9, minute=15)

        bot.process_quote(Quote(15.0, morning, "test"), morning)
        self.assertEqual(len(sent), 1)
        self.assertIn("VIX plan", sent[0])

        bot.process_quote(Quote(15.2, morning, "test"), morning)
        self.assertEqual(len(sent), 1)

    def test_stale_quote_does_not_send_todays_digest(self):
        settings = replace(self.settings, daily_digest=True)
        bot = VixGuardBot(settings)
        sent = []
        bot.broadcast = self._record(sent)
        yesterday = NOW - timedelta(days=1)

        bot.process_quote(Quote(15.0, yesterday, "test"), NOW)
        self.assertEqual(sent, [])


if __name__ == "__main__":
    unittest.main()
