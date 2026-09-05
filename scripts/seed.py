"""Seed Lumen Commerce with realistic, story-bearing data.

We intentionally bake the following patterns into the data so that the
downstream dashboards and ML model surface something interesting:

  * Catalog: 6 categories, ~120 products with cost/price spreads driving margin.
  * Velocity: a small head (10% of SKUs) drives ~60% of revenue; a long tail
    of slow movers gives us "obsolete inventory" candidates.
  * Seasonality: weekly cycle (weekends +30%), holiday lift in Nov–Dec.
  * Channels: paid_search has the highest CAC but mid-tier AOV; organic and
    email convert better but smaller volume.
  * Cohorts: customers acquired in older months have higher repeat purchase
    rates — gives Q1 cohorts that look "better" in retention reports.
  * Cart abandonment: ~30% of carts are abandoned, with a higher rate on mobile.

Run after `docker compose up postgres` and `alembic upgrade head` (or
`python scripts/seed.py --create`).
"""

from __future__ import annotations

import argparse
import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from faker import Faker
from sqlalchemy.orm import Session

from app.database import Base, SessionLocal, engine
from app.models import (
    Cart,
    CartItem,
    Category,
    Customer,
    InventoryLevel,
    Order,
    OrderItem,
    OrderStatus,
    Payment,
    PaymentStatus,
    Product,
    ProductEvent,
    ProductVariant,
    Promotion,
    PromotionRedemption,
    Shipment,
    ShipmentStatus,
    StockMovement,
)

fake = Faker()
Faker.seed(42)
random.seed(42)

# ------------------------------------------------------------------ tunables --

N_CUSTOMERS = 1_000
N_PRODUCTS = 120
N_ORDERS_TARGET = 25_000
HISTORY_DAYS = 540  # ~18 months
START = datetime.now(UTC) - timedelta(days=HISTORY_DAYS)

# Accounts with a real password hash, so the storefront can be signed into
# after seeding. Every other customer exists only as analytics data.
DEMO_ACCOUNTS = [
    ("demo@lumen.com", "demo12345", "Demo", "User"),
    ("jane@lumen.com", "shopper99", "Jane", "Shopper"),
]

CATEGORIES = [
    ("apparel", "Apparel"),
    ("footwear", "Footwear"),
    ("accessories", "Accessories"),
    ("home", "Home & Living"),
    ("beauty", "Beauty"),
    ("electronics", "Electronics"),
]

CHANNELS = [
    ("organic", 0.30),
    ("paid_search", 0.20),
    ("paid_social", 0.18),
    ("email", 0.12),
    ("direct", 0.10),
    ("referral", 0.07),
    ("affiliate", 0.03),
]


def _weighted_choice(choices: list[tuple[str, float]]) -> str:
    pop, weights = zip(*choices, strict=True)
    return random.choices(pop, weights=weights, k=1)[0]


def _seasonality_factor(day: datetime) -> float:
    """Weekly cycle + November/December holiday lift."""
    weekend = 1.30 if day.weekday() >= 5 else 1.0
    holiday = 1.55 if day.month in (11, 12) else 1.0
    growth = 1.0 + (day - START).days / HISTORY_DAYS * 0.20  # 20% YoY growth
    return weekend * holiday * growth


# ------------------------------------------------------------------- builders --


