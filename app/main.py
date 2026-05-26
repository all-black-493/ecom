from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import analytics, catalog, events, ml, orders, pages
from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title="Lumen Commerce",
    description="Ecommerce backend + embedded analytics",
    version="0.1.0",
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

# UI pages
app.include_router(pages.router)
# JSON API
app.include_router(catalog.router)
app.include_router(orders.router)
app.include_router(analytics.router)
app.include_router(events.router)
app.include_router(ml.router)


@app.get("/healthz", tags=["meta"])
def health():
    return {"status": "ok", "env": settings.app_env}
