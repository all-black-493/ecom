"""Synthetic shopper traffic for Lumen Commerce.

Mirrors the seed's statistical model but generates traffic *now* so the
dashboards refresh as real-looking activity happens. Three user shapes:

    Shopper   — 80% of population. Browses heavily, buys occasionally.
    Buyer     — 15%. Has higher intent: skips browsing, goes to checkout.
    Bouncer   — 5%. Views one page then leaves (drives abandonment).

Usage:

    # Web UI on :8089 (easy to start/stop, see live charts)
    locust -f scripts/locustfile.py --host=http://localhost:8000

    # Headless burst: 30 users, 5/sec ramp, 5 minutes
    locust -f scripts/locustfile.py --host=http://localhost:8000 \\
      --users 30 --spawn-rate 5 --run-time 5m --headless

    # Against production (careful — generates REAL orders in Cloud SQL)
    locust -f scripts/locustfile.py \\
      --host=https://lumen-app-555338846378.us-central1.run.app \\
      --users 10 --spawn-rate 1 --run-time 2m --headless
"""

from __future__ import annotations

import random
from uuid import uuid4

from locust import HttpUser, between, task

# Mirrors seed.py — keep these in sync so the synthetic traffic looks
# like the same kind of business.
CHANNELS = [
    ("organic", 0.30),
    ("paid_search", 0.20),
    ("paid_social", 0.18),
    ("email", 0.12),
    ("direct", 0.10),
    ("referral", 0.07),
    ("affiliate", 0.03),
]
DEVICES = [("desktop", 0.45), ("mobile", 0.50), ("tablet", 0.05)]

# The seed creates 1,000 customers. In production this would come from a
# /api/customers/random endpoint or signup flow. Hardcoded for simplicity.
N_CUSTOMERS = 1_000


def _weighted_choice(choices):
    pop, w = zip(*choices, strict=True)
    return random.choices(pop, weights=w, k=1)[0]


def _zipf_pick(items):
    """Mimic the Pareto product picker from seed.py."""
    if not items:
        return None
    idx = min(int(random.paretovariate(1.3)) - 1, len(items) - 1)
    return items[idx]


# ----------------------------------------------------------- base shopper --


class Shopper(HttpUser):
    """The typical shopper: browses, sometimes buys."""

    weight = 8
    wait_time = between(1, 5)

    def on_start(self):
        self.session_id = uuid4().hex[:24]
        self.customer_id = random.randint(1, N_CUSTOMERS)
        self.channel = _weighted_choice(CHANNELS)
        self.device = _weighted_choice(DEVICES)
        self.cart: list[dict] = []
        self.products: list[dict] = []
        self._refresh_catalog()

    def _refresh_catalog(self):
        r = self.client.get("/api/catalog/products?limit=30", name="/catalog [seed]")
        if r.status_code == 200:
            self.products = r.json()

    def _track_view(self, product_id: int, event_type: str = "view"):
        self.client.post(
            "/api/events/product",
            name="/events/product",
            json={
                "session_id": self.session_id,
                "customer_id": self.customer_id,
                "product_id": product_id,
                "event_type": event_type,
            },
        )

    @task(10)
    def browse(self):
        """Pull the catalog — mimics scrolling a listing page."""
        self.client.get("/api/catalog/products?limit=20", name="/catalog browse")

    @task(8)
    def view_product(self):
        """Open a product detail page (Zipf-weighted toward popular SKUs)."""
        if not self.products:
            return
        p = _zipf_pick(self.products)
        self.client.get(f"/api/catalog/products/{p['id']}", name="/products/[id]")
        self._track_view(p["id"], "view")

    @task(3)
    def add_to_cart(self):
        if not self.products:
            return
        p = _zipf_pick(self.products)
        qty = random.choices([1, 2, 3], weights=[0.75, 0.20, 0.05])[0]
        self.cart.append(
            {"product_id": p["id"], "quantity": qty, "unit_price": p["price"]}
        )
        self._track_view(p["id"], "add_to_cart")

    @task(1)
    def checkout(self):
        if not self.cart:
            return
        # 35% of people who add to cart end up bouncing — leave items.
        if random.random() < 0.35:
            self.cart.clear()
            return
        payload = {
            "customer_id": self.customer_id,
            "items": [{"product_id": i["product_id"], "quantity": i["quantity"]} for i in self.cart],
            "channel": self.channel,
            "device_type": self.device,
        }
        self.cart.clear()
        self.client.post("/api/orders", name="/orders [checkout]", json=payload)


# ------------------------------------------------------------- impatient buyer --


class Buyer(HttpUser):
    """Knows what they want; skips browsing, places order quickly."""

    weight = 2
    wait_time = between(0.5, 2.5)

    def on_start(self):
        self.session_id = uuid4().hex[:24]
        self.customer_id = random.randint(1, N_CUSTOMERS)
        self.channel = _weighted_choice([("email", 0.5), ("direct", 0.3), ("organic", 0.2)])
        r = self.client.get("/api/catalog/products?limit=10", name="/catalog [buyer]")
        self.products = r.json() if r.status_code == 200 else []

    @task
    def quick_buy(self):
        if not self.products:
            return
        items = [
            {"product_id": p["id"], "quantity": random.choice([1, 1, 2])}
            for p in random.sample(self.products, k=random.randint(1, 3))
        ]
        self.client.post(
            "/api/orders",
            name="/orders [buyer]",
            json={
                "customer_id": self.customer_id,
                "items": items,
                "channel": self.channel,
                "device_type": "desktop",
            },
        )


# ----------------------------------------------------------------- bouncer --


class Bouncer(HttpUser):
    """Lands on one page, leaves. Drives bounce rate and view-only events."""

    weight = 1
    wait_time = between(2, 8)

    def on_start(self):
        self.session_id = uuid4().hex[:24]

    @task(3)
    def land_on_home(self):
        self.client.get("/", name="/ [bouncer]")

    @task(1)
    def land_on_catalog(self):
        self.client.get("/catalog", name="/catalog [bouncer]")
