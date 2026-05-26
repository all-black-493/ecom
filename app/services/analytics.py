"""Analytics queries served directly from Postgres for the in-app dashboard.

These queries mirror the warehouse marts so an analyst can validate that
the dashboard agrees with Looker Studio. They are kept deliberately simple
and use SQL window functions where it expresses intent more clearly.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def _date_range(days_back: int) -> tuple[datetime, datetime]:
    end = datetime.now(timezone.utc)
    return end - timedelta(days=days_back), end


def kpi_summary(db: Session, days_back: int = 30) -> dict[str, Any]:
    start, end = _date_range(days_back)
    row = db.execute(
        text(
            """
            SELECT
              COUNT(*)::int                              AS orders,
              COALESCE(SUM(grand_total), 0)::numeric     AS revenue,
              COALESCE(AVG(grand_total), 0)::numeric     AS aov,
              COUNT(DISTINCT customer_id)::int           AS unique_customers
            FROM orders
            WHERE status IN ('paid','fulfilled','shipped','delivered')
              AND placed_at BETWEEN :s AND :e
            """
        ),
        {"s": start, "e": end},
    ).mappings().one()
    return dict(row)


def revenue_by_day(db: Session, days_back: int = 90) -> list[dict]:
    start, end = _date_range(days_back)
    rows = db.execute(
        text(
            """
            SELECT
              date_trunc('day', placed_at)::date AS day,
              SUM(grand_total)::numeric          AS revenue,
              COUNT(*)::int                      AS orders
            FROM orders
            WHERE placed_at BETWEEN :s AND :e
              AND status NOT IN ('cancelled')
            GROUP BY 1
            ORDER BY 1
            """
        ),
        {"s": start, "e": end},
    ).mappings().all()
    return [dict(r) for r in rows]


def top_products(db: Session, days_back: int = 30, limit: int = 10) -> list[dict]:
    start, end = _date_range(days_back)
    rows = db.execute(
        text(
            """
            SELECT
              p.id, p.sku, p.name, p.brand,
              SUM(oi.quantity)::int                                       AS units,
              SUM(oi.quantity * oi.unit_price)::numeric                   AS revenue,
              SUM(oi.quantity * (oi.unit_price - oi.unit_cost))::numeric  AS gross_margin
            FROM order_items oi
            JOIN orders o ON o.id = oi.order_id
            JOIN products p ON p.id = oi.product_id
            WHERE o.placed_at BETWEEN :s AND :e
              AND o.status NOT IN ('cancelled','refunded')
            GROUP BY p.id, p.sku, p.name, p.brand
            ORDER BY revenue DESC
            LIMIT :n
            """
        ),
        {"s": start, "e": end, "n": limit},
    ).mappings().all()
    return [dict(r) for r in rows]


def slow_movers(db: Session, days_back: int = 60, max_units: int = 5) -> list[dict]:
    """Products with <= max_units sold in the window — candidates for clearance."""
    start, end = _date_range(days_back)
    rows = db.execute(
        text(
            """
            WITH sold AS (
              SELECT p.id, COALESCE(SUM(oi.quantity), 0) AS units
              FROM products p
              LEFT JOIN order_items oi ON oi.product_id = p.id
              LEFT JOIN orders o ON o.id = oi.order_id
                AND o.placed_at BETWEEN :s AND :e
                AND o.status NOT IN ('cancelled','refunded')
              WHERE p.is_active
              GROUP BY p.id
            ),
            on_hand AS (
              SELECT pv.product_id, SUM(il.on_hand) AS on_hand
              FROM inventory_levels il
              JOIN product_variants pv ON pv.id = il.variant_id
              GROUP BY pv.product_id
            )
            SELECT p.sku, p.name, p.brand, sold.units::int AS units_sold,
                   COALESCE(oh.on_hand, 0)::int AS on_hand,
                   p.price, p.cost
            FROM products p
            JOIN sold ON sold.id = p.id
            LEFT JOIN on_hand oh ON oh.product_id = p.id
            WHERE sold.units <= :u
            ORDER BY on_hand DESC NULLS LAST, units_sold ASC
            LIMIT 50
            """
        ),
        {"s": start, "e": end, "u": max_units},
    ).mappings().all()
    return [dict(r) for r in rows]


def revenue_by_channel(db: Session, days_back: int = 30) -> list[dict]:
    start, end = _date_range(days_back)
    rows = db.execute(
        text(
            """
            SELECT channel,
                   COUNT(*)::int                AS orders,
                   SUM(grand_total)::numeric    AS revenue,
                   AVG(grand_total)::numeric    AS aov
            FROM orders
            WHERE placed_at BETWEEN :s AND :e
              AND status NOT IN ('cancelled')
            GROUP BY channel
            ORDER BY revenue DESC
            """
        ),
        {"s": start, "e": end},
    ).mappings().all()
    return [dict(r) for r in rows]


def cart_abandonment(db: Session, days_back: int = 30) -> dict[str, Any]:
    start, end = _date_range(days_back)
    row = db.execute(
        text(
            """
            SELECT
              SUM(CASE WHEN status = 'abandoned' THEN 1 ELSE 0 END)::int      AS abandoned,
              SUM(CASE WHEN status = 'converted' THEN 1 ELSE 0 END)::int      AS converted,
              COUNT(*)::int                                                   AS total
            FROM carts
            WHERE created_at BETWEEN :s AND :e
            """
        ),
        {"s": start, "e": end},
    ).mappings().one()
    abandoned = row["abandoned"] or 0
    total = row["total"] or 0
    rate = (abandoned / total) if total else 0
    return {**dict(row), "abandonment_rate": round(rate, 4)}


def repeat_purchase_rate(db: Session, days_back: int = 90) -> dict[str, Any]:
    start, end = _date_range(days_back)
    row = db.execute(
        text(
            """
            WITH cohort AS (
              SELECT customer_id, COUNT(*) AS n_orders
              FROM orders
              WHERE placed_at BETWEEN :s AND :e
                AND status NOT IN ('cancelled')
              GROUP BY customer_id
            )
            SELECT
              COUNT(*) FILTER (WHERE n_orders > 1)::int  AS repeat_customers,
              COUNT(*)::int                              AS total_customers
            FROM cohort
            """
        ),
        {"s": start, "e": end},
    ).mappings().one()
    rep = row["repeat_customers"] or 0
    total = row["total_customers"] or 0
    return {**dict(row), "repeat_rate": round(rep / total, 4) if total else 0}


def cohort_retention(db: Session) -> list[dict]:
    """Monthly cohort table — % of customers from cohort C who bought in month M."""
    rows = db.execute(
        text(
            """
            WITH first_orders AS (
              SELECT customer_id,
                     date_trunc('month', MIN(placed_at))::date AS cohort_month
              FROM orders
              WHERE status NOT IN ('cancelled')
              GROUP BY customer_id
            ),
            activity AS (
              SELECT o.customer_id,
                     fo.cohort_month,
                     date_trunc('month', o.placed_at)::date AS active_month
              FROM orders o
              JOIN first_orders fo ON fo.customer_id = o.customer_id
              WHERE o.status NOT IN ('cancelled')
            )
            SELECT cohort_month,
                   active_month,
                   COUNT(DISTINCT customer_id)::int AS customers
            FROM activity
            GROUP BY 1, 2
            ORDER BY 1, 2
            """
        )
    ).mappings().all()
    return [dict(r) for r in rows]


def aov_by_device(db: Session, days_back: int = 30) -> list[dict]:
    start, end = _date_range(days_back)
    rows = db.execute(
        text(
            """
            SELECT device_type,
                   COUNT(*)::int            AS orders,
                   AVG(grand_total)::numeric AS aov,
                   SUM(grand_total)::numeric AS revenue
            FROM orders
            WHERE placed_at BETWEEN :s AND :e
              AND status NOT IN ('cancelled')
            GROUP BY device_type
            ORDER BY revenue DESC
            """
        ),
        {"s": start, "e": end},
    ).mappings().all()
    return [dict(r) for r in rows]


def gross_margin_by_category(db: Session, days_back: int = 30) -> list[dict]:
    start, end = _date_range(days_back)
    rows = db.execute(
        text(
            """
            SELECT
              c.name AS category,
              SUM(oi.quantity * oi.unit_price)::numeric                              AS revenue,
              SUM(oi.quantity * (oi.unit_price - oi.unit_cost))::numeric             AS gross_margin,
              (SUM(oi.quantity * (oi.unit_price - oi.unit_cost))
                / NULLIF(SUM(oi.quantity * oi.unit_price), 0))::numeric              AS margin_pct
            FROM order_items oi
            JOIN orders o    ON o.id = oi.order_id
            JOIN products p  ON p.id = oi.product_id
            JOIN categories c ON c.id = p.category_id
            WHERE o.placed_at BETWEEN :s AND :e
              AND o.status NOT IN ('cancelled','refunded')
            GROUP BY c.name
            ORDER BY gross_margin DESC
            """
        ),
        {"s": start, "e": end},
    ).mappings().all()
    return [dict(r) for r in rows]


def stockouts_at_risk(db: Session, days_back: int = 28) -> list[dict]:
    """Products selling faster than reorder point would survive — restock urgency."""
    start, end = _date_range(days_back)
    rows = db.execute(
        text(
            """
            WITH velocity AS (
              SELECT pv.id AS variant_id,
                     pv.product_id,
                     COALESCE(SUM(oi.quantity), 0)::float / GREATEST(:d, 1) AS units_per_day
              FROM product_variants pv
              LEFT JOIN order_items oi ON oi.variant_id = pv.id
              LEFT JOIN orders o ON o.id = oi.order_id
                AND o.placed_at BETWEEN :s AND :e
                AND o.status NOT IN ('cancelled','refunded')
              GROUP BY pv.id, pv.product_id
            )
            SELECT p.sku, p.name, pv.size, pv.color,
                   il.on_hand, il.reorder_point,
                   v.units_per_day,
                   (il.on_hand / NULLIF(v.units_per_day, 0))::int AS days_of_cover
            FROM inventory_levels il
            JOIN product_variants pv ON pv.id = il.variant_id
            JOIN products p ON p.id = pv.product_id
            JOIN velocity v ON v.variant_id = pv.id
            WHERE v.units_per_day > 0
              AND (il.on_hand / NULLIF(v.units_per_day, 0)) < 14
            ORDER BY days_of_cover ASC
            LIMIT 50
            """
        ),
        {"s": start, "e": end, "d": days_back},
    ).mappings().all()
    return [dict(r) for r in rows]


def funnel_last_30d(db: Session) -> dict[str, int]:
    start, end = _date_range(30)
    row = db.execute(
        text(
            """
            SELECT
              (SELECT COUNT(*) FROM product_events WHERE event_type='view'
                AND occurred_at BETWEEN :s AND :e)::int                AS views,
              (SELECT COUNT(*) FROM product_events WHERE event_type='add_to_cart'
                AND occurred_at BETWEEN :s AND :e)::int                AS add_to_cart,
              (SELECT COUNT(*) FROM carts
                WHERE status IN ('abandoned','converted')
                AND created_at BETWEEN :s AND :e)::int                 AS started_checkout,
              (SELECT COUNT(*) FROM orders
                WHERE placed_at BETWEEN :s AND :e
                AND status NOT IN ('cancelled'))::int                  AS purchased
            """
        ),
        {"s": start, "e": end},
    ).mappings().one()
    return dict(row)
