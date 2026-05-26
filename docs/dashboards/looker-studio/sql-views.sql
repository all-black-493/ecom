-- Convenience views written specifically for Looker Studio, blending the
-- existing marts with comparison columns ("vs prior period") that Looker
-- Studio cannot easily compute on its own.

CREATE OR REPLACE VIEW `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.ls_v_executive_daily` AS
WITH today AS (
  SELECT date, revenue, orders, aov, unique_customers, revenue_7d_avg
  FROM `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.mart_daily_revenue`
),
prior AS (
  SELECT
    DATE_ADD(date, INTERVAL 30 DAY) AS date,
    revenue          AS revenue_prior,
    orders           AS orders_prior,
    aov              AS aov_prior,
    unique_customers AS unique_customers_prior
  FROM `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.mart_daily_revenue`
)
SELECT t.*,
       p.revenue_prior, p.orders_prior, p.aov_prior, p.unique_customers_prior,
       SAFE_DIVIDE(t.revenue - p.revenue_prior, p.revenue_prior) AS revenue_yoy_30d
FROM today t LEFT JOIN prior p USING (date);

CREATE OR REPLACE VIEW `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.ls_v_forecast_overlay` AS
SELECT
  forecast_date AS date,
  category_name,
  yhat,
  yhat_lower,
  yhat_upper,
  model_run_at
FROM `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.mart_demand_forecast`
WHERE model_run_at = (SELECT MAX(model_run_at) FROM `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.mart_demand_forecast`);
