import json
import unittest
from unittest.mock import mock_open, patch

import numpy as np
import pandas as pd

import backtester
import runner_incremental_backtests as incremental


class PandasCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.dates = pd.date_range("2024-01-01", periods=3, tz="UTC", name="date")

    def test_zero_portfolio_branch_clears_shares(self):
        allocations = pd.DataFrame({"A": [1.0]}, index=self.dates[:1])
        prices = pd.DataFrame({"A": [10.0, 0.0, 20.0]}, index=self.dates)

        with patch("builtins.print"):
            values, _ = backtester.scenario(allocations, prices, 100.0, "test")

        # The rebound must not restore shares cleared on the zero-price day.
        self.assertEqual(values.tolist(), [100.0, 100.0, 100.0])

    def test_ordinary_scenario_preserves_results_and_inputs(self):
        allocations = pd.DataFrame({"A": [1.0]}, index=self.dates[:1])
        prices = pd.DataFrame({"A": [10.0, 11.0, 12.0]}, index=self.dates)
        original_allocations = allocations.copy()
        original_prices = prices.copy()

        with patch("builtins.print"):
            values, _ = backtester.scenario(allocations, prices, 100.0, "test")

        self.assertEqual(values.tolist(), [100.0, 110.0, 120.0])
        pd.testing.assert_frame_equal(allocations, original_allocations)
        pd.testing.assert_frame_equal(prices, original_prices)

    def _allocations(self, prices):
        allocations = pd.DataFrame(
            0.5, index=self.dates[:1], columns=prices.columns
        )
        return allocations, allocations, allocations

    def _full_run_prices(self, prices):
        with (
            patch("builtins.print"),
            patch.object(backtester, "prepare_allocations", return_value=self._allocations(prices)),
            patch.object(backtester, "load_prices", return_value=prices.copy()),
            patch.object(backtester, "scenario", return_value=(None, {})) as scenario,
        ):
            backtester.backtest_hedge_fund("123", download_data=False)
        return [call.args[1] for call in scenario.call_args_list]

    def _incremental_run_prices(self, prices):
        existing_values = pd.DataFrame(
            100.0,
            index=self.dates[:2],
            columns=["PortfolioValue_copy", "PortfolioValue_copy_scaled", "PortfolioValue_fund"],
        )
        funds = json.dumps({"0000000123": {"name": "Test fund"}})
        with (
            patch("builtins.print"),
            patch.object(incremental, "open", mock_open(read_data=funds), create=True),
            patch.object(incremental, "load_allocations_meta", return_value={}),
            patch.object(incremental.os.path, "exists", return_value=True),
            patch.object(pd, "read_csv", return_value=existing_values),
            patch.object(incremental, "prepare_allocations", return_value=self._allocations(prices)),
            patch.object(incremental, "get_ticker_data"),
            patch.object(incremental, "load_prices", return_value=prices.copy()),
            patch.object(incremental, "scenario", return_value=(None, {})) as scenario,
            patch.object(pd.DataFrame, "to_csv"),
            patch.object(incremental, "update_fund_data"),
            patch.object(incremental, "go"),
            patch.object(incremental, "tqdm", side_effect=lambda items, **kwargs: items),
        ):
            incremental.run_incremental_backtests()
        return [call.args[1] for call in scenario.call_args_list]

    def _check_screening(self, run):
        cases = [
            ("gap_spike", [1.0, np.nan, 25.0], ["STEADY"]),
            ("no_gap_spike", [1.0, 25.0, 25.0], ["STEADY"]),
            ("ordinary_gap", [10.0, np.nan, 12.0], ["GAP", "STEADY"]),
            ("ordinary_prices", [10.0, 11.0, 12.0], ["GAP", "STEADY"]),
        ]
        for name, values, expected_columns in cases:
            with self.subTest(case=name):
                prices = pd.DataFrame(
                    {"GAP": values, "STEADY": [10.0, 11.0, 12.0]}, index=self.dates
                )
                scenario_prices = run(prices)
                self.assertEqual(len(scenario_prices), 3)
                for actual in scenario_prices:
                    self.assertEqual(actual.columns.tolist(), expected_columns)
                    if name == "ordinary_gap":
                        # Screening must not replace the simulation's existing bfill.
                        self.assertEqual(actual.loc[self.dates[1], "GAP"], 12.0)
                    elif name == "ordinary_prices":
                        pd.testing.assert_frame_equal(actual, prices)

    def test_full_backtest_screens_gap_spikes(self):
        self._check_screening(self._full_run_prices)

    def test_incremental_backtest_screens_gap_spikes(self):
        self._check_screening(self._incremental_run_prices)


if __name__ == "__main__":
    unittest.main()
