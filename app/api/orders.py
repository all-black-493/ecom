from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Order
from app.schemas.order import OrderOut, PlaceOrderIn
from app.services.orders import InvalidPromoError, place_order

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.post("", response_model=OrderOut, status_code=201)
def create_order(payload: PlaceOrderIn, db: Session = Depends(get_db)):
    try:
        order = place_order(db, payload)
    except InvalidPromoError as e:
        raise HTTPException(400, f"invalid promo: {e}") from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    db.commit()
    db.refresh(order)
    return order


@router.get("/{order_id}", response_model=OrderOut)
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.execute(
        select(Order).where(Order.id == order_id).options(selectinload(Order.items))
    ).scalar_one_or_none()
    if not order:
        raise HTTPException(404)
    return order
