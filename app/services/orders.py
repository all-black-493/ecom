"""Order placement service — encapsulates the multi-table write."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models import (
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


class OutOfStockError(RuntimeError):
    pass


class InvalidPromoError(RuntimeError):
    pass


def place_order(db: Session, payload: PlaceOrderIn) -> Order:
    """Place an order atomically. Caller controls the transaction."""
    order = Order(
        order_number=f"L{uuid4().hex[:10].upper()}",
        customer_id=payload.customer_id,
        status=OrderStatus.PENDING,
        channel=payload.channel,
        device_type=payload.device_type,
        placed_at=datetime.now(timezone.utc),
    )
    db.add(order)
    db.flush()

    subtotal = Decimal("0")
    for it in payload.items:
        product = db.get(Product, it.product_id)
        if not product or not product.is_active:
            raise ValueError(f"product {it.product_id} not purchasable")

        db.add(
            OrderItem(
                order_id=order.id,
                product_id=product.id,
                variant_id=it.variant_id,
                quantity=it.quantity,
                unit_price=product.price,
                unit_cost=product.cost,
            )
        )
        subtotal += product.price * it.quantity

        if it.variant_id is not None:
            db.add(
                StockMovement(
                    variant_id=it.variant_id,
                    delta=-it.quantity,
                    reason="sale",
                    ref_order_id=order.id,
                )
            )

    discount = Decimal("0")
    if payload.promo_code:
        promo = db.query(Promotion).filter_by(code=payload.promo_code, is_active=True).one_or_none()
        if not promo:
            raise InvalidPromoError(payload.promo_code)
        if promo.kind == "percent":
            discount = (subtotal * promo.value / Decimal("100")).quantize(Decimal("0.01"))
        else:
            discount = min(subtotal, promo.value)
        db.add(
            PromotionRedemption(
                promotion_id=promo.id,
                order_id=order.id,
                customer_id=payload.customer_id,
                amount_off=discount,
            )
        )

    shipping = Decimal("0") if subtotal > Decimal("75") else Decimal("9.99")
    tax = ((subtotal - discount) * Decimal("0.08")).quantize(Decimal("0.01"))
    grand = (subtotal - discount + shipping + tax).quantize(Decimal("0.01"))

    order.subtotal = subtotal.quantize(Decimal("0.01"))
    order.discount_total = discount
    order.shipping_total = shipping
    order.tax_total = tax
    order.grand_total = grand

    db.add(
        Payment(
            order_id=order.id,
            provider="stripe",
            method="card",
            status=PaymentStatus.CAPTURED,
            amount=grand,
            captured_at=datetime.now(timezone.utc),
        )
    )
    order.status = OrderStatus.PAID
    order.paid_at = datetime.now(timezone.utc)

    return order
