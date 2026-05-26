-- Business-facing marts. Looker Studio and Cube point at these.

-- ----------------------------------------------------------- mart_daily_revenue --
CREATE OR REPLACE VIEW `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.mart_daily_revenue` AS
SELECT
  order_date                                                          AS date,
  SUM(grand_total)                                                    AS revenue,
  COUNT(DISTINCT order_id)                                            AS orders,
  COUNT(DISTINCT customer_id)                                         AS unique_customers,
  SAFE_DIVIDE(SUM(grand_total), COUNT(DISTINCT order_id))             AS aov,
  -- 7-day rolling
  AVG(SUM(grand_total)) OVER (
    ORDER BY order_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
  )                                                                   AS revenue_7d_avg
FROM `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.fct_orders`
WHERE is_revenue_recognized
GROUP BY order_date;

-- --------------------------------------------------------- mart_product_velocity --
CREATE OR REPLACE VIEW `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.mart_product_velocity` AS
WITH last_28 AS (
  SELECT product_id, SUM(quantity) AS units_28d, SUM(line_revenue) AS revenue_28d
  FROM `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.fct_order_items`
  WHERE order_date BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 28 DAY) AND CURRENT_DATE()
  GROUP BY product_id
),
last_84 AS (
  SELECT product_id, SUM(quantity) AS units_84d, SUM(line_revenue) AS revenue_84d
  FROM `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.fct_order_items`
  WHERE order_date BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 84 DAY) AND CURRENT_DATE()
  GROUP BY product_id
)
SELECT
  p.product_id,
  p.sku,
  p.name,
  p.brand,
  p.category_name,
  COALESCE(a.units_28d, 0)   AS units_28d,
  COALESCE(a.revenue_28d, 0) AS revenue_28d,
  COALESCE(b.units_84d, 0)   AS units_84d,
  COALESCE(b.revenue_84d, 0) AS revenue_84d,
  SAFE_DIVIDE(a.units_28d, 28.0) AS units_per_day,
  CASE
    WHEN COALESCE(a.units_28d, 0) = 0 THEN 'dead'
    WHEN a.units_28d <= 5 THEN 'slow'
    WHEN a.units_28d <= 25 THEN 'steady'
    ELSE 'fast'
  END AS velocity_bucket
FROM `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.dim_product` p
LEFT JOIN last_28 a ON a.product_id = p.product_id
LEFT JOIN last_84 b ON b.product_id = p.product_id
WHERE p.is_active;

-- ----------------------------------------------------------- mart_category_pnl --
CREATE OR REPLACE VIEW `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.mart_category_pnl` AS
SELECT
  dp.category_name,
  oi.order_date,
  SUM(oi.line_revenue) AS revenue,
  SUM(oi.line_cost)    AS cost,
  SUM(oi.line_margin)  AS gross_margin,
  SAFE_DIVIDE(SUM(oi.line_margin), SUM(oi.line_revenue)) AS margin_pct
FROM `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.fct_order_items` oi
JOIN `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.dim_product` dp ON dp.product_id = oi.product_id
GROUP BY dp.category_name, oi.order_date;

-- ----------------------------------------------------------- mart_channel_perf --
CREATE OR REPLACE VIEW `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.mart_channel_perf` AS
SELECT
  channel,
  order_date,
  device_type,
  COUNT(*)            AS orders,
  SUM(grand_total)    AS revenue,
  AVG(grand_total)    AS aov,
  COUNT(DISTINCT customer_id) AS unique_customers
FROM `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.fct_orders`
WHERE is_revenue_recognized
GROUP BY channel, order_date, device_type;

-- --------------------------------------------------------- mart_cohort_retention --
CREATE OR REPLACE VIEW `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.mart_cohort_retention` AS
WITH first_order AS (
  SELECT customer_id, DATE_TRUNC(MIN(order_date), MONTH) AS cohort_month
  FROM `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.fct_orders`
  WHERE is_revenue_recognized
  GROUP BY customer_id
),
activity AS (
  SELECT o.customer_id, fo.cohort_month,
         DATE_TRUNC(o.order_date, MONTH) AS active_month
  FROM `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.fct_orders` o
  JOIN first_order fo USING (customer_id)
  WHERE o.is_revenue_recognized
)
SELECT
  cohort_month,
  active_month,
  DATE_DIFF(active_month, cohort_month, MONTH) AS months_since_signup,
  COUNT(DISTINCT customer_id) AS active_customers
FROM activity
GROUP BY cohort_month, active_month;

-- --------------------------------------------------------- mart_customer_lifecycle --
CREATE OR REPLACE VIEW `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.mart_customer_lifecycle` AS
WITH per_customer AS (
  SELECT
    customer_id,
    COUNT(*) AS lifetime_orders,
    SUM(grand_total) AS lifetime_revenue,
    MIN(order_date) AS first_order_date,
    MAX(order_date) AS last_order_date
  FROM `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.fct_orders`
  WHERE is_revenue_recognized
  GROUP BY customer_id
)
SELECT
  c.*,
  pc.lifetime_orders,
  pc.lifetime_revenue,
  pc.first_order_date,
  pc.last_order_date,
  DATE_DIFF(CURRENT_DATE(), pc.last_order_date, DAY) AS days_since_last_order,
  CASE
    WHEN pc.last_order_date IS NULL                                THEN 'never_purchased'
    WHEN DATE_DIFF(CURRENT_DATE(), pc.last_order_date, DAY) <= 30  THEN 'active'
    WHEN DATE_DIFF(CURRENT_DATE(), pc.last_order_date, DAY) <= 90  THEN 'lapsing'
    WHEN DATE_DIFF(CURRENT_DATE(), pc.last_order_date, DAY) <= 180 THEN 'dormant'
    ELSE 'churned'
  END AS lifecycle_stage
