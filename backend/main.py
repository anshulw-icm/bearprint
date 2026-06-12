import os
from datetime import date, timedelta
from typing import Optional
import requests as req
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Bearprint API", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET","POST"], allow_headers=["*"])

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

def db_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }

def db_get(table, params):
    r = req.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=db_headers(), params=params)
    return r.json()

def db_insert(table, row):
    req.post(f"{SUPABASE_URL}/rest/v1/{table}", headers=db_headers(), json=row)

class FeedbackPayload(BaseModel):
    q1: Optional[str] = None
    q2: Optional[str] = None
    q3: Optional[str] = None
    bp_at_time: Optional[float] = None

@app.get("/")
def root():
    return {"status": "ok", "service": "Bearprint API v0.2"}

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/today")
def get_today():
    rows = db_get("bearprint_daily", {
        "select": "*",
        "order": "date.desc",
        "limit": "1"
    })
    if not rows or not isinstance(rows, list):
        raise HTTPException(status_code=404, detail="No data yet.")
    return rows[0]

@app.get("/history")
def get_history(days: int = 30):
    since = (date.today() - timedelta(days=days + 10)).isoformat()
    rows = db_get("bearprint_daily", {
        "select": "*",
        "date": f"gte.{since}",
        "order": "date.asc",
        "limit": str(days)
    })
    if not isinstance(rows, list):
        return {"days": 0, "data": []}
    return {"days": len(rows), "data": rows}

@app.get("/etf/today")
def get_etf_today():
    """Returns today's BPX ETF NAV and performance metrics."""
    rows = db_get("bearprint_daily", {
        "select": "*",
        "order": "date.desc",
        "limit": "1"
    })
    if not rows or not isinstance(rows, list):
        raise HTTPException(status_code=404, detail="No data yet.")
    today = rows[0]

    # Get 30 days for crash simulation
    history = db_get("bearprint_daily", {
        "select": "date,bp_value,bpx_nav,zone",
        "order": "date.desc",
        "limit": "30"
    })
    if not isinstance(history, list):
        history = []

    bp = float(today.get("bp_value", 50))
    bpx_nav = float(today.get("bpx_nav", 100))
    bpx_change = float(today.get("bpx_change", 0))

    # Crash simulation: ₹1L invested, how does portfolio perform today
    nifty_change = round(-(bp - 50) * 0.4, 2)  # rough inverse of breadth
    sim_nifty_only      = round(100000 * (1 + nifty_change/100), 0)
    sim_80_20           = round(100000 * (0.8 * (1 + nifty_change/100) + 0.2 * (1 + bpx_change/100)), 0)
    sim_60_40           = round(100000 * (0.6 * (1 + nifty_change/100) + 0.4 * (1 + bpx_change/100)), 0)

    return {
        "ticker": "BPX",
        "name": "Bearprint Inverse Index ETF",
        "date": today["date"],
        "nav": bpx_nav,
        "change_pct": bpx_change,
        "bp_value": bp,
        "zone": today.get("zone"),
        "base_nav": 100.0,
        "formula": "NAV = max(1, 100 + (bearprint - 50) × 2.5)",
        "crash_sim": {
            "invested": 100000,
            "currency": "INR",
            "nifty_change_pct": nifty_change,
            "nifty_only": int(sim_nifty_only),
            "mix_80_20": int(sim_80_20),
            "mix_60_40": int(sim_60_40),
        },
        "history": list(reversed(history)),
        "disclaimer": "BPX is a simulated ETF for research purposes. Not a real financial instrument. Not financial advice.",
    }

@app.post("/feedback")
def post_feedback(payload: FeedbackPayload, request: Request):
    db_insert("feedback", {
        "q1": payload.q1,
        "q2": payload.q2,
        "q3": payload.q3,
        "bp_at_time": payload.bp_at_time,
        "user_agent": request.headers.get("user-agent", "")[:200],
    })
    return {"status": "saved"}