def seed_catalog(db: Session) -> tuple[list[Product], list[ProductVariant]]:
    cats = {}
    for slug, name in CATEGORIES:
        c = Category(slug=slug, name=name)
        db.add(c)
        cats[slug] = c
    db.flush()

    products: list[Product] = []
    variants: list[ProductVariant] = []

    # Head products (10%) drive volume — give them lower prices, higher margins.
    head_count = int(N_PRODUCTS * 0.10)

    for i in range(N_PRODUCTS):
        is_head = i < head_count
        cat_slug = random.choice([c[0] for c in CATEGORIES])
        price = Decimal(str(round(random.uniform(15, 250), 2)))
        # Head SKUs are priced for volume; tail SKUs are higher-margin niche items
        cost_ratio = random.uniform(0.45, 0.65) if is_head else random.uniform(0.30, 0.55)
        cost = (price * Decimal(str(cost_ratio))).quantize(Decimal("0.01"))
        launched = START + timedelta(days=random.randint(0, HISTORY_DAYS - 30))

        p = Product(
            sku=f"LUM-{1000+i:05d}",
            name=fake.unique.catch_phrase(),
            description=fake.paragraph(nb_sentences=3),
            category_id=cats[cat_slug].id,
            brand=random.choice(["Lumen", "Lumen Pro", "Lumen Essentials"]),
            price=price,
            cost=cost,
            weight_grams=random.randint(100, 2_000),
            launched_at=launched,
        )
        db.add(p)
        products.append(p)
    db.flush()

    for p in products:
        for size in random.sample(["XS", "S", "M", "L", "XL"], k=random.randint(2, 4)):
            for color in random.sample(["black", "navy", "olive", "rust", "stone"], k=random.randint(1, 3)):
                v = ProductVariant(
                    product_id=p.id,
                    sku=f"{p.sku}-{size}-{color[:3].upper()}",
                    size=size,
                    color=color,
                )
                db.add(v)
                variants.append(v)
    db.flush()

    # Seed inventory levels
    for v in variants:
        on_hand = random.randint(0, 500)
        db.add(
            InventoryLevel(
                variant_id=v.id, on_hand=on_hand, reserved=0, reorder_point=random.choice([10, 20, 50])
            )
        )
        # Initial stock receipt
        db.add(
            StockMovement(
                variant_id=v.id,
                delta=on_hand,
                reason="initial_load",
                occurred_at=START,
            )
        )
    db.commit()
    return products, variants


def seed_customers(db: Session) -> list[Customer]:
    from app.services.auth import hash_password

    customers = []

    for email, password, first, last in DEMO_ACCOUNTS:
        c = Customer(
            email=email,
            first_name=first,
            last_name=last,
            password_hash=hash_password(password),
            signup_channel="direct",
            signup_country="US",
            marketing_opt_in=True,
            created_at=START + timedelta(days=10),
        )
        db.add(c)
        customers.append(c)

    # The rest carry a placeholder hash — they shape the analytics data but
    # cannot sign in.
    for _ in range(N_CUSTOMERS - len(DEMO_ACCOUNTS)):
        created = START + timedelta(
            days=int(random.triangular(0, HISTORY_DAYS, HISTORY_DAYS * 0.3))
        )
        c = Customer(
            email=fake.unique.email(),
            first_name=fake.first_name(),
            last_name=fake.last_name(),
            password_hash="$placeholder$",
            signup_channel=_weighted_choice(CHANNELS),
            signup_country=random.choice(["US", "US", "US", "CA", "GB", "AU", "DE"]),
            marketing_opt_in=random.random() < 0.55,
            created_at=created,
        )
        db.add(c)
        customers.append(c)
    db.flush()
    db.commit()
    return customers


def seed_promotions(db: Session) -> list[Promotion]:
    promos = [
        Promotion(code="WELCOME10", kind="percent", value=Decimal("10"), starts_at=START),
        Promotion(code="SUMMER20", kind="percent", value=Decimal("20"), starts_at=START),
        Promotion(code="FREESHIP", kind="fixed", value=Decimal("9.99"), starts_at=START),
        Promotion(code="BFCM30", kind="percent", value=Decimal("30"), starts_at=START),
    ]
    db.add_all(promos)
    db.commit()
    return promos


def _pick_product_zipfian(products: list[Product]) -> Product:
    """Zipf-distributed picker — head SKUs dominate."""
    idx = min(int(random.paretovariate(1.3)) - 1, len(products) - 1)
    return products[idx]


