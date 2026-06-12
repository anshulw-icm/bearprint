import os
from datetime import date, timedelta
from typing import Optional
import requests as req
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Bearprint API", version="0.3.0")
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
    return {"status": "ok", "service": "Bearprint API v0.3"}

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/today")
def get_today():
    rows = db_get("bearprint_daily", {"select": "*", "order": "date.desc", "limit": "1"})
    if not rows or not isinstance(rows, list):
        raise HTTPException(status_code=404, detail="No data yet.")
    return rows[0]

@app.get("/history")
def get_history(days: int = 30, month: Optional[str] = None):
    """
    Returns history data.
    - days: number of recent trading days (default 30, max 180)
    - month: filter by month e.g. '2026-01' returns all data for January 2026
    """
    if month:
        # Parse month filter e.g. '2026-01'
        try:
            y, m = int(month.split("-")[0]), int(month.split("-")[1])
            month_start = date(y, m, 1).isoformat()
            if m == 12:
                month_end = date(y+1, 1, 1).isoformat()
            else:
                month_end = date(y, m+1, 1).isoformat()
            rows = db_get("bearprint_daily", {
                "select": "*",
                "date": f"gte.{month_start}",
                "date": f"lt.{month_end}",
                "order": "date.asc",
                "limit": "31"
            })
            # Supabase only allows one 'date' param — use range differently
            rows = db_get("bearprint_daily", {
                "select": "*",
                "and": f"(date.gte.{month_start},date.lt.{month_end})",
                "order": "date.asc",
                "limit": "31"
            })
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid month format. Use YYYY-MM")
    else:
        days = min(days, 180)
        since = (date.today() - timedelta(days=days + 20)).isoformat()
        rows = db_get("bearprint_daily", {
            "select": "*",
            "date": f"gte.{since}",
            "order": "date.asc",
            "limit": str(min(days + 30, 250))  # extra buffer since we skip holidays
        })

    if not isinstance(rows, list):
        return {"days": 0, "data": []}
    return {"days": len(rows), "data": rows}

@app.get("/months")
def get_available_months():
    """Returns list of months that have data, for the month selector UI."""
    rows = db_get("bearprint_daily", {
        "select": "date",
        "order": "date.asc",
        "limit": "180"
    })
    if not isinstance(rows, list):
        return {"months": []}
    seen = set()
    months = []
    for r in rows:
        m = r["date"][:7]  # e.g. '2026-01'
        if m not in seen:
            seen.add(m)
            months.append(m)
    return {"months": months}

@app.get("/etf/today")
def get_etf_today():
    rows = db_get("bearprint_daily", {"select": "*", "order": "date.desc", "limit": "1"})
    if not rows or not isinstance(rows, list):
        raise HTTPException(status_code=404, detail="No data yet.")
    today = rows[0]
    history = db_get("bearprint_daily", {
        "select": "date,bp_value,bpx_nav,zone,bpx_change",
        "order": "date.asc",
        "limit": "180"
    })
    if not isinstance(history, list):
        history = []

    bp = float(today.get("bp_value", 50))
    bpx_nav = float(today.get("bpx_nav", 100))
    bpx_change = float(today.get("bpx_change", 0))
    nifty_change = round(-(bp - 50) * 0.4, 2)
    sim_nifty      = round(100000 * (1 + nifty_change/100), 0)
    sim_80_20      = round(100000 * (0.8*(1+nifty_change/100) + 0.2*(1+bpx_change/100)), 0)
    sim_60_40      = round(100000 * (0.6*(1+nifty_change/100) + 0.4*(1+bpx_change/100)), 0)

    return {
        "ticker": "BPX",
        "name": "Bearprint Inverse Index ETF",
        "date": today["date"],
        "nav": bpx_nav,
        "change_pct": bpx_change,
        "bp_value": bp,
        "zone": today.get("zone"),
        "base_nav": 100.0,
        "crash_sim": {
            "invested": 100000,
            "nifty_change_pct": nifty_change,
            "nifty_only": int(sim_nifty),
            "mix_80_20": int(sim_80_20),
            "mix_60_40": int(sim_60_40),
        },
        "history": history,
        "disclaimer": "BPX is a simulated ETF. Not a real instrument. Not financial advice.",
    }

@app.post("/feedback")
def post_feedback(payload: FeedbackPayload, request: Request):
    db_insert("feedback", {
        "q1": payload.q1, "q2": payload.q2, "q3": payload.q3,
        "bp_at_time": payload.bp_at_time,
        "user_agent": request.headers.get("user-agent","")[:200],
    })
    return {"status": "saved"}
