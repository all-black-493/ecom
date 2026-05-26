-- Dimension & fact tables in lumen_mart.
-- Built as views over raw for ease of recompute; in production these would
-- be materialized incremental tables managed by dbt/dataform.

CREATE SCHEMA IF NOT EXISTS `${GCP_PROJECT_ID}.${BQ_DATASET_MART}`;

-- ---------------------------------------------------------------- dim_date --
CREATE OR REPLACE TABLE `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.dim_date` AS
SELECT
  d AS date,
  EXTRACT(YEAR FROM d)         AS year,
  EXTRACT(QUARTER FROM d)      AS quarter,
  EXTRACT(MONTH FROM d)        AS month,
  FORMAT_DATE('%B', d)         AS month_name,
  EXTRACT(WEEK FROM d)         AS week,
  EXTRACT(DAY FROM d)          AS day,
  EXTRACT(DAYOFWEEK FROM d)    AS day_of_week,
  FORMAT_DATE('%A', d)         AS day_name,
  IF(EXTRACT(DAYOFWEEK FROM d) IN (1, 7), TRUE, FALSE) AS is_weekend,
  IF(EXTRACT(MONTH FROM d) IN (11, 12), TRUE, FALSE)   AS is_holiday_season
FROM UNNEST(GENERATE_DATE_ARRAY('2023-01-01', '2027-12-31')) AS d;

-- ------------------------------------------------------------ dim_customer --
-- Type 2 SCD on signup_channel is rare to change; simplifying to Type 1 here.
CREATE OR REPLACE VIEW `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.dim_customer` AS
SELECT
  id AS customer_sk,
  id AS customer_id,
  email,
  first_name,
  last_name,
  signup_channel,
  signup_country,
  marketing_opt_in,
  DATE(created_at) AS signup_date,
  DATE_DIFF(CURRENT_DATE(), DATE(created_at), DAY) AS tenure_days
FROM `${GCP_PROJECT_ID}.${BQ_DATASET_RAW}.customers`;

-- ------------------------------------------------------------- dim_product --
CREATE OR REPLACE VIEW `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.dim_product` AS
SELECT
  p.id AS product_sk,
  p.id AS product_id,
  p.sku,
  p.name,
  p.brand,
  p.price AS list_price,
  p.cost  AS list_cost,
  (p.price - p.cost) / NULLIF(p.price, 0) AS list_margin_pct,
  c.slug AS category_slug,
  c.name AS category_name,
  p.is_active,
  DATE(p.launched_at) AS launched_date
FROM `${GCP_PROJECT_ID}.${BQ_DATASET_RAW}.products` p
LEFT JOIN `${GCP_PROJECT_ID}.${BQ_DATASET_RAW}.categories` c ON c.id = p.category_id;

-- --------------------------------------------------------------- fct_orders --
CREATE OR REPLACE VIEW `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.fct_orders` AS
SELECT
  o.id            AS order_sk,
  o.id            AS order_id,
  o.order_number,
  o.customer_id,
  o.status,
  o.channel,
  o.utm_source,
  o.utm_campaign,
  o.device_type,
  DATE(o.placed_at)  AS order_date,
  o.placed_at,
  o.paid_at,
  o.fulfilled_at,
  o.delivered_at,
  o.cancelled_at,
  o.subtotal,
  o.discount_total,
  o.shipping_total,
  o.tax_total,
  o.grand_total,
  -- Derived
  TIMESTAMP_DIFF(o.delivered_at, o.placed_at, HOUR) AS hours_to_deliver,
  IF(o.status IN ('paid','fulfilled','shipped','delivered'), TRUE, FALSE) AS is_revenue_recognized
FROM `${GCP_PROJECT_ID}.${BQ_DATASET_RAW}.orders` o;

-- ----------------------------------------------------------- fct_order_items --
CREATE OR REPLACE VIEW `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.fct_order_items` AS
SELECT
  oi.id           AS order_item_sk,
  oi.order_id,
  oi.product_id,
  oi.variant_id,
  o.customer_id,
  DATE(o.placed_at) AS order_date,
  o.channel,
  o.device_type,
  oi.quantity,
  oi.unit_price,
  oi.unit_cost,
  oi.line_discount,
  oi.quantity * oi.unit_price                AS line_revenue,
  oi.quantity * oi.unit_cost                 AS line_cost,
  oi.quantity * (oi.unit_price - oi.unit_cost) AS line_margin
FROM `${GCP_PROJECT_ID}.${BQ_DATASET_RAW}.order_items` oi
JOIN `${GCP_PROJECT_ID}.${BQ_DATASET_RAW}.orders` o ON o.id = oi.order_id
WHERE o.status NOT IN ('cancelled','refunded');

-- ----------------------------------------------------------- fct_stock_moves --
CREATE OR REPLACE VIEW `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.fct_stock_moves` AS
SELECT
  sm.id           AS stock_move_sk,
  sm.variant_id,
  pv.product_id,
  sm.warehouse_code,
  sm.delta,
  sm.reason,
  sm.ref_order_id,
  DATE(sm.occurred_at) AS move_date,
  sm.occurred_at
FROM `${GCP_PROJECT_ID}.${BQ_DATASET_RAW}.stock_movements` sm
JOIN `${GCP_PROJECT_ID}.${BQ_DATASET_RAW}.product_variants` pv ON pv.id = sm.variant_id;

-- ----------------------------------------------------------- fct_product_events --
CREATE OR REPLACE VIEW `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.fct_product_events` AS
SELECT
  pe.id          AS event_sk,
  pe.session_id,
  pe.customer_id,
  pe.product_id,
  pe.event_type,
  DATE(pe.occurred_at) AS event_date,
  pe.occurred_at
FROM `${GCP_PROJECT_ID}.${BQ_DATASET_RAW}.product_events` pe;

-- ---------------------------------------------------------------- fct_carts --
CREATE OR REPLACE VIEW `${GCP_PROJECT_ID}.${BQ_DATASET_MART}.fct_carts` AS
SELECT
  c.id           AS cart_sk,
  c.customer_id,
  c.session_id,
  c.status,
  DATE(c.created_at) AS created_date,
  c.created_at,
  c.abandoned_at,
  c.converted_at,
  TIMESTAMP_DIFF(c.abandoned_at, c.created_at, MINUTE) AS minutes_to_abandon
FROM `${GCP_PROJECT_ID}.${BQ_DATASET_RAW}.carts` c;
