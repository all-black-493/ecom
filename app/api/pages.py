"""Web UI — Jinja2 pages for the storefront, auth, cart, checkout and dashboards.

Form POSTs answer with a 303 redirect so a refresh never re-submits. Pages that
need a session depend on require_customer_page, which redirects to /login
instead of returning the API's 401.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.database import get_db
from app.models import Address, Cart, Category, Customer, Order, Product
from app.services import cart as cart_svc
from app.services.auth import (
    clear_session_cookie,
    create_session_token,
    get_anon_id,
    get_current_customer,
    hash_password,
    require_customer_page,
    safe_next,
    set_session_cookie,
    verify_password,
)
from app.services.orders import EmptyCartError, InvalidPromoError, checkout_cart

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="app/templates")

SEE_OTHER = status.HTTP_303_SEE_OTHER


def _cart_count(request: Request, db: Session, customer: Customer | None) -> int:
    """Item count for the header badge. Read-only — never creates a cart."""
    clause = (
        Cart.customer_id == customer.id if customer else Cart.session_id == get_anon_id(request)
    )
    cart = db.scalar(select(Cart).where(clause, Cart.status == "active"))
    return sum(item.quantity for item in cart.items) if cart else 0


def _ctx(request: Request, db: Session, customer: Customer | None, **extra) -> dict:
    """Template context every page shares: auth state and the cart badge."""
    return {
        "request": request,
        "current_customer": customer,
        "cart_count": _cart_count(request, db, customer),
        **extra,
    }


def _hydrate(db: Session, items) -> list[dict]:
    """Attach the Product to each cart/order line for display."""
    return [
        {
            "id": item.id,
            "product": db.get(Product, item.product_id),
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "line_total": item.unit_price * item.quantity,
        }
        for item in items
    ]


@router.get("/", response_class=HTMLResponse)
def home(
    request: Request,
    db: Session = Depends(get_db),
    customer: Customer | None = Depends(get_current_customer),
):
    cats = db.scalars(select(Category)).all()
    featured = db.scalars(select(Product).where(Product.is_active).limit(8)).all()
    return templates.TemplateResponse(
        request, "home.html", _ctx(request, db, customer, categories=cats, featured=featured)
    )


@router.get("/catalog", response_class=HTMLResponse)
def catalog(
    request: Request,
    db: Session = Depends(get_db),
    category_id: int | None = None,
    customer: Customer | None = Depends(get_current_customer),
):
    cats = db.scalars(select(Category)).all()
    stmt = select(Product).where(Product.is_active)
    if category_id is not None:
        stmt = stmt.where(Product.category_id == category_id)
    products = db.scalars(stmt.limit(60)).all()
    return templates.TemplateResponse(
        request,
        "catalog.html",
        _ctx(
            request,
            db,
            customer,
            categories=cats,
            products=products,
            selected_category=category_id,
        ),
    )


@router.get("/products/{product_id}", response_class=HTMLResponse)
def product_detail(
    product_id: int,
    request: Request,
    db: Session = Depends(get_db),
    customer: Customer | None = Depends(get_current_customer),
):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404)
    return templates.TemplateResponse(
        request, "product_detail.html", _ctx(request, db, customer, product=product)
    )


@router.get("/login", response_class=HTMLResponse)
def login_page(
    request: Request,
    db: Session = Depends(get_db),
    customer: Customer | None = Depends(get_current_customer),
    next: str = "/",
):
    target = safe_next(next)
    if customer:
        return RedirectResponse(target, status_code=SEE_OTHER)
    return templates.TemplateResponse(
        request, "auth/login.html", _ctx(request, db, None, error=None, next=target)
    )


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
    db: Session = Depends(get_db),
):
    target = safe_next(next)
    customer = db.scalar(select(Customer).where(Customer.email == email.lower()))
    if not customer or not verify_password(password, customer.password_hash):
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            _ctx(request, db, None, error="Invalid email or password.", next=target),
            status_code=400,
        )

    cart_svc.claim_anon_cart(db, customer.id, get_anon_id(request))
    db.commit()

    response = RedirectResponse(target, status_code=SEE_OTHER)
    set_session_cookie(response, create_session_token(customer.id))
    return response


@router.get("/register", response_class=HTMLResponse)
def register_page(
    request: Request,
    db: Session = Depends(get_db),
    customer: Customer | None = Depends(get_current_customer),
):
    if customer:
        return RedirectResponse("/", status_code=SEE_OTHER)
    return templates.TemplateResponse(
        request, "auth/register.html", _ctx(request, db, None, error=None)
    )


@router.post("/register", response_class=HTMLResponse)
def register_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    marketing_opt_in: bool = Form(False),
    db: Session = Depends(get_db),
):
    def fail(message: str):
        return templates.TemplateResponse(
            request,
            "auth/register.html",
            _ctx(request, db, None, error=message),
            status_code=400,
        )

    if len(password) < 8:
        return fail("Password must be at least 8 characters.")
    if db.scalar(select(Customer).where(Customer.email == email.lower())):
        return fail("That email is already registered.")

    customer = Customer(
        email=email.lower(),
        first_name=first_name,
        last_name=last_name,
        password_hash=hash_password(password),
        signup_channel="direct",
        signup_country="US",
        marketing_opt_in=marketing_opt_in,
    )
    db.add(customer)
    db.flush()
    cart_svc.claim_anon_cart(db, customer.id, get_anon_id(request))
    db.commit()

    response = RedirectResponse("/", status_code=SEE_OTHER)
    set_session_cookie(response, create_session_token(customer.id))
    return response


@router.post("/logout")
def logout_submit():
    response = RedirectResponse("/", status_code=SEE_OTHER)
    clear_session_cookie(response)
    return response


@router.get("/cart", response_class=HTMLResponse)
def cart_page(
    request: Request,
    db: Session = Depends(get_db),
    customer: Customer | None = Depends(get_current_customer),
):
    cart = cart_svc.resolve_active_cart(db, customer, get_anon_id(request))
    db.commit()
    return templates.TemplateResponse(
        request,
        "cart.html",
        _ctx(
            request,
            db,
            customer,
            items=_hydrate(db, cart.items),
            totals=cart_svc.cart_totals(cart),
        ),
    )


@router.post("/cart/add")
def cart_add(
    request: Request,
    product_id: int = Form(...),
    quantity: int = Form(1),
    db: Session = Depends(get_db),
    customer: Customer | None = Depends(get_current_customer),
):
    cart = cart_svc.resolve_active_cart(db, customer, get_anon_id(request))
    try:
        cart_svc.add_item(db, cart, product_id=product_id, quantity=quantity)
    except (LookupError, ValueError) as e:
        db.rollback()
        raise HTTPException(400, str(e)) from e
    db.commit()
    return RedirectResponse("/cart", status_code=SEE_OTHER)


@router.post("/cart/update")
def cart_update(
    request: Request,
    item_id: int = Form(...),
    quantity: int = Form(...),
    db: Session = Depends(get_db),
    customer: Customer | None = Depends(get_current_customer),
):
    cart = cart_svc.resolve_active_cart(db, customer, get_anon_id(request))
    try:
        cart_svc.update_quantity(db, cart, item_id, quantity)
    except LookupError as e:
        db.rollback()
        raise HTTPException(404, str(e)) from e
    db.commit()
    return RedirectResponse("/cart", status_code=SEE_OTHER)


@router.get("/checkout", response_class=HTMLResponse)
def checkout_page(
    request: Request,
    db: Session = Depends(get_db),
    customer: Customer = Depends(require_customer_page),
):
    cart = cart_svc.resolve_active_cart(db, customer, get_anon_id(request))
    db.commit()
    if not cart.items:
        return RedirectResponse("/cart", status_code=SEE_OTHER)
    return templates.TemplateResponse(
        request,
        "checkout.html",
        _ctx(
            request,
            db,
            customer,
            items=_hydrate(db, cart.items),
            totals=cart_svc.cart_totals(cart),
            error=None,
        ),
    )


@router.post("/checkout")
def checkout_submit(
    request: Request,
    line1: str = Form(...),
    city: str = Form(...),
    region: str = Form(...),
    postal_code: str = Form(...),
    line2: str = Form(""),
    country: str = Form("US"),
    promo_code: str = Form(""),
    db: Session = Depends(get_db),
    customer: Customer = Depends(require_customer_page),
):
    cart = cart_svc.resolve_active_cart(db, customer, get_anon_id(request))

    # One default shipping address per customer is enough for this demo.
    addr = db.scalar(select(Address).where(Address.customer_id == customer.id, Address.is_default))
    if not addr:
        addr = Address(customer_id=customer.id, is_default=True)
        db.add(addr)
    addr.line1 = line1
    addr.line2 = line2 or None
    addr.city = city
    addr.region = region
    addr.postal_code = postal_code
    addr.country = country.upper()
    db.flush()

    try:
        order = checkout_cart(db, customer, cart, promo_code=promo_code or None)
    except EmptyCartError:
        db.rollback()
        return RedirectResponse("/cart", status_code=SEE_OTHER)
    except (InvalidPromoError, ValueError) as e:
        message = (
            f"Promo code {promo_code} is not valid." if isinstance(e, InvalidPromoError) else str(e)
        )
        db.rollback()
        cart = cart_svc.resolve_active_cart(db, customer, get_anon_id(request))
        return templates.TemplateResponse(
            request,
            "checkout.html",
            _ctx(
                request,
                db,
                customer,
                items=_hydrate(db, cart.items),
                totals=cart_svc.cart_totals(cart),
                error=message,
            ),
            status_code=400,
        )

    db.commit()
    return RedirectResponse(f"/orders/{order.id}", status_code=SEE_OTHER)


@router.get("/orders", response_class=HTMLResponse)
def orders_page(
    request: Request,
    db: Session = Depends(get_db),
    customer: Customer = Depends(require_customer_page),
):
    orders = (
        db.execute(
            select(Order)
            .where(Order.customer_id == customer.id)
            .options(selectinload(Order.items))
            .order_by(Order.placed_at.desc())
            .limit(50)
        )
        .scalars()
        .all()
    )
    return templates.TemplateResponse(
        request, "orders.html", _ctx(request, db, customer, orders=orders)
    )


@router.get("/orders/{order_id}", response_class=HTMLResponse)
def order_detail_page(
    order_id: int,
    request: Request,
    db: Session = Depends(get_db),
    customer: Customer = Depends(require_customer_page),
):
    order = db.execute(
        select(Order)
        .where(Order.id == order_id, Order.customer_id == customer.id)
        .options(selectinload(Order.items))
    ).scalar_one_or_none()
    if not order:
        raise HTTPException(404)
    return templates.TemplateResponse(
        request,
        "order_detail.html",
        _ctx(request, db, customer, order=order, items=_hydrate(db, order.items)),
    )


@router.get("/account", response_class=HTMLResponse)
def account_page(
    request: Request,
    db: Session = Depends(get_db),
    customer: Customer = Depends(require_customer_page),
):
    return templates.TemplateResponse(request, "account.html", _ctx(request, db, customer))


@router.get("/dashboards", response_class=HTMLResponse)
def dashboards_home(
    request: Request,
    db: Session = Depends(get_db),
    customer: Customer | None = Depends(get_current_customer),
):
    return templates.TemplateResponse(request, "dashboards/index.html", _ctx(request, db, customer))


@router.get("/dashboards/sales", response_class=HTMLResponse)
def dashboards_sales(
    request: Request,
    db: Session = Depends(get_db),
    customer: Customer | None = Depends(get_current_customer),
):
    settings = get_settings()
    return templates.TemplateResponse(
        request,
        "dashboards/sales.html",
        _ctx(
            request,
            db,
            customer,
            cube_api_url=settings.cubejs_api_url,
            cube_token="dev-token",
        ),
    )


@router.get("/dashboards/inventory", response_class=HTMLResponse)
def dashboards_inventory(
    request: Request,
    db: Session = Depends(get_db),
    customer: Customer | None = Depends(get_current_customer),
):
    settings = get_settings()
    return templates.TemplateResponse(
        request,
        "dashboards/inventory.html",
        _ctx(
            request,
            db,
            customer,
            cube_api_url=settings.cubejs_api_url,
            cube_token="dev-token",
        ),
    )
