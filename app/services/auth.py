"""Password hashing, session tokens, and the current-customer dependencies.

Sessions are stateless: an HS256 JWT signed with APP_SECRET, carried in the
HttpOnly `lumen_session` cookie. Guests get a separate `lumen_anon` cookie
holding a random id, which the Cart model stores as `session_id`; on login
that cart is claimed by the customer.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit
from uuid import uuid4

import bcrypt
from fastapi import Depends, HTTPException, Request, Response, status
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Customer

SESSION_COOKIE = "lumen_session"
ANON_COOKIE = "lumen_anon"
SESSION_TTL_DAYS = 7
ANON_TTL_DAYS = 180
ALGO = "HS256"

# bcrypt hashes at most 72 bytes. Truncate rather than raise so a long
# password fails at neither registration nor login.
BCRYPT_MAX_BYTES = 72


class LoginRequired(Exception):
    """Raised by page routes that need a session; main.py turns it into a
    redirect to /login."""

    def __init__(self, next_path: str = "/") -> None:
        self.next_path = next_path


def _prepare(plain: str) -> bytes:
    return plain.encode("utf-8")[:BCRYPT_MAX_BYTES]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_prepare(plain), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_session_token(customer_id: int) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(customer_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=SESSION_TTL_DAYS)).timestamp()),
    }
    return jwt.encode(payload, get_settings().app_secret, algorithm=ALGO)


def decode_session_token(token: str) -> int | None:
    """The customer id, or None if the token is expired or invalid."""
    try:
        payload = jwt.decode(token, get_settings().app_secret, algorithms=[ALGO])
        return int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        return None


def _secure_cookies() -> bool:
    return get_settings().app_env == "production"


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_TTL_DAYS * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=_secure_cookies(),
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE)


def new_anon_id() -> str:
    return uuid4().hex[:24]


def set_anon_cookie(response: Response, anon_id: str) -> None:
    response.set_cookie(
        ANON_COOKIE,
        anon_id,
        max_age=ANON_TTL_DAYS * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=_secure_cookies(),
    )


def get_anon_id(request: Request) -> str:
    """The guest cart id for this browser, assigned by the anon_session
    middleware in main.py."""
    return request.state.anon_id


def safe_next(target: str | None, fallback: str = "/") -> str:
    """Only allow same-site redirect targets — never an absolute URL."""
    if not target or not target.startswith("/") or target.startswith("//"):
        return fallback
    parts = urlsplit(target)
    if parts.scheme or parts.netloc:
        return fallback
    return target


def get_current_customer(
    request: Request,
    db: Session = Depends(get_db),
) -> Customer | None:
    """The logged-in Customer, or None. Never raises — for routes that work
    for guests too."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    customer_id = decode_session_token(token)
    if not customer_id:
        return None
    return db.get(Customer, customer_id)


def require_customer(customer: Customer | None = Depends(get_current_customer)) -> Customer:
    """401s if there is no valid session. For the JSON API."""
    if not customer:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login required")
    return customer


def require_customer_page(
    request: Request,
    customer: Customer | None = Depends(get_current_customer),
) -> Customer:
    """Redirects to /login if there is no valid session. For HTML pages."""
    if not customer:
        raise LoginRequired(request.url.path)
    return customer
