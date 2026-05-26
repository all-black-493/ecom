-- BigQuery raw-layer DDL. These tables shadow Postgres 1:1.
-- Idempotent: safe to re-run during ETL bootstrap.

CREATE SCHEMA IF NOT EXISTS `${GCP_PROJECT_ID}.${BQ_DATASET_RAW}`;

CREATE TABLE IF NOT EXISTS `${GCP_PROJECT_ID}.${BQ_DATASET_RAW}.customers` (
  id              INT64,
  email           STRING,
  first_name      STRING,
  last_name       STRING,
  signup_channel  STRING,
  signup_country  STRING,
  marketing_opt_in BOOL,
  created_at      TIMESTAMP,
  updated_at      TIMESTAMP,
  _ingested_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY DATE(created_at)
CLUSTER BY signup_channel;

CREATE TABLE IF NOT EXISTS `${GCP_PROJECT_ID}.${BQ_DATASET_RAW}.categories` (
  id        INT64,
  slug      STRING,
  name      STRING,
  parent_id INT64,
  _ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS `${GCP_PROJECT_ID}.${BQ_DATASET_RAW}.products` (
  id            INT64,
  sku           STRING,
  name          STRING,
  description   STRING,
  category_id   INT64,
  brand         STRING,
  price         NUMERIC,
  cost          NUMERIC,
  weight_grams  INT64,
  is_active     BOOL,
  launched_at   TIMESTAMP,
  created_at    TIMESTAMP,
  _ingested_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY DATE(launched_at)
CLUSTER BY brand, is_active;

CREATE TABLE IF NOT EXISTS `${GCP_PROJECT_ID}.${BQ_DATASET_RAW}.product_variants` (
  id              INT64,
  product_id      INT64,
  sku             STRING,
  size            STRING,
  color           STRING,
  price_override  NUMERIC,
  _ingested_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS `${GCP_PROJECT_ID}.${BQ_DATASET_RAW}.orders` (
  id              INT64,
  order_number    STRING,
  customer_id     INT64,
  status          STRING,
  currency        STRING,
  subtotal        NUMERIC,
  discount_total  NUMERIC,
  shipping_total  NUMERIC,
  tax_total       NUMERIC,
  grand_total     NUMERIC,
  channel         STRING,
  utm_source      STRING,
  utm_campaign    STRING,
  device_type     STRING,
  placed_at       TIMESTAMP,
  paid_at         TIMESTAMP,
  fulfilled_at    TIMESTAMP,
  delivered_at    TIMESTAMP,
  cancelled_at    TIMESTAMP,
  _ingested_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY DATE(placed_at)
CLUSTER BY status, channel;

CREATE TABLE IF NOT EXISTS `${GCP_PROJECT_ID}.${BQ_DATASET_RAW}.order_items` (
  id             INT64,
  order_id       INT64,
  product_id     INT64,
  variant_id     INT64,
  quantity       INT64,
  unit_price     NUMERIC,
  unit_cost      NUMERIC,
  line_discount  NUMERIC,
  _ingested_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS `${GCP_PROJECT_ID}.${BQ_DATASET_RAW}.inventory_levels` (
  id             INT64,
  variant_id     INT64,
  warehouse_code STRING,
  on_hand        INT64,
  reserved       INT64,
  reorder_point  INT64,
  updated_at     TIMESTAMP,
  _ingested_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS `${GCP_PROJECT_ID}.${BQ_DATASET_RAW}.stock_movements` (
  id             INT64,
  variant_id     INT64,
  warehouse_code STRING,
  delta          INT64,
  reason         STRING,
  ref_order_id   INT64,
  occurred_at    TIMESTAMP,
  _ingested_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY DATE(occurred_at);

CREATE TABLE IF NOT EXISTS `${GCP_PROJECT_ID}.${BQ_DATASET_RAW}.carts` (
  id             INT64,
  customer_id    INT64,
  session_id     STRING,
  status         STRING,
  created_at     TIMESTAMP,
  abandoned_at   TIMESTAMP,
  converted_at   TIMESTAMP,
  _ingested_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY DATE(created_at);

CREATE TABLE IF NOT EXISTS `${GCP_PROJECT_ID}.${BQ_DATASET_RAW}.product_events` (
  id            INT64,
  session_id    STRING,
  customer_id   INT64,
  product_id    INT64,
  event_type    STRING,
  occurred_at   TIMESTAMP,
  _ingested_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY DATE(occurred_at)
CLUSTER BY event_type;

CREATE TABLE IF NOT EXISTS `${GCP_PROJECT_ID}.${BQ_DATASET_RAW}.promotion_redemptions` (
  id             INT64,
  promotion_id   INT64,
  order_id       INT64,
  customer_id    INT64,
  amount_off     NUMERIC,
  redeemed_at    TIMESTAMP,
  _ingested_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY DATE(redeemed_at);
