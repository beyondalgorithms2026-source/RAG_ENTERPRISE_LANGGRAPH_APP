"""Deployment guards for the hosted demo: browser allow-list (CORS) and daily/monthly spend caps.

The app itself already serves GET /healthz ({"status": "ok"}, no backend or model call).

Spend is counted in SQLite (SPEND_DB_PATH, default /data/spend.sqlite, ./data/spend.sqlite when /data is missing or
APP_ENV=local). This app does not receive token counts from the model layer, so each answered question that can call a
model is counted at EST_COST_PER_CALL_USD (default 0.01: one governed question makes several model calls). Over
DAILY_SPEND_CAP_USD (default 0.50) or MONTHLY_SPEND_CAP_USD (default 5) those requests answer HTTP 429 with a plain
message. Read-only evidence pages and /healthz stay available. A broken ledger never blocks visitors.
"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import Optional

DEFAULT_ORIGINS = "https://spanfold.com,https://www.spanfold.com"
LOCAL_ORIGIN_REGEX = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
DEFAULT_DAILY = 0.50
DEFAULT_MONTHLY = 5.00
DEFAULT_EST_PER_CALL = 0.01
# Requests that can call a model through the orchestrator.
PAID_POSTS = ("/ask", "/ask-orchestrated", "/demo/before-after", "/eval/run", "/red-team/run")
MSG_DAILY = "This demo has reached its daily limit. Please try again tomorrow."
MSG_MONTHLY = "This demo has reached its monthly limit. Please try again next month."


def _env_float(name: str, default: float) -> float:
    try:
        v = float(os.environ.get(name, "").strip())
        return v if v >= 0 else default
    except ValueError:
        return default


def is_local() -> bool:
    return os.environ.get("APP_ENV", "").strip().lower() == "local"


def allowed_origins() -> list:
    raw = os.environ.get("ALLOWED_ORIGINS", "").strip() or DEFAULT_ORIGINS
    return [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]


def spend_db_path() -> Path:
    p = os.environ.get("SPEND_DB_PATH", "").strip()
    if p:
        return Path(p)
    data = Path("/data")
    if not is_local() and data.is_dir() and os.access(data, os.W_OK):
        return data / "spend.sqlite"
    return Path("./data/spend.sqlite")


def _connect() -> sqlite3.Connection:
    p = spend_db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(p), timeout=5)
    db.execute("CREATE TABLE IF NOT EXISTS spend (ts REAL, day TEXT, month TEXT, demo TEXT, usd REAL)")
    db.execute("CREATE INDEX IF NOT EXISTS spend_day ON spend(day)")
    return db


def totals(now: Optional[float] = None) -> tuple:
    """(dollars today, dollars this month), UTC calendar."""
    t = time.gmtime(now if now is not None else time.time())
    day, month = time.strftime("%Y-%m-%d", t), time.strftime("%Y-%m", t)
    db = _connect()
    try:
        d = db.execute("SELECT COALESCE(SUM(usd),0) FROM spend WHERE day=?", (day,)).fetchone()[0]
        m = db.execute("SELECT COALESCE(SUM(usd),0) FROM spend WHERE month=?", (month,)).fetchone()[0]
    finally:
        db.close()
    return float(d), float(m)


def over_cap(now: Optional[float] = None) -> Optional[str]:
    try:
        d, m = totals(now)
    except (sqlite3.Error, OSError, ValueError):
        return None
    if d >= _env_float("DAILY_SPEND_CAP_USD", DEFAULT_DAILY):
        return "daily"
    if m >= _env_float("MONTHLY_SPEND_CAP_USD", DEFAULT_MONTHLY):
        return "monthly"
    return None


def record_spend(usd: Optional[float] = None, label: str = "", now: Optional[float] = None) -> float:
    """Add one paid call: the real cost when known (> 0), otherwise EST_COST_PER_CALL_USD."""
    amount = float(usd) if usd and usd > 0 else _env_float("EST_COST_PER_CALL_USD", DEFAULT_EST_PER_CALL)
    ts = now if now is not None else time.time()
    t = time.gmtime(ts)
    try:
        db = _connect()
        try:
            db.execute(
                "INSERT INTO spend VALUES (?,?,?,?,?)",
                (ts, time.strftime("%Y-%m-%d", t), time.strftime("%Y-%m", t), label, amount),
            )
            db.commit()
        finally:
            db.close()
    except (sqlite3.Error, OSError, ValueError):
        pass
    return amount


def install(app) -> None:
    """Add the spend gate, then CORS (last, so it is the outer layer and 429 replies carry CORS headers)."""
    from fastapi.responses import JSONResponse
    from starlette.middleware.cors import CORSMiddleware

    @app.middleware("http")
    async def _spend_gate(request, call_next):
        paid = request.method == "POST" and request.url.path.rstrip("/") in PAID_POSTS
        if paid:
            scope = over_cap()
            if scope:
                return JSONResponse(
                    {
                        "detail": MSG_DAILY if scope == "daily" else MSG_MONTHLY,
                        "error": "demo_limit_reached",
                        "limit": scope,
                    },
                    status_code=429,
                    headers={"Retry-After": "3600", "Cache-Control": "no-store"},
                )
        response = await call_next(request)
        if paid and response.status_code < 500 and response.status_code not in (403, 404, 422):
            record_spend(None, request.url.path)
        return response

    kw = dict(allow_origins=allowed_origins(), allow_methods=["GET"], allow_headers=[])
    if is_local():
        kw["allow_origin_regex"] = LOCAL_ORIGIN_REGEX
    app.add_middleware(CORSMiddleware, **kw)
