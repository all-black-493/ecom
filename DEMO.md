# Demo & presentation guide

How to use this project end-to-end and present it well.

---

## Part 1 — The mental model (memorize this)

The whole thing is **four stages of a single data lifecycle**:

```
   1. CAPTURE           2. STORE            3. ANALYZE         4. ACT
   ─────────            ─────────           ─────────          ─────
   FastAPI app    ──►   Postgres OLTP ──►   Postgres /         Dashboards
   (storefront,         (source of truth)   BigQuery views     ML forecast
    orders, carts)                          Cube semantic      Presentation
                                            layer
                            │                      ▲
                            ▼                      │
                          Airflow ──── transforms ─┘
                          (hourly)
```

If you can sketch that diagram and explain each arrow, you've understood the
project. **Every component exists to serve the arrow.** The arrows are the
product.

### Why each layer exists (not what it is — *why*)

| Layer | The problem it solves |
|-------|------------------------|
| **FastAPI app** | Customers need to browse and buy. This is the *source of all data*. |
| **PostgreSQL** | Transactional integrity: an order, a payment, and a stock movement must commit atomically. OLAP systems can't do this. |
| **Cube.dev** | The analyst's SQL and the dashboard's SQL drift apart. Cube is the *one* place revenue is defined. |
| **Airflow** | Data goes stale. Airflow is the heartbeat that keeps the warehouse fresh and the forecast retrained. |
| **BigQuery** | A long cohort query on Postgres locks pages and slows checkout. BigQuery has its own compute. |
| **Looker Studio** | Founders read the dashboard on their phone over coffee. You don't host that yourself. |
| **Prophet ML** | "How much will we sell next month" is a 30-second answer if you've already built this. Otherwise it's a 3-week project. |
| **Presentation** | Numbers don't change minds. *Stories* change minds. The deck is the artifact a non-technical room actually decides on. |

---

## Part 2 — End-to-end use, in order

Run these in sequence the first time. Each step verifies the one before it.

### Step 1 — Bring up the local stack (3 min)
```bash
make dev          # env + postgres + cube + seed
make app          # leave this running
make smoke        # in another terminal — should be 22 / 22 green
```

**What you've just shown:** a real FastAPI ecommerce app with 31k orders of
realistic seeded data, sitting on Postgres, with Cube.dev as the semantic
layer. The smoke test proves every endpoint works.

### Step 2 — Walk the storefront (1 min)
- Open `http://localhost:8000/` → home page, categories, featured products
- Open `http://localhost:8000/catalog` → product grid, filter by category
- Open `http://localhost:8000/docs` → FastAPI Swagger UI

**What you've just shown:** this isn't a mock. It's a real ecommerce backend
with a usable API.

### Step 3 — In-app dashboards (3 min)
- `http://localhost:8000/dashboards/sales` — KPI scoreboard, daily revenue chart,
  channel breakdown, category margin, top 10 products table.
- `http://localhost:8000/dashboards/inventory` — funnel, cart abandonment,
  stockout-risk table, slow movers, demand forecast chart.

**What you've just shown:** the dashboards are part of the app, not a separate
tool. The user logs in and sees them. Cube.dev runs the queries; if Cube is
down the REST API falls back transparently.

### Step 4 — Cube.dev playground (2 min)
- Open `http://localhost:4000`
- Pick measures `Orders.revenue`, `Orders.count` and time-dimension `Orders.placedAt`
  with daily granularity, last 90 days.
- Hit "Run query."

**What you've just shown:** the same `Orders.revenue` measure that the app
uses is queryable by an analyst with no SQL. **Numbers always reconcile**
because they come from one source.

### Step 5 — Run the forecast (90 sec)
```bash
make forecast
```
Then reload the inventory dashboard. The forecast chart now reflects your data.

```bash
cat ml/forecast_metrics.json
```
**What you've just shown:** the Prophet model, walk-forward back-tested with
MAPE and 80% interval coverage. Not a toy — a model you can defend.

### Step 6 — Airflow (optional, if you started it)
```bash
make airflow
# http://localhost:8080 — admin/admin
```
Show the two DAGs. Click `forecast_retrain_daily` → graph view → explain that
every night it pulls 18 months of revenue from BigQuery, fits a model per
category, writes the forecast *back* to BigQuery, and exports the JSON the
app reads.

**What you've just shown:** the ML doesn't live in a notebook. It's a scheduled
job that closes the loop.

### Step 7 — The board deck (4 min)
```bash
open docs/presentation/deck.html
```
Walk through the 11 slides, hitting the four key moments:
1. **Slide 2:** "Growing — but the growth is concentrated"
2. **Slide 5:** "10% of products → 60% of revenue. $48k tied in slow movers."
3. **Slide 7:** "Cart-to-checkout: 1 percentage point = $35k/month"
4. **Slide 10:** "We're asking the board to approve two things."

**What you've just shown:** the analytical work was in service of a decision.
The deck *is* the deliverable, not an afterthought.

### Total demo time: ~15 minutes for the full path.

---

## Part 3 — How to present, by audience

### For a technical audience (engineers, data team, interviewer)

**Hook:** "End-to-end analytics platform. OLTP, warehouse, semantic layer,
orchestration, ML, dashboards, and a board deck — all consistent."