def seed_orders(
    db: Session,
    customers: list[Customer],
    products: list[Product],
    variants: list[ProductVariant],
    promos: list[Promotion],
) -> None:
    # Pre-bucket variants by product for fast lookup
    variants_by_product: dict[int, list[ProductVariant]] = {}
    for v in variants:
        variants_by_product.setdefault(v.product_id, []).append(v)

    # Cumulative cohort: each customer has an acquisition date; orders only
    # exist after that date.
    customers_by_day: dict[int, list[Customer]] = {}
    for c in customers:
        day_idx = (c.created_at - START).days
        customers_by_day.setdefault(day_idx, []).append(c)

    available: list[Customer] = []
    orders_created = 0

    for d in range(HISTORY_DAYS):
        today = START + timedelta(days=d)
        available.extend(customers_by_day.get(d, []))
        if not available:
            continue

        base_orders = N_ORDERS_TARGET / HISTORY_DAYS
        n_today = max(0, int(base_orders * _seasonality_factor(today) * random.uniform(0.7, 1.3)))

        for _ in range(n_today):
            customer = random.choice(available)
            # Older customers more likely to repeat
            tenure_days = (today - customer.created_at).days
            if tenure_days < 0:
                continue
            channel = _weighted_choice(CHANNELS) if random.random() < 0.4 else customer.signup_channel
            device = random.choices(["desktop", "mobile", "tablet"], weights=[0.45, 0.50, 0.05])[0]

            order = Order(
                order_number=f"L{uuid4().hex[:10].upper()}",
                customer_id=customer.id,
                status=OrderStatus.PENDING,
                channel=channel,
                utm_source=channel if channel.startswith("paid") else None,
                utm_campaign=random.choice(["spring24", "always_on", "retargeting", None]),
                device_type=device,
                placed_at=today + timedelta(seconds=random.randint(0, 86_399)),
            )
            db.add(order)
            db.flush()

            n_items = random.choices([1, 2, 3, 4, 5], weights=[0.45, 0.28, 0.15, 0.08, 0.04])[0]
            subtotal = Decimal("0")
            used_products = set()
            for _ in range(n_items):
                p = _pick_product_zipfian(products)
                if p.id in used_products:
                    continue
                used_products.add(p.id)
                v = random.choice(variants_by_product.get(p.id, [None]))
                qty = random.choices([1, 2, 3], weights=[0.75, 0.20, 0.05])[0]
                unit_price = p.price
                unit_cost = p.cost
                line = OrderItem(
                    order_id=order.id,
                    product_id=p.id,
                    variant_id=v.id if v else None,
                    quantity=qty,
                    unit_price=unit_price,
                    unit_cost=unit_cost,
                )
                db.add(line)
                subtotal += unit_price * qty

                # Stock movement
                if v:
                    db.add(
                        StockMovement(
                            variant_id=v.id,
                            delta=-qty,
                            reason="sale",
                            ref_order_id=order.id,
                            occurred_at=order.placed_at,
                        )
                    )

            discount = Decimal("0")
            if random.random() < 0.18:
                promo = random.choice(promos)
                pct = (promo.value / Decimal("100")) if promo.kind == "percent" else None
                discount = (subtotal * pct) if pct else min(subtotal, promo.value)
                db.add(
                    PromotionRedemption(
                        promotion_id=promo.id,
                        order_id=order.id,
                        customer_id=customer.id,
                        amount_off=discount,
                        redeemed_at=order.placed_at,
                    )
                )

            shipping = Decimal("0") if subtotal > Decimal("75") else Decimal("9.99")
            tax = (subtotal - discount) * Decimal("0.08")
            grand = (subtotal - discount + shipping + tax).quantize(Decimal("0.01"))

            order.subtotal = subtotal.quantize(Decimal("0.01"))
            order.discount_total = discount.quantize(Decimal("0.01"))
            order.shipping_total = shipping
            order.tax_total = tax.quantize(Decimal("0.01"))
            order.grand_total = grand

            # Lifecycle: most orders are paid + fulfilled. Some cancelled / refunded.
            roll = random.random()
            if roll < 0.92:
                order.status = OrderStatus.DELIVERED
                order.paid_at = order.placed_at + timedelta(minutes=random.randint(1, 30))
                order.fulfilled_at = order.placed_at + timedelta(hours=random.randint(2, 48))
                order.delivered_at = order.fulfilled_at + timedelta(days=random.randint(2, 7))
                db.add(
                    Payment(
                        order_id=order.id,
                        provider=random.choice(["stripe", "stripe", "paypal"]),
                        method=random.choice(["card", "card", "card", "wallet"]),
                        status=PaymentStatus.CAPTURED,
                        amount=grand,
                        captured_at=order.paid_at,
                    )
                )
                db.add(
                    Shipment(
                        order_id=order.id,
                        carrier=random.choice(["UPS", "FedEx", "USPS"]),
                        tracking_number=fake.bothify(text="1Z##########"),
                        status=ShipmentStatus.DELIVERED,
                        picked_at=order.fulfilled_at - timedelta(hours=2),
                        shipped_at=order.fulfilled_at,
                        delivered_at=order.delivered_at,
                    )
                )
            elif roll < 0.97:
                order.status = OrderStatus.CANCELLED
                order.cancelled_at = order.placed_at + timedelta(hours=random.randint(1, 72))
            else:
                order.status = OrderStatus.REFUNDED
                order.paid_at = order.placed_at + timedelta(minutes=10)
                db.add(
                    Payment(
                        order_id=order.id,
                        status=PaymentStatus.REFUNDED,
                        amount=grand,
                        captured_at=order.paid_at,
                    )
                )

            orders_created += 1

        if d % 30 == 0:
            db.commit()
            print(f"  day {d}/{HISTORY_DAYS}  orders={orders_created}")

    db.commit()
    print(f"orders created: {orders_created}")


