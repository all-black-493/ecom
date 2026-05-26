# Warehouse — BigQuery star schema

## Layering

We follow a three-layer warehouse (Kimball-influenced, but lighter):

```
lumen_raw       lumen_stg           lumen_mart
──────────      ────────────        ──────────────
1:1 copies   →  cleaned + typed  →  business marts
of Postgres     (still per-table)   (joined, modeled)
tables          deduped on PK       wide, query-ready
                                    used by Looker Studio
```

- **`lumen_raw`**: nightly full snapshot (or incremental for big tables).
  Tables here look exactly like Postgres. No transformations beyond casting.
- **`lumen_stg`**: deduped, typed, conformed names (snake_case, `created_at`).
  This is where slowly-changing dimensions get their effective dates.
- **`lumen_mart`**: facts and dimensions joined into the wide tables that
  dashboards point at.

## Why a warehouse at all when Postgres works?

For the in-app dashboards (Cube.dev) Postgres is fast enough. The warehouse
exists because:

1. **Decoupled compute.** A long-running cohort query in Postgres locks
   pages and hurts checkout latency. BigQuery has its own compute.
2. **History.** OLTP rows get updated; warehouse rows accumulate history.
   "What did the catalog look like on 2025-11-30?" is impossible in
   Postgres alone.
3. **Joining external data.** Marketing CAC, GA4, ad spend, ERP cost layers
   — all easier to land in BigQuery and join there.
4. **ML feature engineering.** Prophet trains on years of daily data; we
   don't want to drag that through OLTP.

## Grain choices

Picking the right *grain* is the most important schema decision:

| Fact table          | Grain                          | Why                                                  |
|---------------------|--------------------------------|------------------------------------------------------|
| `fct_orders`        | one row per order              | KPI numerator (orders, revenue, AOV, margin)         |
| `fct_order_items`   | one row per line item          | product-level revenue, mix analysis                  |
| `fct_stock_moves`   | one row per stock movement     | inventory aging, turnover                            |
| `fct_product_events`| one row per pageview/atc       | funnel analysis                                      |
| `fct_carts`         | one row per cart               | abandonment, recovery                                |

## Dimensions

| Dim                  | SCD type | Notes                                            |
|----------------------|----------|--------------------------------------------------|
| `dim_customer`       | Type 2   | Track signup_channel changes (rare but real)     |
| `dim_product`        | Type 2   | Price/cost changes need history for margin truth |
| `dim_date`           | static   | Pre-built calendar with fiscal markers           |
| `dim_channel`        | Type 1   | Lookups for channel display names                |

## Marts

Marts are the wide, denormalized tables that Looker Studio queries.
They isolate dashboard breakage from upstream schema changes.

See `sql/03_marts.sql` for the full list with definitions.
