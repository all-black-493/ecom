"""Order placement — encapsulates the multi-table write behind the checkout.

Two entry points share the same pricing and payment tail:
  place_order   — raw item payload (seed script, load tests, internal API)
  checkout_cart — the customer-facing flow, sourced from an active Cart
Both leave the transaction open; the caller commits.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models import (
    Cart,
    Customer,
    Order,
    OrderItem,
    OrderStatus,
    Payment,
    PaymentStatus,
    Product,
    Promotion,
    PromotionRedemption,
    StockMovement,
)
from app.schemas.order import PlaceOrderIn
from app.services import cart as cart_svc
from app.services.cart import CENTS, FREE_SHIPPING_OVER, SHIPPING_FLAT, TAX_RATE


class OutOfStockError(RuntimeError):
    pass


class InvalidPromoError(RuntimeError):
    pass


class EmptyCartError(RuntimeError):
    pass


class _Line:
    __slots__ = ("product_id", "variant_id", "quantity")

    def __init__(self, product_id: int, variant_id: int | None, quantity: int) -> None:
        self.product_id = product_id
        self.variant_id = variant_id
        self.quantity = quantity


def _new_order(customer_id: int, channel: str, device_type: str) -> Order:
    return Order(
        order_number=f"L{uuid4().hex[:10].upper()}",
        customer_id=customer_id,
        status=OrderStatus.PENDING,
        channel=channel,
        device_type=device_type,
        placed_at=datetime.now(UTC),
    )


def _add_lines(db: Session, order: Order, lines: Iterable[_Line]) -> Decimal:
    """Write the order items and their stock movements. Returns the subtotal."""
    subtotal = Decimal("0")
    for line in lines:
        product = db.get(Product, line.product_id)
        if not product or not product.is_active:
            raise ValueError(f"product {line.product_id} is not purchasable")

        db.add(
            OrderItem(
                order_id=order.id,
                product_id=product.id,
                variant_id=line.variant_id,
                quantity=line.quantity,
                unit_price=product.price,
                unit_cost=product.cost,
            )
        )
        subtotal += product.price * line.quantity

        if line.variant_id is not None:
            db.add(
                StockMovement(
                    variant_id=line.variant_id,
                    delta=-line.quantity,
                    reason="sale",
                    ref_order_id=order.id,
                )
            )
    return subtotal


def _apply_promo(
    db: Session, order: Order, customer_id: int, subtotal: Decimal, code: str | None
) -> Decimal:
    if not code:
        return Decimal("0")
    promo = db.query(Promotion).filter_by(code=code, is_active=True).one_or_none()
    if not promo:
        raise InvalidPromoError(code)
    if promo.kind == "percent":
        discount = (subtotal * promo.value / Decimal("100")).quantize(CENTS)
    else:
        discount = min(subtotal, promo.value)
    db.add(
        PromotionRedemption(
            promotion_id=promo.id,
            order_id=order.id,
            customer_id=customer_id,
            amount_off=discount,
        )
    )
    return discount


def _settle(db: Session, order: Order, subtotal: Decimal, discount: Decimal) -> None:
    """Price the order, capture a (mocked) payment, and mark it paid."""
    shipping = Decimal("0") if subtotal > FREE_SHIPPING_OVER else SHIPPING_FLAT
    tax = ((subtotal - discount) * TAX_RATE).quantize(CENTS)

    order.subtotal = subtotal.quantize(CENTS)
    order.discount_total = discount
    order.shipping_total = shipping
    order.tax_total = tax
    order.grand_total = (subtotal - discount + shipping + tax).quantize(CENTS)

    db.add(
        Payment(
            order_id=order.id,
            provider="stripe",
            method="card",
            status=PaymentStatus.CAPTURED,
            amount=order.grand_total,
            captured_at=datetime.now(UTC),
        )
    )
    order.status = OrderStatus.PAID
    order.paid_at = datetime.now(UTC)


def place_order(db: Session, payload: PlaceOrderIn) -> Order:
    order = _new_order(payload.customer_id, payload.channel, payload.device_type)
    db.add(order)
    db.flush()

    subtotal = _add_lines(
        db,
        order,
        (_Line(it.product_id, it.variant_id, it.quantity) for it in payload.items),
    )
    discount = _apply_promo(db, order, payload.customer_id, subtotal, payload.promo_code)
    _settle(db, order, subtotal, discount)
    return order


def checkout_cart(
    db: Session,
    customer: Customer,
    cart: Cart,
    channel: str = "direct",
    device_type: str = "desktop",
    promo_code: str | None = None,
) -> Order:
    """Convert an active cart into a paid order.

    The cart is marked converted rather than deleted — it stays available to
    the funnel and abandonment reports, and the next cart API call starts a
    fresh one.
    """
    if not cart.items:
        raise EmptyCartError("Cart is empty")

    order = _new_order(customer.id, channel, device_type)
    db.add(order)
    db.flush()

    subtotal = _add_lines(
        db,
        order,
        (_Line(ci.product_id, ci.variant_id, ci.quantity) for ci in cart.items),
    )
    discount = _apply_promo(db, order, customer.id, subtotal, promo_code)
    _settle(db, order, subtotal, discount)

    cart_svc.mark_converted(cart)
    return order
