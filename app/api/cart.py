"""Cart API — works for guests and logged-in customers alike.

The guest identity comes from the lumen_anon cookie, the auth identity from
get_current_customer; the cart service reconciles the two.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Cart, Customer, Product
from app.schemas.cart import AddToCartIn, CartItemOut, CartOut, CartTotalsOut, UpdateCartItemIn
from app.services import cart as cart_svc
from app.services.auth import get_anon_id, get_current_customer

router = APIRouter(prefix="/api/cart", tags=["cart"])


def _serialize_cart(db: Session, cart: Cart) -> CartOut:
    db.refresh(cart)
    items_out = []
    for item in cart.items:
        product = db.get(Product, item.product_id)
        items_out.append(
            CartItemOut(
                id=item.id,
                product_id=item.product_id,
                variant_id=item.variant_id,
                quantity=item.quantity,
                unit_price=item.unit_price,
                product_name=product.name if product else None,
                product_sku=product.sku if product else None,
                line_total=item.unit_price * item.quantity,
            )
        )
    return CartOut(
        id=cart.id,
        status=cart.status,
        items=items_out,
        totals=CartTotalsOut(**cart_svc.cart_totals(cart)),
    )


def _active_cart(request: Request, db: Session, customer: Customer | None) -> Cart:
    return cart_svc.resolve_active_cart(db, customer, get_anon_id(request))


@router.get("", response_model=CartOut)
def view_cart(
    request: Request,
    db: Session = Depends(get_db),
    customer: Customer | None = Depends(get_current_customer),
):
    cart = _active_cart(request, db, customer)
    db.commit()
    return _serialize_cart(db, cart)


@router.post("/items", response_model=CartOut, status_code=201)
def add_to_cart(
    payload: AddToCartIn,
    request: Request,
    db: Session = Depends(get_db),
    customer: Customer | None = Depends(get_current_customer),
):
    cart = _active_cart(request, db, customer)
    try:
        cart_svc.add_item(
            db,
            cart,
            product_id=payload.product_id,
            quantity=payload.quantity,
            variant_id=payload.variant_id,
        )
    except LookupError as e:
        db.rollback()
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e)) from e
    db.commit()
    return _serialize_cart(db, cart)


@router.patch("/items/{item_id}", response_model=CartOut)
def update_cart_item(
    item_id: int,
    payload: UpdateCartItemIn,
    request: Request,
    db: Session = Depends(get_db),
    customer: Customer | None = Depends(get_current_customer),
):
    cart = _active_cart(request, db, customer)
    try:
        cart_svc.update_quantity(db, cart, item_id, payload.quantity)
    except LookupError as e:
        db.rollback()
        raise HTTPException(404, str(e)) from e
    db.commit()
    return _serialize_cart(db, cart)


@router.delete("/items/{item_id}", response_model=CartOut)
def remove_cart_item(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    customer: Customer | None = Depends(get_current_customer),
):
    cart = _active_cart(request, db, customer)
    try:
        cart_svc.remove_item(db, cart, item_id)
    except LookupError as e:
        db.rollback()
        raise HTTPException(404, str(e)) from e
    db.commit()
    return _serialize_cart(db, cart)
