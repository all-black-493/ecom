"""Server-side cart operations.

A cart belongs to either a customer (logged in) or a session id (the guest's
`lumen_anon` cookie). `resolve_active_cart` returns the right one and creates
it when needed, so callers never have to branch on the auth state.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Cart, CartItem, Customer, Product

TAX_RATE = Decimal("0.08")
FREE_SHIPPING_OVER = Decimal("75")
SHIPPING_FLAT = Decimal("9.99")
CENTS = Decimal("0.01")


def resolve_active_cart(db: Session, customer: Customer | None, session_id: str) -> Cart:
    """The customer's active cart, else this browser's guest cart (claimed if
    the customer just logged in), else a new one."""
    cart: Cart | None = None

    if customer:
        cart = db.scalar(
            select(Cart).where(Cart.customer_id == customer.id, Cart.status == "active")
        )

    if cart is None:
        cart = db.scalar(select(Cart).where(Cart.session_id == session_id, Cart.status == "active"))
        if cart and customer and cart.customer_id is None:
            cart.customer_id = customer.id

    if cart is None:
        cart = Cart(
            customer_id=customer.id if customer else None,
            session_id=session_id,
            status="active",
        )
        db.add(cart)
        db.flush()

    return cart


def claim_anon_cart(db: Session, customer_id: int, session_id: str) -> None:
    """Link this browser's guest cart to a customer who just signed in or
    registered. Caller commits."""
    cart = db.scalar(
        select(Cart).where(
            Cart.session_id == session_id,
            Cart.status == "active",
            Cart.customer_id.is_(None),
        )
    )
    if cart:
        cart.customer_id = customer_id


def add_item(
    db: Session,
    cart: Cart,
    product_id: int,
    quantity: int = 1,
    variant_id: int | None = None,
) -> CartItem:
    if quantity < 1:
        raise ValueError("Quantity must be at least 1")
    product = db.get(Product, product_id)
    if not product or not product.is_active:
        raise LookupError(f"Product {product_id} is not purchasable")

    variant_match = (
        CartItem.variant_id.is_(None) if variant_id is None else CartItem.variant_id == variant_id
    )
    existing = db.scalar(
        select(CartItem).where(
            CartItem.cart_id == cart.id,
            CartItem.product_id == product_id,
            variant_match,
        )
    )
    if existing:
        existing.quantity += quantity
        return existing

    item = CartItem(
        cart_id=cart.id,
        product_id=product_id,
        variant_id=variant_id,
        quantity=quantity,
        unit_price=product.price,
    )
    db.add(item)
    db.flush()
    return item


def _owned_item(db: Session, cart: Cart, item_id: int) -> CartItem:
    item = db.get(CartItem, item_id)
    if not item or item.cart_id != cart.id:
        raise LookupError(f"Cart item {item_id} not found in this cart")
    return item


def update_quantity(db: Session, cart: Cart, item_id: int, quantity: int) -> None:
    item = _owned_item(db, cart, item_id)
    if quantity <= 0:
        db.delete(item)
    else:
        item.quantity = quantity


def remove_item(db: Session, cart: Cart, item_id: int) -> None:
    db.delete(_owned_item(db, cart, item_id))


def cart_totals(cart: Cart) -> dict:
    """Pre-promotion totals for the cart and checkout pages. The authoritative
    figures are recomputed by services.orders when the order is placed."""
    subtotal = sum((Decimal(item.unit_price) * item.quantity for item in cart.items), Decimal("0"))
    shipping = Decimal("0") if subtotal > FREE_SHIPPING_OVER else SHIPPING_FLAT
    tax = (subtotal * TAX_RATE).quantize(CENTS)
    return {
        "item_count": sum(item.quantity for item in cart.items),
        "subtotal": subtotal.quantize(CENTS),
        "shipping": shipping,
        "tax": tax,
        "grand_total": (subtotal + shipping + tax).quantize(CENTS),
    }


def mark_converted(cart: Cart) -> None:
    cart.status = "converted"
    cart.converted_at = datetime.now(UTC)
