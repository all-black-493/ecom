# Cube.dev — sample queries

Open http://localhost:4000 (Cube playground) and try these. Each query
maps directly to one of the questions in `docs/analytics-questions.md`.

## Q1 — Daily revenue (90 days)

```json
{
  "measures": ["Orders.revenue", "Orders.count"],
  "timeDimensions": [{
    "dimension": "Orders.placedAt",
    "granularity": "day",
    "dateRange": "last 90 days"
  }]
}
```

## Q2 — Top 10 SKUs by revenue (30 days)

```json
{
  "measures": ["OrderItems.revenue", "OrderItems.units", "OrderItems.grossMargin"],
  "dimensions": ["Products.sku", "Products.name", "Products.brand"],
  "timeDimensions": [{
    "dimension": "Orders.placedAt",
    "dateRange": "last 30 days"
  }],
  "order": { "OrderItems.revenue": "desc" },
  "limit": 10
}
```

## Q3 — Gross margin by category (30 days)

```json
{
  "measures": ["OrderItems.revenue", "OrderItems.grossMargin", "OrderItems.marginPct"],
  "dimensions": ["Products.categoryName"],
  "timeDimensions": [{
    "dimension": "Orders.placedAt",
    "dateRange": "last 30 days"
  }],
  "order": { "OrderItems.grossMargin": "desc" }
}
```

## Q4 — AOV by device

```json
{
  "measures": ["Orders.aov", "Orders.count"],
  "dimensions": ["Orders.deviceType"],
  "timeDimensions": [{
    "dimension": "Orders.placedAt",
    "dateRange": "last 30 days"
  }]
}
```

## Q5 — Cart abandonment

```json
{
  "measures": ["Carts.abandonmentRate", "Carts.abandoned", "Carts.count"],
  "timeDimensions": [{
    "dimension": "Carts.createdAt",
    "dateRange": "last 30 days"
  }]
}
```
