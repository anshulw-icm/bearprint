"""
bearprint/backend/main.py
FastAPI app — serves Bearprint data to the frontend.
Deploy free on Render.com (render.yaml included).
"""

import os
from datetime import date, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client, Client

# ── APP SETUP ─────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Bearprint API",
    description="Market breadth index for Nifty 500",
    version="0.1.0",
)

# Allow your frontend origin (update with your actual domain)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ── SUPABASE CLIENT ───────────────────────────────────────────────────────────
def get_db() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_KEY"]
    return create_client(url, key)


# ── MODELS ────────────────────────────────────────────────────────────────────
class FeedbackPayload(BaseModel):
    q1: Optional[str] = None   # "yes" | "maybe" | "no"
    q2: Optional[str] = None   # "hedge" | "hold" | "sell" | "nothing"
    q3: Optional[str] = None   # free text
    bp_at_time: Optional[float] = None


class BhavprintDay(BaseModel):
    date:     str
    bp_value: float
    losers:   int
    total:    int
    zone:     str
    avg_7d:   float


# ── HELPERS ───────────────────────────────────────────────────────────────────
def zone_label(bp: float) -> str:
    if bp >= 65: return "crash"
    if bp >= 45: return "caution"
    return "calm"


# ── ENDPOINTS ─────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "ok", "service": "Bearprint API v0.1"}


@app.get("/today", response_model=BhavprintDay)
def get_today():
    """
    Returns the most recent trading day's Bearprint signal.
    The frontend uses this to render the hero number + insight banner.
    """
    db = get_db()
    resp = (
        db.table("bearprint_daily")
        .select("*")
        .order("date", desc=True)
        .limit(1)
        .execute()
    )

    if not resp.data:
        raise HTTPException(status_code=404, detail="No data yet. Run the compute script first.")

    return resp.data[0]


@app.get("/history")
def get_history(days: int = 30):
    """
    Returns last N trading days of Bearprint data for the chart and table.
    Frontend calls: fetch('/history?days=30')
    """
    if days > 365:
        raise HTTPException(status_code=400, detail="Max 365 days")

    since = (date.today() - timedelta(days=days + 10)).isoformat()  # buffer for weekends
    db = get_db()
    resp = (
        db.table("bearprint_daily")
        .select("*")
        .gte("date", since)
        .order("date", desc=False)
        .limit(days)
        .execute()
    )

    return {"days": len(resp.data), "data": resp.data}


@app.post("/feedback")
def post_feedback(payload: FeedbackPayload, request: Request):
    """
    Saves user feedback from the form at the bottom of the webapp.
    Stores alongside the current Bearprint value for context.
    """
    db = get_db()

    row = {
        "q1":         payload.q1,
        "q2":         payload.q2,
        "q3":         payload.q3,
        "bp_at_time": payload.bp_at_time,
        "user_agent": request.headers.get("user-agent", "")[:200],
    }

    db.table("feedback").insert(row).execute()
    return {"status": "saved", "message": "Thank you — your feedback is recorded."}


@app.get("/health")
def health():
    """Render.com health check endpoint."""
    return {"status": "healthy"}