FROM `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.dim_customer` c
LEFT JOIN per_customer pc USING (customer_id);

-- -------------------------------------------------------------- mart_funnel --
CREATE OR REPLACE VIEW `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.mart_funnel` AS
WITH events AS (
  SELECT event_date, event_type, COUNT(*) AS n
  FROM `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.fct_product_events`
  GROUP BY 1, 2
),
carts AS (
  SELECT created_date AS event_date, COUNT(*) AS n_started_checkout
  FROM `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.fct_carts`
  WHERE status IN ('abandoned','converted')
  GROUP BY 1
),
ords AS (
  SELECT order_date AS event_date, COUNT(*) AS n_purchased
  FROM `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.fct_orders`
  WHERE is_revenue_recognized
  GROUP BY 1
)
SELECT
  COALESCE(v.event_date, c.event_date, o.event_date) AS event_date,
  SUM(CASE WHEN v.event_type = 'view' THEN v.n END)             AS views,
  SUM(CASE WHEN v.event_type = 'add_to_cart' THEN v.n END)      AS add_to_cart,
  ANY_VALUE(c.n_started_checkout)                               AS started_checkout,
  ANY_VALUE(o.n_purchased)                                      AS purchased
FROM events v
FULL OUTER JOIN carts c ON c.event_date = v.event_date
FULL OUTER JOIN ords  o ON o.event_date = COALESCE(v.event_date, c.event_date)
GROUP BY 1;

-- --------------------------------------------------------- mart_stockout_risk --
CREATE OR REPLACE VIEW `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.mart_stockout_risk` AS
WITH velocity AS (
  SELECT
    variant_id,
    SUM(quantity) / 28.0 AS units_per_day
  FROM `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.fct_order_items`
  WHERE order_date BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 28 DAY) AND CURRENT_DATE()
  GROUP BY variant_id
),
on_hand AS (
  SELECT variant_id, SUM(on_hand) AS on_hand
  FROM `${GCP_PROJECT_ID}.${BQ_DATASET_RAW}.inventory_levels`
  GROUP BY variant_id
)
SELECT
  pv.id AS variant_id,
  p.sku,
  p.name,
  pv.size,
  pv.color,
  o.on_hand,
  v.units_per_day,
  SAFE_DIVIDE(o.on_hand, NULLIF(v.units_per_day, 0)) AS days_of_cover,
  CASE
    WHEN SAFE_DIVIDE(o.on_hand, NULLIF(v.units_per_day, 0)) < 7  THEN 'urgent'
    WHEN SAFE_DIVIDE(o.on_hand, NULLIF(v.units_per_day, 0)) < 14 THEN 'reorder_soon'
    ELSE 'healthy'
  END AS stock_status
FROM `${GCP_PROJECT_ID}.${BQ_DATASET_RAW}.product_variants` pv
JOIN `${GCP_PROJECT_ID}.${BQ_DATASET_RAW}.products` p ON p.id = pv.product_id
LEFT JOIN velocity v ON v.variant_id = pv.id
LEFT JOIN on_hand  o ON o.variant_id = pv.id;

-- --------------------------------------------------------- mart_inventory_aging --
CREATE OR REPLACE VIEW `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.mart_inventory_aging` AS
SELECT
  p.category_name,
  p.brand,
  p.product_id,
  p.sku,
  p.name,
  SUM(il.on_hand) AS on_hand,
  p.list_cost,
  SUM(il.on_hand) * p.list_cost AS tied_capital
FROM `${GCP_PROJECT_ID}.${BQ_DATASET_RAW}.inventory_levels` il
JOIN `${GCP_PROJECT_ID}.${BQ_DATASET_RAW}.product_variants` pv ON pv.id = il.variant_id
JOIN `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.dim_product` p ON p.product_id = pv.product_id
GROUP BY p.category_name, p.brand, p.product_id, p.sku, p.name, p.list_cost;

-- ----------------------------------------------------------- mart_promo_lift --
CREATE OR REPLACE VIEW `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.mart_promo_lift` AS
SELECT
  pr.promotion_id,
  DATE_TRUNC(pr.redeemed_at, MONTH) AS month,
  COUNT(*) AS redemptions,
  SUM(pr.amount_off) AS discount_given,
  SUM(o.grand_total) AS gross_revenue,
  SUM(oi.line_margin) AS gross_margin,
  -- naive lift: margin / discount (incremental margin per $ given up)
  SAFE_DIVIDE(SUM(oi.line_margin), NULLIF(SUM(pr.amount_off), 0)) AS lift_ratio
FROM `${GCP_PROJECT_ID}.${BQ_DATASET_RAW}.promotion_redemptions` pr
JOIN `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.fct_orders` o      ON o.order_id = pr.order_id
JOIN `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.fct_order_items` oi ON oi.order_id = pr.order_id
GROUP BY pr.promotion_id, month;

-- ----------------------------------------------------------- mart_demand_forecast --
-- This mart is populated by the Prophet job in ml/run_forecast.py via load_gbq.
-- Shape is fixed: (forecast_date, category_name, yhat, yhat_lower, yhat_upper, model_run_at).
CREATE TABLE IF NOT EXISTS `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.mart_demand_forecast` (
  forecast_date   DATE,
  category_name   STRING,
  yhat            FLOAT64,
  yhat_lower      FLOAT64,
  yhat_upper      FLOAT64,
  model_run_at    TIMESTAMP
)
PARTITION BY forecast_date
CLUSTER BY category_name;
