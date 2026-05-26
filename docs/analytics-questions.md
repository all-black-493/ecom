# Analytics questions

This is the **specification** that the warehouse, reports, and ML model are
built to answer. Each question has:

* **Who asks it** — the persona / role
* **Cadence** — how often the answer matters
* **Decision it drives** — analytics that doesn't change a decision is decoration
* **Source mart** — which warehouse model serves it
* **Failure mode** — what people get wrong when they look at this number

---

## Group 1 — Revenue & sales velocity

### Q1. What is our daily revenue, and how does it compare to the prior period?
- **Asker:** Founder / CFO
- **Cadence:** Daily, 9:00 AM
- **Decision:** Whether to escalate (drop > 15% week-over-week), green-light spend
- **Mart:** `fct_orders` → `mart_daily_revenue`
- **Failure mode:** Comparing today vs yesterday in a weekly-seasonal business — always compare same-day-of-week or use 7-day rolling

### Q2. Which products are our fast and slow movers?
- **Asker:** Merchandising
- **Cadence:** Weekly
- **Decision:** Reorder, promote, clear, or de-list
- **Mart:** `fct_order_items` → `mart_product_velocity`
- **Failure mode:** Looking at units instead of revenue or gross-margin contribution — a SKU can be a slow mover by units but a margin hero

### Q3. What is the gross-margin contribution of each category?
- **Asker:** Merchandising / CFO
- **Cadence:** Monthly
- **Decision:** Where to invest catalog effort, which categories to expand
- **Mart:** `mart_category_pnl`
- **Failure mode:** Comparing categories on revenue when their margin profile differs by 20 points

### Q4. How does AOV (average order value) differ by device and channel?
- **Asker:** Growth / UX
- **Cadence:** Weekly
- **Decision:** Mobile UX investment priority, channel mix optimization
- **Mart:** `fct_orders` → `mart_channel_perf`
- **Failure mode:** AOV averages hide outliers; pair with median

## Group 2 — Customer behaviour & retention

### Q5. What is our cart abandonment rate and how is it trending?
- **Asker:** Growth / UX
- **Cadence:** Weekly
- **Decision:** Trigger checkout-flow optimization or recovery emails
- **Mart:** `fct_carts` → `mart_funnel`
- **Failure mode:** Quoting industry benchmarks without segmenting (mobile vs desktop differ by 15+ points)

### Q6. What is the conversion funnel from product-view to purchase?
- **Asker:** Growth
- **Cadence:** Weekly
- **Decision:** Where to invest UX work — biggest drop wins
- **Mart:** `fct_product_events` → `mart_funnel`
- **Failure mode:** Treating each step as independent; the funnel only makes sense as one user journey

### Q7. What is the repeat-purchase rate over a 90-day window?
- **Asker:** Founder / Growth
- **Cadence:** Monthly
- **Decision:** Retention vs acquisition spend allocation
- **Mart:** `mart_customer_lifecycle`
- **Failure mode:** Counting customers from the seed cohort when they haven't had time to repeat

### Q8. What is the retention curve by monthly acquisition cohort?
- **Asker:** Founder / Growth
- **Cadence:** Monthly
- **Decision:** Spotting cohort degradation (something we did in Q3 broke retention)
- **Mart:** `mart_cohort_retention`
- **Failure mode:** Misreading a young cohort as "worse" when it just hasn't had enough months yet

### Q9. Which acquisition channels deliver the highest LTV-to-CAC?
- **Asker:** Growth / CFO
- **Cadence:** Monthly
- **Decision:** Channel budget allocation
- **Mart:** `mart_channel_perf` (CAC sourced externally)
- **Failure mode:** Using first-order revenue as LTV; you need 6-month cumulative

### Q10. What is the customer lifetime value (LTV) by segment?
- **Asker:** Marketing / Founder
- **Cadence:** Monthly
- **Decision:** What to pay for a customer in each segment
- **Mart:** `mart_customer_lifecycle`
- **Failure mode:** Computing LTV on payers only, ignoring the cost of acquiring the non-payers

## Group 3 — Inventory & operations

### Q11. Which SKUs are at risk of stocking out in the next 14 days?
- **Asker:** Operations
- **Cadence:** Daily
- **Decision:** Trigger expedited purchase orders
- **Mart:** `mart_stockout_risk` (uses ML forecast)
- **Failure mode:** Using lifetime average velocity instead of recent 28-day velocity

### Q12. How much capital is tied up in slow-moving inventory?
- **Asker:** CFO / Operations
- **Cadence:** Monthly
- **Decision:** Markdown campaigns, write-downs
- **Mart:** `mart_inventory_aging`
- **Failure mode:** Counting reserved stock as available

### Q13. What is our order-to-delivery cycle time, broken down by carrier?
- **Asker:** Operations
- **Cadence:** Weekly
- **Decision:** Renegotiate carrier contracts; SLA monitoring
- **Mart:** `mart_fulfillment_sla`
- **Failure mode:** Ignoring orders that haven't shipped (right-censored data)

## Group 4 — Promotions & marketing

### Q14. What is the incremental margin of each promo code, accounting for cannibalization?
- **Asker:** Growth / Merchandising
- **Cadence:** After each campaign
- **Decision:** Renew, retire, or modify a promotion
- **Mart:** `mart_promo_lift`
- **Failure mode:** Crediting the promo for orders that would have happened anyway

### Q15. What is the campaign attribution (last-touch vs first-touch)?
- **Asker:** Marketing
- **Cadence:** Monthly
- **Decision:** Which channels deserve credit
- **Mart:** `mart_attribution`
- **Failure mode:** Reporting only one attribution model and treating it as truth

## Group 5 — Forecasting & advanced analytics

### Q16. What is the expected revenue and unit demand for the next 30 days, top-line and per category?
- **Asker:** Founder / Operations / Finance
- **Cadence:** Daily refresh (Airflow)
- **Decision:** Cash planning, inventory purchasing
- **Mart:** `mart_demand_forecast` (Prophet)
- **Failure mode:** Reporting the point estimate without the confidence interval

### Q17. Which customers are at highest risk of churn (no purchase in 90 days)?
- **Asker:** Retention / CRM
- **Cadence:** Weekly
- **Decision:** Targeted win-back emails
- **Mart:** `mart_churn_risk` (Logistic regression — future iteration)
- **Failure mode:** Defining churn too narrowly (only "active" customers)

### Q18. What product affinities exist — "customers who bought X also bought Y"?
- **Asker:** Merchandising / Personalization
- **Cadence:** Monthly
- **Decision:** Bundle creation, on-site recommendations
- **Mart:** `mart_product_affinity` (Market-basket — future iteration)
- **Failure mode:** Trivial pairs (everyone buys both); use lift not just frequency

---

## What this project ships

The starter implementation answers **Q1–Q12, Q14, Q16** end-to-end:
in-app dashboards (Cube.js), executive reports (Looker Studio), and the
demand-forecast advanced-analytics use case (Q16, Prophet).

Q13, Q15, Q17, Q18 are scaffolded in `docs/dashboard-design.md` and have
warehouse marts defined; the dashboard panels are stubbed but require an
external CAC feed (Q15) and a training run (Q17, Q18) to populate.
