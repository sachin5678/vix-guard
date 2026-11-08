"""Tests for Yahoo payload parsing (offline fixtures)."""

import unittest
from datetime import datetime, timedelta

from vixguard.config import IST
from vixguard.market import DataUnavailable, Quote, parse_yahoo_payload


def payload(closes, timestamps=None, meta=None):
    return {
        "chart": {
            "result": [
                {
                    "meta": meta or {},
                    "timestamp": timestamps or list(range(1, len(closes) + 1)),
                    "indicators": {"quote": [{"close": closes}]},
                }
            ],
            "error": None,
        }
    }


class ParseTests(unittest.TestCase):
    def test_uses_last_non_null_intraday_close(self):
        quote = parse_yahoo_payload(payload([15.0, None, 18.436]))
        self.assertEqual(quote.value, 18.44)
        self.assertEqual(quote.source, "Yahoo Finance")
        self.assertIsNotNone(quote.as_of)

    def test_falls_back_to_meta_price_when_bars_are_empty(self):
        quote = parse_yahoo_payload(
            payload([], meta={"regularMarketPrice": 18.43, "regularMarketTime": 1794132784})
        )
        self.assertEqual(quote.value, 18.43)
        self.assertIsNotNone(quote.as_of)

    def test_error_in_chart_is_reported(self):
        with self.assertRaises(DataUnavailable):
            parse_yahoo_payload(
                {"chart": {"result": None, "error": {"description": "Not found"}}}
            )

    def test_empty_result_is_reported(self):
        with self.assertRaises(DataUnavailable):
            parse_yahoo_payload({"chart": {"result": [], "error": None}})

    def test_implausible_value_is_rejected(self):
        with self.assertRaises(DataUnavailable):
            parse_yahoo_payload(payload([9999.0]))

    def test_non_numeric_meta_price_is_rejected(self):
        with self.assertRaises(DataUnavailable):
            parse_yahoo_payload(payload([], meta={"regularMarketPrice": "oops"}))

    def test_garbage_is_rejected(self):
        with self.assertRaises(DataUnavailable):
            parse_yahoo_payload([])


class QuoteAgeTests(unittest.TestCase):
    def test_staleness(self):
        now = datetime(2026, 11, 9, 10, 0, tzinfo=IST)
        old = Quote(18.0, now - timedelta(hours=5), "test")
        fresh = Quote(18.0, now - timedelta(minutes=5), "test")
        unknown = Quote(18.0, None, "test")
        self.assertTrue(old.is_stale(timedelta(hours=4), now))
        self.assertFalse(fresh.is_stale(timedelta(hours=4), now))
        self.assertFalse(unknown.is_stale(timedelta(hours=4), now))


if __name__ == "__main__":
    unittest.main()
