"""Tests for the pure threshold logic."""

import unittest

from vixguard.rules import Change, Regime, Strategy, changes, regime_for


class RegimeTests(unittest.TestCase):
    def test_at_and_inside_thresholds_both_allowed(self):
        for vix in (11.0, 14.2, 22.0):
            with self.subTest(vix=vix):
                regime = regime_for(vix)
                self.assertFalse(regime.nifty_blocked)
                self.assertFalse(regime.sensex_blocked)

    def test_just_above_22_blocks_nifty_only(self):
        regime = regime_for(22.01)
        self.assertTrue(regime.nifty_blocked)
        self.assertFalse(regime.sensex_blocked)

    def test_just_below_11_blocks_sensex_only(self):
        regime = regime_for(10.99)
        self.assertFalse(regime.nifty_blocked)
        self.assertTrue(regime.sensex_blocked)

    def test_both_never_blocked_at_the_same_time(self):
        for tenth in range(1, 500):
            regime = regime_for(tenth / 10)
            self.assertFalse(
                regime.nifty_blocked and regime.sensex_blocked,
                msg=f"both blocked at VIX {tenth / 10}",
            )

    def test_is_blocked_helper(self):
        regime = Regime(nifty_blocked=True, sensex_blocked=False)
        self.assertTrue(regime.is_blocked(Strategy.NIFTY))
        self.assertFalse(regime.is_blocked(Strategy.SENSEX))

    def test_custom_thresholds(self):
        regime = regime_for(19.0, nifty_max=18.0, sensex_min=12.0)
        self.assertTrue(regime.nifty_blocked)
        self.assertFalse(regime.sensex_blocked)


class ChangeTests(unittest.TestCase):
    def test_first_run_never_alerts(self):
        self.assertEqual(changes(None, regime_for(25.0)), [])

    def test_no_change_is_silent(self):
        self.assertEqual(changes(regime_for(15.0), regime_for(16.0)), [])

    def test_nifty_stop(self):
        result = changes(regime_for(21.0), regime_for(23.0))
        self.assertEqual(
            result, [Change(Strategy.NIFTY, True, 22.0, "above")]
        )

    def test_nifty_resume(self):
        result = changes(regime_for(23.0), regime_for(21.9))
        self.assertEqual(
            result, [Change(Strategy.NIFTY, False, 22.0, "above")]
        )

    def test_sensex_stop(self):
        result = changes(regime_for(12.0), regime_for(10.5))
        self.assertEqual(
            result, [Change(Strategy.SENSEX, True, 11.0, "below")]
        )

    def test_sensex_resume(self):
        result = changes(regime_for(10.5), regime_for(11.2))
        self.assertEqual(
            result, [Change(Strategy.SENSEX, False, 11.0, "below")]
        )

    def test_gap_through_both_lines_reports_both(self):
        result = changes(regime_for(25.0), regime_for(9.0))
        self.assertEqual(len(result), 2)
        strategies = {change.strategy for change in result}
        self.assertEqual(strategies, {Strategy.NIFTY, Strategy.SENSEX})

    def test_custom_thresholds_are_reported(self):
        result = changes(
            regime_for(17.0, nifty_max=18.0),
            regime_for(19.0, nifty_max=18.0),
            nifty_max=18.0,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].threshold, 18.0)


if __name__ == "__main__":
    unittest.main()
