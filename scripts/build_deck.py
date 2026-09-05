"""Render docs/presentation/deck.html from live warehouse data.

Every figure in the deck is queried at build time through the same analytics
service the in-app dashboards use, so the board deck and the dashboards can
never disagree. Run with: make deck
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.database import SessionLocal
from app.services import analytics as a

ROOT = Path(__file__).resolve().parents[1]
DECK_DIR = ROOT / "docs" / "presentation"
FORECAST_JSON = ROOT / "app" / "static" / "forecast.json"
METRICS_JSON = ROOT / "ml" / "forecast_metrics.json"

SLOW_WINDOW = 60
SLOW_MAX_UNITS = 5


def money(v, precision: int = 0) -> str:
    return f"${float(v):,.{precision}f}"


def compact_money(v) -> str:
    v = float(v)
    if abs(v) >= 1_000_000:
        return f"${v / 1_000_000:.1f}M"
    if abs(v) >= 1_000:
        return f"${v / 1_000:.0f}k"
    return f"${v:,.0f}"


def pct(part, whole, precision: int = 1) -> float:
    return round(float(part) / float(whole) * 100, precision) if whole else 0.0


def delta(current, prior) -> dict:
    current, prior = float(current), float(prior)
    change = pct(current - prior, prior) if prior else 0.0
    up = change >= 0
    return {
        "delta_pct": abs(round(change, 1)),
        "arrow": "▲" if up else "▼",
        "direction": "is up" if up else "is down",
        "direction_class": "up" if up else "down",
    }


def bar_chart(rows, label_key, value_key, fmt=compact_money, width: int = 18) -> str:
    if not rows:
        return "(no data)"
    top = max(float(r[value_key]) for r in rows) or 1
    label_w = max(len(str(r[label_key])) for r in rows)
    value_w = max(len(fmt(r[value_key])) for r in rows)
    return "\n".join(
        "{label:<{lw}}  {bar:<{bw}}  {value:>{vw}}".format(
            label=r[label_key],
            bar="█" * max(1, round(float(r[value_key]) / top * width)),
            value=fmt(r[value_key]),
            lw=label_w,
            bw=width,
            vw=value_w,
        )
        for r in rows
    )


def sparkline(values, width: int = 56) -> str:
    """Single-row block sparkline — legible in monospace and in print."""
    if not values:
        return "(no forecast)"
    blocks = "▁▂▃▄▅▆▇█"
    step = max(1, len(values) // width)
    pts = values[::step][:width]
    lo, hi = min(pts), max(pts)
    span = (hi - lo) or 1
    line = "".join(blocks[min(len(blocks) - 1, int((v - lo) / span * len(blocks)))] for v in pts)
    return (
        f"peak {compact_money(hi)}\n"
        f"{line}\n"
        f"trough {compact_money(lo)}\n"
        f"└{'─' * (len(pts) - 1)}► next {len(values)} days"
    )


def build_context(db, days: int) -> dict:
    current = a.kpi_summary(db, days)
    prior = a.kpi_summary(db, days, offset_days=days)
    repeat = a.repeat_purchase_rate(db, 90)
    repeat_prior = a.repeat_purchase_rate(db, 90, offset_days=90)

    channels = a.revenue_by_channel(db, days)
    channel_total = sum(float(c["revenue"]) for c in channels) or 1
    for c in channels:
        c["share"] = pct(c["revenue"], channel_total)
        c["revenue_fmt"] = money(c["revenue"])
        c["aov_fmt"] = money(c["aov"], 2)
    top_n = min(3, len(channels))
    channel_top_share = round(sum(c["share"] for c in channels[:top_n]), 1)

    products = a.top_products(db, days, limit=10)
    product_revenue_total = float(current["revenue"]) or 1
    product_top_n = min(10, len(products))
    product_top_share = pct(
        sum(float(p["revenue"]) for p in products[:product_top_n]), product_revenue_total
    )

    slow = a.slow_movers(db, SLOW_WINDOW, SLOW_MAX_UNITS)
    slow_capital = sum(float(s["on_hand"]) * float(s["cost"]) for s in slow)

    best_aov = max(channels, key=lambda c: float(c["aov"]))

    margins = a.gross_margin_by_category(db, days)

    funnel = a.funnel_last_30d(db)
    steps = [
        ("Product views", funnel["views"]),
        ("Added to cart", funnel["add_to_cart"]),
        ("Purchased", funnel["purchased"]),
    ]
    base = steps[0][1] or 1
    funnel_rows = [{"step": n, "n": v, "share": pct(v, base)} for n, v in steps]
    drops = [
        (f"{steps[i][0].lower()} → {steps[i + 1][0].lower()}", pct(steps[i][1] - steps[i + 1][1], steps[i][1]))
        for i in range(len(steps) - 1)
    ]
    worst_step, worst_loss = max(drops, key=lambda d: d[1])
    aov = float(current["aov"])
    point_value = base * 0.01 * (steps[2][1] / steps[1][1] if steps[1][1] else 0) * aov

    forecast = json.loads(FORECAST_JSON.read_text())
    metrics = json.loads(METRICS_JSON.read_text())
    yhat = [float(r["yhat"]) for r in forecast]

    return {
        "days": days,
        "generated_at": datetime.now(UTC).strftime("%d %B %Y"),
        "window_label": f"{days} days ending {datetime.now(UTC):%d %B %Y}",
        "headline": (
            f"We're {'growing' if float(current['revenue']) >= float(prior['revenue']) else 'contracting'}"
            " — and the revenue is concentrated."
        ),
        "kpi": {
            "revenue": {"value": money(current["revenue"]), **delta(current["revenue"], prior["revenue"])},
            "aov": {"value": money(current["aov"], 2)},
        },
        "kpi_cards": [
            {"label": "Revenue", "value": compact_money(current["revenue"]), "basis": days,
             **delta(current["revenue"], prior["revenue"])},
            {"label": "Orders", "value": f"{current['orders']:,}", "basis": days,
             **delta(current["orders"], prior["orders"])},
            {"label": "Repeat purchase rate (90d)", "basis": 90,
             "value": f"{repeat['repeat_rate'] * 100:.1f}%",
             **delta(repeat["repeat_rate"], repeat_prior["repeat_rate"])},
        ],
        "channels": channels,
        "channel_top_n": top_n,
        "channel_top_share": channel_top_share,
        "channel_best_aov": best_aov,
        "channel_chart": bar_chart(channels, "channel", "revenue"),
        "product_top_n": product_top_n,
        "product_top_share": product_top_share,
        "product_chart": bar_chart(
            [{"sku": p["sku"], "revenue": p["revenue"]} for p in products], "sku", "revenue"
        ),
        "product_count": len(products),
        "slow_count": len(slow),
        "slow_capital": compact_money(slow_capital),
        "slow_window": SLOW_WINDOW,
        "slow_max_units": SLOW_MAX_UNITS,
        "margin_chart": bar_chart(margins, "category", "gross_margin"),
        "margin_note": (
            f"{margins[0]['category']} leads on gross margin at {money(margins[0]['gross_margin'])}."
            if margins else "No category margin recorded in this window."
        ),
        "funnel_headline": f"{100 - funnel_rows[-1]['share']:.0f} in 100 shoppers never buy.",
        "funnel_chart": bar_chart(
            funnel_rows, "step", "share", fmt=lambda v: f"{float(v):.1f}%", width=20
        ),
        "funnel_worst_step": worst_step,
        "funnel_worst_loss": round(worst_loss, 1),
        "funnel_point_value": compact_money(point_value),
        "forecast_chart": sparkline(yhat),
        "forecast_days": len(forecast),
        "forecast_total": compact_money(sum(yhat)),
        "forecast_low": compact_money(sum(float(r["yhat_lower"]) for r in forecast)),
        "forecast_high": compact_money(sum(float(r["yhat_upper"]) for r in forecast)),
        "metrics": {
            "n_splits": metrics["n_splits"],
            "mape_pct": round(metrics["mape_top_line_mean"] * 100, 1),
            "coverage_pct": round(metrics["coverage_80_mean"] * 100, 1),
        },
        "asks": [
            {
                "what": f"Fix the {worst_step} step",
                "why": f"Largest funnel drop at {worst_loss:.0f}%",
                "impact": f"{compact_money(point_value)} per point, per {days} days",
            },
            {
                "what": "Slow-mover clearance",
                "why": f"{len(slow)} products under {SLOW_MAX_UNITS} units in {SLOW_WINDOW} days",
                "impact": f"Frees {compact_money(slow_capital)} at cost",
            },
            {
                "what": f"Shift spend toward {best_aov['channel']}",
                "why": f"Highest AOV at {best_aov['aov_fmt']} vs {money(aov, 2)} book",
                "impact": f"{money((float(best_aov['aov']) - aov) * 100)} per 100 orders shifted",
            },
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--out", type=Path, default=DECK_DIR / "deck.html")
    args = parser.parse_args()

    env = Environment(
        loader=FileSystemLoader(DECK_DIR), undefined=StrictUndefined, autoescape=False
    )
    with SessionLocal() as db:
        context = build_context(db, args.days)

    args.out.write_text(env.get_template("deck.html.j2").render(**context))
    print(f"wrote {args.out.relative_to(ROOT)} — {context['window_label']}")


if __name__ == "__main__":
    main()
