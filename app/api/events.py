"""Lightweight event tracking for funnel analytics.

These are append-only single-table writes — designed to handle high
throughput from Locust load tests (and, eventually, real browser
analytics). Returns 201 with no body to minimize round-trip size.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ProductEvent

router = APIRouter(prefix="/api/events", tags=["events"])


class ProductEventIn(BaseModel):
    session_id: str = Field(..., max_length=64)
    product_id: int
    customer_id: int | None = None
    event_type: str = Field("view", pattern=r"^(view|add_to_cart|remove_from_cart|wishlist)$")


@router.post("/product", status_code=status.HTTP_201_CREATED)
def record_product_event(payload: ProductEventIn, db: Session = Depends(get_db)):
    db.add(
        ProductEvent(
            session_id=payload.session_id,
            customer_id=payload.customer_id,
            product_id=payload.product_id,
            event_type=payload.event_type,
        )
    )
    db.commit()
    return {"ok": True}
