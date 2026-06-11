import os
from datetime import date, timedelta
from typing import Optional
import requests as req
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Bearprint API", version="0.1.0")
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
    return {"status": "ok", "service": "Bearprint API v0.1"}

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/today")
def get_today():
    rows = db_get("bearprint_daily", {"select": "*", "order": "date.desc", "limit": "1"})
    if not rows or not isinstance(rows, list):
        raise HTTPException(status_code=404, detail="No data yet. Run the compute script first.")
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
