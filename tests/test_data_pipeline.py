"""Checks for response timing, historical boundaries, and numerical bins."""

import sys
import unittest
from datetime import date, timedelta
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_model_tables import TICKERS, build_rows, split_for  # noqa: E402
from evaluate_baseline import category, quantile  # noqa: E402
from validate_drafts import stated_change, OIL_PATTERN, YIELD_PATTERN, validate_events, validate_scenarios  # noqa: E402


class DataPipelineTests(unittest.TestCase):
    def test_response_window_includes_shock_day_and_uses_trading_rows(self):
        calendar = [(date(1999, 1, 4) + timedelta(days=day)).isoformat() for day in range(25)]
        etfs = {ticker: [{"date": day, "adj_close": str(100 + index)}
                         for index, day in enumerate(calendar)] for ticker in TICKERS}
        oil = {calendar[1]: (calendar[1], 12.0, calendar[0], 10.0, True)}
        yields = {calendar[1]: (calendar[1], 4.75, calendar[0], 4.70, True)}
        vix = {day: None for day in calendar}
        rows = build_rows(etfs, calendar, oil, yields, vix)
        spy = next(row for row in rows if row["ticker"] == "SPY" and row["shock_date"] == calendar[1])
        self.assertAlmostEqual(spy["oil_change_percent"], 20.0)
        self.assertAlmostEqual(spy["treasury_10y_change_basis_points"], 5.0)
        self.assertAlmostEqual(spy["return_1d"], 101 / 100 - 1)
        self.assertAlmostEqual(spy["return_5d"], 105 / 100 - 1)
        self.assertAlmostEqual(spy["return_20d"], 120 / 100 - 1)
        self.assertEqual(spy["outcome_end_date_20d"], calendar[20])

    def test_negative_wti_never_creates_percentage_shock(self):
        calendar = [(date(2020, 4, 19) + timedelta(days=day)).isoformat() for day in range(22)]
        etfs = {ticker: [{"date": day, "adj_close": "100"} for day in calendar]
                for ticker in TICKERS}
        oil = {calendar[1]: (calendar[1], -36.98, calendar[0], 18.31, True)}
        yields = {calendar[1]: (calendar[1], 0.6, calendar[0], 0.62, True)}
        vix = {day: None for day in calendar}
        rows = build_rows(etfs, calendar, oil, yields, vix)
        row = next(row for row in rows if row["ticker"] == "SPY" and row["shock_date"] == calendar[1])
        self.assertEqual(row["oil_change_percent"], "")
        self.assertAlmostEqual(row["oil_change_usd"], -55.29)
        self.assertEqual(row["split"], "incomplete")

    def test_split_embargo_and_bin_edges(self):
        self.assertEqual(split_for("2018-12-10", "2019-01-08", True), "embargo")
        self.assertEqual(split_for("2018-12-10", "2018-12-31", True), "train")
        self.assertEqual(split_for("2022-12-10", "2023-01-05", True), "embargo")
        self.assertEqual(split_for("2023-01-02", "2023-01-27", True), "test")
        self.assertEqual(category(-3, 5), "oil_m3_m1|yield_ge_p5")
        self.assertEqual(quantile([0.0, 10.0], 0.5), 5.0)

    def test_stale_factor_keeps_observed_price_without_deducing_daily_shock(self):
        calendar = [(date(2000, 1, 3) + timedelta(days=day)).isoformat() for day in range(22)]
        etfs = {ticker: [{"date": day, "adj_close": "100"} for day in calendar]
                for ticker in TICKERS}
        oil = {calendar[1]: (calendar[1], 25.0, "1999-12-20", 20.0, False)}
        yields = {calendar[1]: (calendar[1], 6.0, calendar[0], 5.9, True)}
        vix = {day: None for day in calendar}
        row = next(row for row in build_rows(etfs, calendar, oil, yields, vix)
                   if row["ticker"] == "SPY" and row["shock_date"] == calendar[1])
        self.assertEqual(row["oil_price_usd"], 25.0)
        self.assertEqual(row["oil_previous_price_usd"], 20.0)
        self.assertEqual(row["oil_change_percent"], "")
        self.assertEqual(row["split"], "incomplete")

    def test_scenario_shocks_must_match_text_and_unknowns_stay_blank(self):
        self.assertEqual(stated_change("WTI oil falls 8 percent", OIL_PATTERN,
                                       "WTI oil is unchanged"), -8)
        self.assertEqual(stated_change("US 10-year Treasury yield is unchanged",
                                       YIELD_PATTERN, "US 10-year Treasury yield is unchanged"), 0)
        row = {"scenario_id": "S-test", "scenario_text": "A bank fails tomorrow",
               "affected_sectors": "SPY|XLF", "time_horizon_trading_days": "5",
               "oil_change_percent": "10", "treasury_10y_change_basis_points": "",
               "missing_assumptions": "treasury_yield_change", "review_status": "unreviewed"}
        with self.assertRaisesRegex(ValueError, "Missing shock must stay blank"):
            validate_scenarios([row])

    def test_scheduled_release_time_is_not_first_public_time(self):
        row = {"event_id": "test", "event_date": "2022-03-16",
               "event_date_basis": "Fed statement date",
               "source_url": "https://www.federalreserve.gov/example",
               "source_release_timestamp_utc": "2022-03-16T18:00:00Z",
               "source_time_basis": "for release at 14:00 EDT",
               "first_public_timestamp_utc": "", "first_public_source_url": "",
               "review_status": "date_and_source_release_time_verified",
               "assumed_channels": ""}
        self.assertEqual(validate_events([row])["first_public_times"], 0)
        row["source_release_timestamp_utc"] = "2022-03-17T18:00:00Z"
        with self.assertRaisesRegex(ValueError, "Release time/date mismatch"):
            validate_events([row])


if __name__ == "__main__":
    unittest.main()