**What to dwell on:**
- The schema choices: snapshotting `unit_cost` on order items for margin truth
- The seed strategy: Zipf product distribution + holiday seasonality baked in
  so the forecast has signal to learn
- The OLTP/OLAP split: Postgres for writes, BigQuery for analysis, Cube as
  the bridge
- Idempotent ETL via partition-delete-and-insert (cheaper than MERGE)
- The bug fixes during build: `DateTime(timezone=True)` and `values_callable`
  for enums — *show that you debug from first principles*

**Tough questions you'll get and good answers:**

| Q | A |
|---|---|
| Why Prophet not LightGBM? | "Interpretability matters for forecasts a CFO uses. Prophet's components — trend, weekly, yearly — are inspectable. I'd graduate to LightGBM when we add external regressors and have the team to maintain it." |
| Why Cube.dev not dbt? | "Different jobs. dbt models the warehouse. Cube exposes a semantic API for dashboards. They compose — Cube can sit on top of dbt-managed BigQuery tables." |
| Why not Snowflake / Databricks? | "Cost. For < 1 TB/month BigQuery on-demand pricing is free-tier-adjacent. We can swap at scale." |
| What's the cost? | "~$30/month if you swap Composer for Cloud Scheduler + Cloud Run Jobs. Postgres dominates the bill." |
| What would you change? | "Three things: dbt or Dataform for the warehouse transforms (right now they're raw SQL files); a real auth layer in front of the app and Cube; and the forecast should accept the promo calendar as a known regressor so it stops getting blown out by sales." |

### For a business / non-technical audience

**Hook:** Don't talk about the stack. Tell the story.

"I built a system that turns the noise of every order, every click, and every
abandoned cart into three numbers a CFO can act on tomorrow morning."

**Walk only these:**
1. The board deck (`deck.html`) — front to back
2. The Sales dashboard — point at the KPI scoreboard
3. The forecast chart on the Inventory dashboard — say "this is updated every night"

**Don't show:** Airflow, Cube playground, the code. They'll dilute the point.

**What to emphasize:**
- The deck has *one ask per slide* — that's deliberate
- The forecast has a *band*, not a line — that's deliberate
- The dashboard has *one accent colour* — that's deliberate
- All three are information-design principles, not aesthetic preferences

### For a hybrid audience (typical interview / demo day)

Open and close with the business framing. Spend the middle on the
technical depth. Specifically:

```
0:00 – 1:00   The problem and the headline insight (deck slide 2)
1:00 – 4:00   Walk the in-app dashboards
4:00 – 8:00   Open the code: schema, Cube model, Airflow DAG, ML script
              (1 minute each — don't linger)
8:00 – 12:00  The board deck end-to-end
12:00 – 15:00 Q&A
```

The structure is **insight → tour → insight**. Numbers bookend the code.

---

## Part 4 — The four "wow" moments

These are the points where the audience should think *"oh, that's not what I
expected."* Plant them deliberately.

1. **The seed data has structure.** When showing top products: "Notice 12 SKUs
   do 60% of revenue. That's not random — I seeded it with a Zipf distribution
   on purpose. Without that, every analysis would look flat and the ML would
   learn nothing."

2. **One semantic layer, two consumers.** When opening Cube playground: "This
   `Orders.revenue` measure is the same one the app's dashboard uses *and* the
   one an analyst would point Looker Studio at. There is exactly one place
   revenue is defined."

3. **The forecast writes back.** When showing Airflow: "The Prophet job
   doesn't just produce a number — it writes the forecast into the warehouse
   as a fact table. So the next morning's Looker Studio report shows actuals
   *and* forecast side by side, with no glue code."

4. **Information design isn't decoration.** When showing the dashboard CSS:
   "I picked one accent colour and a single neutral palette deliberately.
   Most dashboards die from chartjunk. The constraint *is* the design."

---

## Part 5 — Likely failure modes during the demo

| What can go wrong | Fix |
|-------------------|-----|
| Docker not running | `docker compose up -d postgres cube` |
| Old (broken) seed | `make seed` again — it's `--reset` |
| Forecast chart empty | `make forecast` |
| Airflow returns "Request Header Fields Too Large" | Use incognito or `http://127.0.0.1:8080` |
| Cube playground shows no schemas | Restart Cube container; check `/cube/conf/model/*.js` mounted |
| Browser caches old dashboard | Hard reload (Ctrl-Shift-R) — Jinja templates aren't cached but JS is |

---

## Part 6 — The 60-second elevator pitch

Memorize this. It's the entire project in one paragraph.

> "I built an ecommerce platform end-to-end: a FastAPI storefront with a real
> Postgres backend, seeded with 31,000 realistic orders that have seasonality
> and Zipf-distributed product sales baked in. Airflow ships hourly snapshots
> to BigQuery where a star schema feeds Looker Studio for the executive
> reports. Cube.dev sits over Postgres as a semantic layer so the same
> revenue measure powers the in-app dashboards and the analyst's queries.
> A nightly Prophet job retrains a demand forecast, writes it back to the
> warehouse, and the inventory dashboard reads it. The whole thing closes
> with a board deck — the story the data is telling, in plain English, with
> a single ask. It costs about $30 a month on GCP."

That's it. Land that and the rest is detail.
