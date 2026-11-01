"""Fit and evaluate a transparent oil/yield conditional-return benchmark."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
HORIZONS = (1, 5, 20)
MIN_BIN_ROWS = 30


def category(oil_percent: float, yield_bp: float) -> str:
    oil = "oil_lt_m3" if oil_percent < -3 else (
        "oil_m3_m1" if oil_percent < -1 else (
            "oil_m1_p1" if oil_percent < 1 else (
                "oil_p1_p3" if oil_percent < 3 else "oil_ge_p3")))
    rate = "yield_lt_m5" if yield_bp < -5 else (
        "yield_m5_p5" if yield_bp < 5 else "yield_ge_p5")
    return f"{oil}|{rate}"


def quantile(values: list[float], proportion: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * proportion
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def summary(values: list[float]) -> dict[str, float | int]:
    if not values:
        raise ValueError("Cannot summarize an empty training group")
    return {"n": len(values), "p10": quantile(values, 0.1),
            "median": quantile(values, 0.5), "p90": quantile(values, 0.9)}


def main() -> None:
    with (PROCESSED / "scenario_response_daily.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    train = [row for row in rows if row["split"] == "train"]
    if not train:
        raise ValueError("No training rows")
    grouped: dict[tuple[str, int, str], list[float]] = defaultdict(list)
    unconditional: dict[tuple[str, int], list[float]] = defaultdict(list)
    for row in train:
        bin_name = category(float(row["oil_change_percent"]), float(row["treasury_10y_change_basis_points"]))
        for horizon in HORIZONS:
            value = float(row[f"return_{horizon}d"])
            grouped[(row["ticker"], horizon, bin_name)].append(value)
            unconditional[(row["ticker"], horizon)].append(value)
    learned = {key: summary(values) for key, values in grouped.items()}
    fallback = {key: summary(values) for key, values in unconditional.items()}
    predictions = []
    metrics: dict[tuple[str, str, int], dict[str, float | int]] = defaultdict(
        lambda: {"n": 0, "median_absolute_error_sum": 0.0,
                 "zero_absolute_error_sum": 0.0, "interval_covered": 0,
                 "interval_width_sum": 0.0, "fallback_rows": 0})
    for row in rows:
        split = row["split"]
        if split not in ("validation", "test"):
            continue
        ticker = row["ticker"]
        bin_name = category(float(row["oil_change_percent"]), float(row["treasury_10y_change_basis_points"]))
        for horizon in HORIZONS:
            conditional = learned.get((ticker, horizon, bin_name))
            use_fallback = conditional is None or conditional["n"] < MIN_BIN_ROWS
            estimate = fallback[(ticker, horizon)] if use_fallback else conditional
            actual = float(row[f"return_{horizon}d"])
            predictions.append({"shock_date": row["shock_date"], "ticker": ticker,
                                "split": split, "horizon_trading_days": horizon,
                                "oil_change_percent": row["oil_change_percent"],
                                "treasury_10y_change_basis_points": row["treasury_10y_change_basis_points"],
                                "bin": bin_name, "training_rows_used": estimate["n"],
                                "fallback": int(use_fallback), "p10": estimate["p10"],
                                "median": estimate["median"], "p90": estimate["p90"],
                                "actual_return": actual})
            item = metrics[(split, ticker, horizon)]
            item["n"] += 1
            item["median_absolute_error_sum"] += abs(actual - estimate["median"])
            item["zero_absolute_error_sum"] += abs(actual)
            item["interval_covered"] += int(estimate["p10"] <= actual <= estimate["p90"])
            item["interval_width_sum"] += estimate["p90"] - estimate["p10"]
            item["fallback_rows"] += int(use_fallback)
    prediction_path = PROCESSED / "baseline_predictions.csv"
    with prediction_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(predictions[0]))
        writer.writeheader()
        writer.writerows(predictions)
    metric_rows = []
    for (split, ticker, horizon), item in sorted(metrics.items()):
        count = item["n"]
        metric_rows.append({"split": split, "ticker": ticker, "horizon_trading_days": horizon,
                            "rows": count, "median_mae": item["median_absolute_error_sum"] / count,
                            "zero_mae": item["zero_absolute_error_sum"] / count,
                            "p10_p90_coverage": item["interval_covered"] / count,
                            "mean_interval_width": item["interval_width_sum"] / count,
                            "fallback_rows": item["fallback_rows"]})
    with (PROCESSED / "baseline_metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(metric_rows[0]))
        writer.writeheader()
        writer.writerows(metric_rows)
    model = {"fitted_at_utc": datetime.now(timezone.utc).isoformat(),
             "training_rows": len(train), "minimum_bin_rows": MIN_BIN_ROWS,
             "bin_edges": {"oil_percent": [-3, -1, 1, 3], "yield_basis_points": [-5, 5]},
             "groups": [{"ticker": ticker, "horizon": horizon, "bin": bin_name, **stats}
                        for (ticker, horizon, bin_name), stats in sorted(learned.items())],
             "fallback_groups": [{"ticker": ticker, "horizon": horizon, **stats}
                                 for (ticker, horizon), stats in sorted(fallback.items())],
             "note": "Historical conditional quantiles are a benchmark, not causal effects or calibrated forecasts."}
    (PROCESSED / "baseline_model.json").write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"training_rows": len(train), "predictions": len(predictions),
                      "metrics": len(metric_rows),
                      "test_spy": [row for row in metric_rows if row["split"] == "test" and row["ticker"] == "SPY"]}, indent=2))


if __name__ == "__main__":
    main()
