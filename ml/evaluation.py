"""Walk-forward evaluation utilities — used by both the standalone script
and the Airflow nightly retrain.

A common mistake is to evaluate forecasts with a single holdout. Demand
data is non-stationary; a model that looks good on October won't necessarily
be good in January. Walk-forward gives us a fair number across multiple
time windows.
"""

from __future__ import annotations

import pandas as pd


def walk_forward(history: pd.DataFrame, fit_fn, horizon: int = 30, n_splits: int = 4) -> pd.DataFrame:
    """Returns one row per split with mape and 80%-interval coverage.

    Args:
      history: DataFrame with ds, y. Must be daily and sorted.
      fit_fn:  Callable(df_train, horizon) -> DataFrame with ds, yhat, yhat_lower, yhat_upper.
      horizon: forecast horizon in days.
      n_splits: number of trailing windows to test.
    """
    history = history.sort_values("ds").reset_index(drop=True)
    rows = []
    for k in range(n_splits, 0, -1):
        cut = len(history) - k * horizon
        if cut < 60:
            continue
        train, test = history.iloc[:cut], history.iloc[cut : cut + horizon]
        fcst = fit_fn(train, horizon)[["ds", "yhat", "yhat_lower", "yhat_upper"]]
        merged = test.merge(fcst, on="ds")
        mape = (abs(merged["y"] - merged["yhat"]) / merged["y"].replace(0, pd.NA)).mean()
        coverage = (
            (merged["y"] >= merged["yhat_lower"]) & (merged["y"] <= merged["yhat_upper"])
        ).mean()
        rows.append(
            {
                "split_end": str(test["ds"].max().date()),
                "n_train": len(train),
                "n_test": len(test),
                "mape": float(mape),
                "coverage_80": float(coverage),
            }
        )
    return pd.DataFrame(rows)
