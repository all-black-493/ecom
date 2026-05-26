from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import analytics

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/kpi")
def kpi(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db)):
    return analytics.kpi_summary(db, days)


@router.get("/revenue-by-day")
def revenue_by_day(days: int = Query(90, ge=7, le=365), db: Session = Depends(get_db)):
    return analytics.revenue_by_day(db, days)


@router.get("/top-products")
def top_products(
    days: int = Query(30, ge=7, le=365), limit: int = 10, db: Session = Depends(get_db)
):
    return analytics.top_products(db, days, limit)


@router.get("/slow-movers")
def slow_movers(
    days: int = Query(60, ge=7, le=365),
    max_units: int = Query(5, ge=0, le=100),
    db: Session = Depends(get_db),
):
    return analytics.slow_movers(db, days, max_units)


@router.get("/revenue-by-channel")
def revenue_by_channel(days: int = 30, db: Session = Depends(get_db)):
    return analytics.revenue_by_channel(db, days)


@router.get("/cart-abandonment")
def cart_abandonment(days: int = 30, db: Session = Depends(get_db)):
    return analytics.cart_abandonment(db, days)


@router.get("/repeat-purchase-rate")
def repeat_purchase_rate(days: int = 90, db: Session = Depends(get_db)):
    return analytics.repeat_purchase_rate(db, days)


@router.get("/cohort-retention")
def cohort_retention(db: Session = Depends(get_db)):
    return analytics.cohort_retention(db)


@router.get("/aov-by-device")
def aov_by_device(days: int = 30, db: Session = Depends(get_db)):
    return analytics.aov_by_device(db, days)


@router.get("/gross-margin-by-category")
def gross_margin_by_category(days: int = 30, db: Session = Depends(get_db)):
    return analytics.gross_margin_by_category(db, days)


@router.get("/stockouts-at-risk")
def stockouts_at_risk(days: int = 28, db: Session = Depends(get_db)):
    return analytics.stockouts_at_risk(db, days)


@router.get("/funnel")
def funnel(db: Session = Depends(get_db)):
    return analytics.funnel_last_30d(db)
