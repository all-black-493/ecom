# Looker Studio dashboards

Looker Studio is a hosted product — there is no checked-in dashboard file.
What we keep in the repo is:

1. **The data layer** that Looker Studio reads from — `lumen_mart` views.
2. **A specification** that lets an analyst rebuild the dashboard from scratch
   in about 30 minutes.
3. **A copy-ready link** once you've built it (paste into `LOOKER_URL` below).

## Data sources

Each report uses BigQuery as a data source, pointing at a view in
`${GCP_PROJECT_ID}.lumen_mart`. Always connect via *Custom Query* or
*BigQuery view* so the dashboard remains decoupled from raw tables.

| Report     | Primary source view              |
|------------|----------------------------------|
| D1 Executive Daily | `mart_daily_revenue` + `mart_demand_forecast` (blend) |
| D2 Merchandising Weekly | `mart_product_velocity` + `mart_category_pnl` |

## D1 — Executive Daily report spec

**Audience:** founder / CFO. **Frequency:** read every morning.
**Print width:** 1200px so it renders cleanly on phone email previews.

### Page layout

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Title:  "Lumen — Executive Daily"          [date range selector: MTD ▼]     │
├────────────────┬────────────────┬────────────────┬───────────────────────────┤
│ Revenue MTD    │ Orders MTD     │ AOV            │ Repeat-rate (30d)         │
│   $342,180     │   2,810        │   $121.78      │   28.4%                   │
│   ▲ 12.4% vs   │   ▲ 9.1% vs    │   ▲ 3.1% vs    │   ▲ 1.8 pp vs prior 30d   │
│   prior period │   prior period │   prior period │                           │
├──────────────────────────────────────────────────────────────────────────────┤
│  Daily revenue + 7-day moving average  (line, 12-week window)                │
│  Forecast band overlay (next 30 days, 80% CI)                                │
├────────────────────────────┬─────────────────────────────────────────────────┤
│  Revenue by channel (bar)  │  Revenue by category — current vs prior 30d     │
│  sorted desc               │  (small multiples; bars side-by-side)           │
├──────────────────────────────────────────────────────────────────────────────┤
│  Forecast detail table — next 7 days with low/high band, by category         │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Chart specifications

| Chart | Type | Data source | Dimensions | Measures | Notes |
|-------|------|-------------|------------|----------|-------|
| KPI scoreboard | Scorecard ×4 | `mart_daily_revenue` | — | `revenue`, `orders`, `aov`, `repeat_rate` | Comparison vs prior period |
| Daily revenue line | Time series | `mart_daily_revenue` | `date` | `revenue`, `revenue_7d_avg` | Two metric Y axes |
| Forecast overlay | Time series (data blend) | `mart_demand_forecast` blended to chart above | `forecast_date` | `yhat`, `yhat_lower`, `yhat_upper` | Use band style, 30% opacity |
| Channel bar | Horizontal bar | `mart_channel_perf` | `channel` | `revenue` | Sort desc, top 7 |
| Category small multiples | Bar (small multiples by category) | `mart_category_pnl` | `category_name`, period | `revenue` | Side-by-side current vs prior |
| Forecast table | Pivot table | `mart_demand_forecast` | `forecast_date`, `category_name` | `yhat`, `yhat_lower`, `yhat_upper` | First 7 days only |

### Theme

* Background: `#FAFAF8`
* Accent: `#0F766E` (single colour for all charts)
* Warning/forecast band: `#B45309` at 25% opacity
* Font: Inter, 14pt body / 24pt KPI

### Filters (page-level)

* Date range (default: last 30 days; presets: today, MTD, last 30, last 90)

## D2 — Merchandising Weekly report spec

**Audience:** Buyer / Category Manager. **Frequency:** weekly.

### Page layout

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Title: "Lumen — Merchandising Weekly"      [category filter ▼]              │
├──────────────────────────────────────────────────────────────────────────────┤
│  Top 25 SKUs by revenue (table with bars, sortable)                          │
├────────────────────────────┬─────────────────────────────────────────────────┤
│  Gross margin by category  │  Velocity heatmap (SKU × week)                  │
│  (bar + line: margin $/%)  │  Cells coloured by units sold                   │
├──────────────────────────────────────────────────────────────────────────────┤
│  Slow movers table  (units_28d ≤ 5, on_hand × cost = tied capital)           │
├──────────────────────────────────────────────────────────────────────────────┤
│  Promo redemption summary (rows: promo, cols: month — discount $, lift %)    │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Build steps

1. Looker Studio → *Create report* → *Connect data* → BigQuery → select `lumen_mart`.
2. Add data source for each view above; "Refresh fields" then mark `date`/
   `order_date` as Date types.
3. Build pages following the layout. Theme: Customize → upload `theme.json`
   from this directory.
4. Share publicly (view only) — paste link below.

## Filling in the URL

Once published, update this stub:

```
LOOKER_STUDIO_URL_D1=
LOOKER_STUDIO_URL_D2=
```

(also reflected in the README's "Quick start" so the deployed app links work).
