# Dashboard design

The dashboards in this project follow a small set of principles, drawn from
**Edward Tufte** (*The Visual Display of Quantitative Information*),
**Stephen Few** (*Information Dashboard Design*), and the **IBCS** standard.

## Five principles we apply

1. **Every chart answers a stated question.** If you can't write the question
   above the chart in plain English, the chart shouldn't exist.
2. **Maximize the data-ink ratio.** Strip gridlines, drop shadows, colored
   backgrounds, 3-D effects, and decorative borders. Pixels exist to convey
   numbers, not to look busy.
3. **One accent colour, used to mean one thing.** Our palette is monochrome
   neutral plus a teal accent for *signal* and an amber accent reserved for
   *warning*. A dashboard with 10 colours has no colour.
4. **Pre-attentive cues > legends.** Sort bars by magnitude, place the most
   important KPI top-left (F-pattern reading), and bold the value not the
   label. People should answer the question in under 5 seconds.
5. **Show context, not just a number.** A KPI without a trend or a
   benchmark is just trivia. Each KPI gets a 30-day sparkline and either a
   prior-period delta or a target.

## Layout grammar

We use a consistent grid across all reports:

```
┌─────────────────────────────────────────────────────────────────────┐
│  KPI 1     │  KPI 2     │  KPI 3     │  KPI 4                       │   (row 1: scoreboard)
├─────────────────────────────────────────────────────────────────────┤
│  Primary chart (time series, full width)                            │   (row 2: trend)
├──────────────────────────────────────┬──────────────────────────────┤
│  Breakdown chart A                   │  Breakdown chart B           │   (row 3: comparison)
├──────────────────────────────────────┴──────────────────────────────┤
│  Ranked table (top N)                                               │   (row 4: detail)
└─────────────────────────────────────────────────────────────────────┘
```

The reader's eye flows: **headline → trend → breakdown → drill-down**.

## Dashboards in this project

### D1 — Executive daily (Looker Studio)
- **Audience:** Founder, CFO. Read on phone in the morning.
- **Question:** "Is the business on track today?"
- **Panels:**
  - KPI row: revenue MTD, orders MTD, AOV, repeat-rate (30d)
  - Daily revenue with 7-day rolling average (trend)
  - Revenue by channel (horizontal bar, sorted)
  - 30-day demand-forecast band overlaid on actuals
- **Choice rationale:** Sparklines beat tables for "is it normal?". Forecast band
  gives the CFO a defensible "what's coming" number with uncertainty visible.

### D2 — Merchandising weekly (Looker Studio)
- **Audience:** Buyer, category manager
- **Question:** "What's selling, what's stuck, what should we do?"
- **Panels:**
  - Top 25 SKUs by revenue (ranked table with conditional formatting)
  - Slow movers — units < 5 in 60 days, on-hand × cost = tied-up capital
  - Gross margin by category (bar + margin %)
  - Promo lift heatmap

### D3 — Sales (in-app, Cube.dev)
- **Audience:** Anyone in the company, embedded in the FastAPI app
- **Question:** "How are we doing right now?"
- **Panels:** KPI row → daily revenue + orders → channel mix + category margin → top products
- **Why Cube.dev:** Sub-second queries off Postgres replicas; same semantic model serves the analyst's notebook too.

### D4 — Inventory (in-app, Cube.dev)
- **Audience:** Operations team
- **Question:** "What needs my attention this morning?"
- **Panels:** Funnel → abandonment → stockout-risk table → slow movers → forecast chart
- **Why operational not strategic:** This dashboard *drives behaviour* — a buyer should leave it with a reorder list.

## Anti-patterns we deliberately avoid

- **Pie charts with > 3 slices.** People cannot judge angles. Use a bar.
- **Stacked-bar everything.** Stacking makes comparison of inner segments impossible. Use small multiples instead.
- **3D anything.**
- **"Dashboard as catalogue."** 14 charts on one page where no chart drives a decision. Each tab in our app has 4–6 panels max.
- **Hidden filters / mystery numbers.** Every dashboard page exposes the date range and any segment filter at the top.

## How dashboards link to the analytics questions

| Question | Primary dashboard | Mart |
|----------|-------------------|------|
| Q1 (daily revenue) | D1, D3 | `mart_daily_revenue` |
| Q2 (fast/slow movers) | D2, D4 | `mart_product_velocity` |
| Q3 (category margin) | D2, D3 | `mart_category_pnl` |
| Q4 (AOV by device/channel) | D3 | `mart_channel_perf` |
| Q5 (cart abandonment) | D4 | `mart_funnel` |
| Q6 (funnel) | D4 | `mart_funnel` |
| Q7–Q8 (repeat / cohort) | D1 | `mart_cohort_retention` |
| Q11 (stockout risk) | D4 | `mart_stockout_risk` |
| Q12 (capital tied up) | D2 | `mart_inventory_aging` |
| Q14 (promo lift) | D2 | `mart_promo_lift` |
| Q16 (demand forecast) | D1, D4 | `mart_demand_forecast` |
