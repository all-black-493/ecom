from urllib.parse import quote

from fastapi import FastAPI, Request, status
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api import analytics, auth, cart, catalog, events, ml, orders, pages
from app.config import get_settings
from app.services.auth import ANON_COOKIE, LoginRequired, new_anon_id, set_anon_cookie

settings = get_settings()

app = FastAPI(
    title="Lumen Commerce",
    description="Ecommerce backend + embedded analytics",
    version="0.1.0",
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(pages.router)

app.include_router(auth.router)
app.include_router(catalog.router)
app.include_router(cart.router)
app.include_router(orders.router)
app.include_router(analytics.router)
app.include_router(events.router)
app.include_router(ml.router)


@app.middleware("http")
async def anon_session(request: Request, call_next):
    """Give every browser a stable guest id so a cart survives until login.

    Handlers read it with services.auth.get_anon_id. Setting the cookie here
    means it lands on whatever response the handler returns.
    """
    anon = request.cookies.get(ANON_COOKIE)
    is_new = anon is None
    request.state.anon_id = anon or new_anon_id()
    response = await call_next(request)
    if is_new:
        set_anon_cookie(response, request.state.anon_id)
    return response


@app.exception_handler(LoginRequired)
async def login_required_handler(request: Request, exc: LoginRequired):
    return RedirectResponse(
        f"/login?next={quote(exc.next_path, safe='/')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.get("/healthz", tags=["meta"])
def health():
    return {"status": "ok", "env": settings.app_env}
