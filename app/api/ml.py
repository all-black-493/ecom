"""ML endpoints — serve the latest forecast.

In dev the forecast lives at app/static/forecast.json (written by
`python ml/run_forecast.py`). In production the Cloud Run Job writes
it to GCS; we proxy it through here so the dashboard's existing
`/static/forecast.json` fetch keeps working.

Set FORECAST_GCS_URI=gs://bucket/forecast.json to enable the proxy.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response

router = APIRouter(prefix="/api/ml", tags=["ml"])

_LOCAL_FALLBACK = Path("app/static/forecast.json")
_CACHE: dict = {"body": None, "fetched_at": 0.0, "ttl_seconds": 300}


def _read_from_gcs(uri: str) -> bytes | None:
    """Returns the forecast bytes from GCS, or None on any failure."""
    try:
        from google.cloud import storage  # type: ignore

        bucket_name, _, blob_path = uri[len("gs://") :].partition("/")
        client = storage.Client()
        return client.bucket(bucket_name).blob(blob_path).download_as_bytes()
    except Exception:
        return None


@router.get("/forecast")
def forecast() -> Response:
    """Latest demand forecast — GCS in prod, local file in dev. 5-minute cache."""
    now = time.time()
    if _CACHE["body"] and now - _CACHE["fetched_at"] < _CACHE["ttl_seconds"]:
        return Response(_CACHE["body"], media_type="application/json")

    uri = os.environ.get("FORECAST_GCS_URI", "").strip()
    body: bytes | None = None
    if uri.startswith("gs://"):
        body = _read_from_gcs(uri)
    if body is None and _LOCAL_FALLBACK.exists():
        body = _LOCAL_FALLBACK.read_bytes()
    if body is None:
        return JSONResponse({"error": "no forecast available"}, status_code=404)

    _CACHE["body"] = body
    _CACHE["fetched_at"] = now
    return Response(body, media_type="application/json")