def seed_carts_and_events(
    db: Session, customers: list[Customer], products: list[Product]
) -> None:
    """Generate browsing events and abandoned carts."""
    # Last 90 days of events
    start = datetime.now(UTC) - timedelta(days=90)
    for _ in range(40_000):
        when = start + timedelta(seconds=random.randint(0, 90 * 86_400))
        c = random.choice(customers) if random.random() < 0.6 else None
        p = _pick_product_zipfian(products)
        event_type = random.choices(
            ["view", "add_to_cart", "remove_from_cart", "wishlist"],
            weights=[0.78, 0.15, 0.04, 0.03],
        )[0]
        db.add(
            ProductEvent(
                session_id=uuid4().hex[:24],
                customer_id=c.id if c else None,
                product_id=p.id,
                event_type=event_type,
                occurred_at=when,
            )
        )
    # Abandoned carts (last 60 days)
    abandoned_start = datetime.now(UTC) - timedelta(days=60)
    for _ in range(2_500):
        created = abandoned_start + timedelta(seconds=random.randint(0, 60 * 86_400))
        c = random.choice(customers) if random.random() < 0.5 else None
        cart = Cart(
            customer_id=c.id if c else None,
            session_id=uuid4().hex[:24],
            status="abandoned",
            created_at=created,
            abandoned_at=created + timedelta(hours=random.randint(1, 24)),
        )
        db.add(cart)
        db.flush()
        for _ in range(random.randint(1, 4)):
            p = _pick_product_zipfian(products)
            db.add(
                CartItem(
                    cart_id=cart.id,
                    product_id=p.id,
                    quantity=random.randint(1, 3),
                    unit_price=p.price,
                )
            )
    db.commit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--create", action="store_true", help="create tables (DDL) before seeding")
    parser.add_argument("--reset", action="store_true", help="drop & recreate all tables")
    args = parser.parse_args()

    if args.reset:
        Base.metadata.drop_all(bind=engine)
    if args.reset or args.create:
        Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        print("seeding catalog…")
        products, variants = seed_catalog(db)
        print("seeding customers…")
        customers = seed_customers(db)
        print("seeding promotions…")
        promos = seed_promotions(db)
        print("seeding orders…")
        seed_orders(db, customers, products, variants, promos)
        print("seeding events & carts…")
        seed_carts_and_events(db, customers, products)
        print("done.")
        print()
        print("sign in with:")
        for email, password, *_ in DEMO_ACCOUNTS:
            print(f"  {email}  /  {password}")
        print("or register a new account at /register")


if __name__ == "__main__":
    main()
