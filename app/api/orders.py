from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Customer, Order
from app.schemas.order import OrderOut, PlaceOrderIn
from app.services import cart as cart_svc
from app.services.auth import get_anon_id, require_customer
from app.services.orders import (
    EmptyCartError,
    InvalidPromoError,
    checkout_cart,
    place_order,
)

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.post("", response_model=OrderOut, status_code=201)
def create_order(payload: PlaceOrderIn, db: Session = Depends(get_db)):
    """Accepts raw items — used by the seed script and load tests. The
    customer-facing flow is POST /api/orders/checkout."""
    try:
        order = place_order(db, payload)
    except InvalidPromoError as e:
        db.rollback()
        raise HTTPException(400, f"invalid promo: {e}") from e
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e)) from e
    db.commit()
    db.refresh(order)
    return order


@router.post("/checkout", response_model=OrderOut, status_code=201)
def checkout(
    request: Request,
    db: Session = Depends(get_db),
    customer: Customer = Depends(require_customer),
    promo_code: str | None = Body(None, embed=True),
    channel: str = Body("direct", embed=True),
    device_type: str = Body("desktop", embed=True),
):
    """Turn the caller's active cart into a paid order."""
    cart = cart_svc.resolve_active_cart(db, customer, get_anon_id(request))
    try:
        order = checkout_cart(
            db,
            customer,
            cart,
            channel=channel,
            device_type=device_type,
            promo_code=promo_code,
        )
    except EmptyCartError as e:
        db.rollback()
        raise HTTPException(400, str(e)) from e
    except InvalidPromoError as e:
        db.rollback()
        raise HTTPException(400, f"invalid promo: {e}") from e
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e)) from e

    db.commit()
    db.refresh(order)
    return order


@router.get("", response_model=list[OrderOut])
def list_my_orders(
    db: Session = Depends(get_db),
    customer: Customer = Depends(require_customer),
    limit: int = 20,
):
    return (
        db.execute(
            select(Order)
            .where(Order.customer_id == customer.id)
            .options(selectinload(Order.items))
            .order_by(Order.placed_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )


@router.get("/{order_id}", response_model=OrderOut)
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    customer: Customer = Depends(require_customer),
):
    order = db.execute(
        select(Order)
        .where(Order.id == order_id, Order.customer_id == customer.id)
        .options(selectinload(Order.items))
    ).scalar_one_or_none()
    if not order:
        raise HTTPException(404)
    return order
