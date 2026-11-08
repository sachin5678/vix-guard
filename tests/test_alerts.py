"""Tests for message rendering (Telegram HTML and plain text)."""

import unittest
from datetime import datetime

from vixguard.alerts import (
    as_of_line,
    render_change,
    render_digest,
    render_feed_down,
    render_feed_up,
    render_snapshot,
    status_plain,
    strip_html,
)
from vixguard.config import IST, Settings
from vixguard.market import Quote
from vixguard.rules import Change, Regime, Strategy

WHEN = datetime(2026, 11, 9, 10, 35, tzinfo=IST)
QUOTE = Quote(value=23.41, as_of=WHEN, source="Yahoo Finance")
SETTINGS = Settings(nifty_max_vix=22.0, sensex_min_vix=11.0)


class ChangeMessageTests(unittest.TestCase):
    def test_nifty_stop_message(self):
        change = Change(Strategy.NIFTY, True, 22.0, "above")
        text = render_change(change, QUOTE, Regime(True, False), SETTINGS)
        self.assertIn("STOP — NIFTY STBT", text)
        self.assertIn("23.41", text)
        self.assertIn("above 22", text)
        self.assertIn("no overnight NIFTY shorts", text)
        self.assertIn("NIFTY STBT — ❌ <b>OFF</b>", text)
        self.assertIn("SENSEX STBT — ✅ <b>ON</b>", text)

    def test_nifty_resume_message(self):
        quote = Quote(value=21.4, as_of=WHEN, source="Yahoo Finance")
        change = Change(Strategy.NIFTY, False, 22.0, "above")
        text = render_change(change, quote, Regime(False, False), SETTINGS)
        self.assertIn("BACK ON — NIFTY STBT", text)
        self.assertIn("at or below 22", text)
        self.assertIn("NIFTY STBT — ✅ <b>ON</b>", text)

    def test_sensex_stop_message(self):
        quote = Quote(value=10.86, as_of=WHEN, source="Yahoo Finance")
        change = Change(Strategy.SENSEX, True, 11.0, "below")
        text = render_change(change, quote, Regime(False, True), SETTINGS)
        self.assertIn("STOP — SENSEX STBT", text)
        self.assertIn("10.86", text)
        self.assertIn("below 11", text)
        self.assertIn("no overnight SENSEX shorts", text)
        self.assertIn("SENSEX STBT — ❌ <b>OFF</b>", text)

    def test_sensex_resume_message(self):
        quote = Quote(value=11.3, as_of=WHEN, source="Yahoo Finance")
        change = Change(Strategy.SENSEX, False, 11.0, "below")
        text = render_change(change, quote, Regime(False, False), SETTINGS)
        self.assertIn("BACK ON — SENSEX STBT", text)
        self.assertIn("at or above 11", text)

    def test_strip_html_is_readable(self):
        change = Change(Strategy.NIFTY, True, 22.0, "above")
        text = render_change(change, QUOTE, Regime(True, False), SETTINGS)
        plain = strip_html(text)
        self.assertNotIn("<b>", plain)
        self.assertNotIn("</b>", plain)
        self.assertIn("STOP — NIFTY STBT", plain)


class StatusMessageTests(unittest.TestCase):
    def test_snapshot(self):
        text = render_snapshot(QUOTE, Regime(True, False), SETTINGS)
        self.assertIn("VIX Guard is online", text)
        self.assertIn("23.41", text)
        self.assertIn("between 11 and 22", text)

    def test_digest_has_day_and_value(self):
        text = render_digest(QUOTE, Regime(True, False), WHEN, SETTINGS)
        self.assertIn("Mon 09 Nov", text)
        self.assertIn("23.41", text)

    def test_feed_messages(self):
        self.assertIn("VIX feed problem", render_feed_down(WHEN))
        self.assertIn("never", render_feed_down(None))
        self.assertIn("VIX feed back", render_feed_up(QUOTE))

    def test_plain_status(self):
        text = status_plain(QUOTE, Regime(False, False), SETTINGS)
        self.assertIn("NIFTY STBT  : ON", text)
        self.assertIn("SENSEX STBT : ON", text)
        self.assertIn("between 11 and 22", text)

    def test_as_of_line(self):
        self.assertIn("09 Nov 2026, 10:35 IST", as_of_line(QUOTE))
        no_time = Quote(value=18.0, as_of=None, source="Yahoo Finance")
        self.assertEqual(as_of_line(no_time), "Source: Yahoo Finance")


if __name__ == "__main__":
    unittest.main()
