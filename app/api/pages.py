"""Web UI pages — Jinja2 templates for the storefront and embedded dashboards."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Category, Product

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    cats = db.scalars(select(Category)).all()
    featured = db.scalars(select(Product).where(Product.is_active).limit(8)).all()
    return templates.TemplateResponse(
        request, "home.html", {"categories": cats, "featured": featured}
    )


@router.get("/catalog", response_class=HTMLResponse)
def catalog(request: Request, db: Session = Depends(get_db), category_id: int | None = None):
    cats = db.scalars(select(Category)).all()
    stmt = select(Product).where(Product.is_active)
    if category_id is not None:
        stmt = stmt.where(Product.category_id == category_id)
    products = db.scalars(stmt.limit(60)).all()
    return templates.TemplateResponse(
        request,
        "catalog.html",
        {"categories": cats, "products": products, "selected_category": category_id},
    )


@router.get("/dashboards", response_class=HTMLResponse)
def dashboards_home(request: Request):
    return templates.TemplateResponse(request, "dashboards/index.html", {})


@router.get("/dashboards/sales", response_class=HTMLResponse)
def dashboards_sales(request: Request):
    settings = get_settings()
    return templates.TemplateResponse(
        request,
        "dashboards/sales.html",
        {"cube_api_url": settings.cubejs_api_url, "cube_token": "dev-token"},
    )


@router.get("/dashboards/inventory", response_class=HTMLResponse)
def dashboards_inventory(request: Request):
    settings = get_settings()
    return templates.TemplateResponse(
        request,
        "dashboards/inventory.html",
        {"cube_api_url": settings.cubejs_api_url, "cube_token": "dev-token"},
    )
