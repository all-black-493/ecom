"""Auth endpoints — register, login, logout, /me.

The JSON side of authentication. The browser flow in app/api/pages.py wraps
the same services with forms and redirects.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Customer
from app.schemas.auth import CustomerOut, LoginIn, RegisterIn, TokenOut
from app.services import cart as cart_svc
from app.services.auth import (
    SESSION_TTL_DAYS,
    clear_session_cookie,
    create_session_token,
    get_anon_id,
    hash_password,
    require_customer,
    set_session_cookie,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _issue(response: Response, customer: Customer) -> TokenOut:
    token = create_session_token(customer.id)
    set_session_cookie(response, token)
    return TokenOut(
        access_token=token,
        expires_in_days=SESSION_TTL_DAYS,
        customer=CustomerOut.model_validate(customer),
    )


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    email = payload.email.lower()
    if db.scalar(select(Customer).where(Customer.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    customer = Customer(
        email=email,
        first_name=payload.first_name,
        last_name=payload.last_name,
        password_hash=hash_password(payload.password),
        signup_channel=payload.signup_channel,
        signup_country=payload.signup_country.upper(),
        marketing_opt_in=payload.marketing_opt_in,
    )
    db.add(customer)
    db.flush()
    cart_svc.claim_anon_cart(db, customer.id, get_anon_id(request))
    db.commit()
    db.refresh(customer)

    return _issue(response, customer)


@router.post("/login", response_model=TokenOut)
def login(
    payload: LoginIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    customer = db.scalar(select(Customer).where(Customer.email == payload.email.lower()))
    if not customer or not verify_password(payload.password, customer.password_hash):
        # One message for both cases — don't leak which emails exist.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    cart_svc.claim_anon_cart(db, customer.id, get_anon_id(request))
    db.commit()

    return _issue(response, customer)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout():
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookie(response)
    return response


@router.get("/me", response_model=CustomerOut)
def me(customer: Customer = Depends(require_customer)):
    return customer
