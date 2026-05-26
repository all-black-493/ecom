# Advanced analytics — demand forecasting

## The business question

**Q16: What is the expected revenue and unit demand for the next 30 days,
top-line and per category?**

We use this forecast in three places:

1. **CFO cash planning** — top-line revenue forecast on the executive dashboard.
2. **Inventory purchasing** — per-category daily demand drives reorder
   quantities for the operations team.
3. **Stockout risk** — for each SKU we combine the category forecast with
   the SKU's historical share to project days-of-cover under expected demand.

## Why Prophet

Prophet handles three things that classic statsmodels asks the analyst to
hand-engineer:

* **Multiple seasonalities** — weekly + yearly automatically.
* **Holiday / event effects** — declarative (we pass Black Friday, Boxing Day).
* **Robust to missing days and outliers** — important because our seed data
  has cancellations and refunds that suppress some days.

For a richer feature set we'd graduate to **LightGBM** or **NeuralProphet**;
Prophet is the right starting point because the assumptions are transparent
and the model is interpretable.

## Files

| File                          | Purpose                                                       |
|-------------------------------|---------------------------------------------------------------|
| `run_forecast.py`             | Standalone training run. Reads from Postgres if BQ creds absent, writes forecast.json |
| `notebooks/forecast_eda.ipynb`| Exploratory notebook — train/test split, MAPE, residual analysis |
| `evaluation.py`               | Walk-forward back-test: produces MAPE + coverage statistics    |

## Evaluation

We back-test with walk-forward validation: split history at month boundaries,
train on everything before, predict the next 30 days, compare to actuals.
Target metrics:

| Metric                     | Target  | Why                                  |
|----------------------------|---------|--------------------------------------|
| MAPE (top-line)            | < 10%   | Tight enough for cash planning       |
| MAPE (per category)        | < 18%   | Smaller volumes → wider band         |
| 80% interval coverage      | 75–85%  | Calibrated uncertainty (not too narrow, not too wide) |

If MAPE drifts above target for two consecutive runs, Airflow opens a
"forecast-degraded" alert via the operations channel.

## Failure modes we monitor

* **Promo-driven blowouts** — Prophet may treat them as outliers and
  under-forecast the next event. Fix: register promo events as known
  regressors when the promo calendar is available.
* **New SKU launches** — no history, so the per-category forecast is
  fine but per-SKU is unreliable. We document this in the dashboard tooltip.
* **Cold start** — under 60 days of history a category falls back to the
  category-average daily revenue with a wider band.
