"""
backfill.py
Downloads real NSE Bhavcopy for each trading day over the last 6 months
and computes + stores real Bearprint and BPX NAV for each day.

Run once from your terminal:
  cd ~/Downloads/bearprint/backend
  SUPABASE_URL="..." SUPABASE_KEY="..." python3 backfill.py

Takes ~10-15 minutes to run (one HTTP request per trading day ~130 days).
NSE sometimes throttles — script retries automatically with a delay.
"""

import os, io, csv, time, zipfile
from datetime import date, timedelta
import requests

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Referer": "https://www.nseindia.com",
    "Accept-Language": "en-US,en;q=0.9",
}

# ── DB ────────────────────────────────────────────────────────────────────────
def db(method, path, **kwargs):
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }
    r = requests.request(method, url, headers=headers, **kwargs)
    return r

def get_existing_dates():
    """Fetch all dates already in DB so we skip them."""
    r = db("GET", "bearprint_daily", params={
        "select": "date",
        "order": "date.asc",
        "limit": "500"
    })
    rows = r.json()
    if not isinstance(rows, list):
        return set()
    return {row["date"] for row in rows}

def get_prev_nav(trade_date: date):
    """Get the most recent BPX NAV before this date for change calculation."""
    yesterday = (trade_date - timedelta(days=1)).isoformat()
    r = db("GET", "bearprint_daily", params={
        "select": "bpx_nav",
        "date": f"lte.{yesterday}",
        "order": "date.desc",
        "limit": "1"
    })
    rows = r.json()
    if isinstance(rows, list) and rows and rows[0].get("bpx_nav"):
        return float(rows[0]["bpx_nav"])
    return None  # no previous — first entry

# ── FETCH ─────────────────────────────────────────────────────────────────────
def fetch_bhavcopy(trade_date: date, retries=3):
    date_fmt = trade_date.strftime("%d%m%Y")
    url = f"https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{date_fmt}.csv"

    for attempt in range(retries):
        try:
            r = requests.get(url, headers=NSE_HEADERS, timeout=30)
            if r.status_code == 404:
                return None  # holiday or weekend — skip silently
            r.raise_for_status()
            rows = list(csv.DictReader(io.StringIO(r.text)))
            rows = [{k.strip(): v.strip() for k, v in row.items()} for row in rows]
            return rows
        except Exception as e:
            if attempt < retries - 1:
                wait = (attempt + 1) * 5
                print(f"    Retry {attempt+1} after {wait}s — {e}")
                time.sleep(wait)
            else:
                print(f"    Failed after {retries} attempts: {e}")
                return None

# ── COMPUTE ───────────────────────────────────────────────────────────────────
def compute(rows):
    total = losers = 0
    for r in rows:
        if r.get("SERIES", "").strip() != "EQ":
            continue
        try:
            prev  = float(r.get("PREV_CLOSE") or 0)
            close = float(r.get("CLOSE_PRICE") or 0)
            if prev <= 0:
                continue
            total += 1
            if close < prev:
                losers += 1
        except (ValueError, TypeError):
            continue
    if total == 0:
        return None
    bp = round((losers / total) * 100, 2)
    zone = "crash" if bp >= 65 else "caution" if bp >= 45 else "calm"
    bpx_nav = round(max(1.0, 100 + (bp - 50) * 2.5), 2)
    return {"bp_value": bp, "losers": losers, "total": total, "zone": zone, "bpx_nav": bpx_nav}

# ── SAVE ──────────────────────────────────────────────────────────────────────
def save(trade_date: date, result: dict, bpx_change: float):
    row = {
        "date": trade_date.isoformat(),
        "bp_value": result["bp_value"],
        "losers": result["losers"],
        "total": result["total"],
        "zone": result["zone"],
        "bpx_nav": result["bpx_nav"],
        "bpx_change": bpx_change,
        "avg_7d": 0.0,  # updated in second pass
    }
    r = db("POST", "bearprint_daily", json=row)
    return r.status_code

def update_avg7d(trade_date: date):
    since = (trade_date - timedelta(days=10)).isoformat()
    rows = db("GET", "bearprint_daily", params={
        "select": "bp_value",
        "date": f"gte.{since}",
        "order": "date.desc",
        "limit": "7"
    }).json()
    if not isinstance(rows, list) or not rows:
        return 0.0
    avg = round(sum(r["bp_value"] for r in rows) / len(rows), 2)
    db("PATCH", f"bearprint_daily?date=eq.{trade_date.isoformat()}", json={"avg_7d": avg})
    return avg

# ── MAIN ──────────────────────────────────────────────────────────────────────
def run_backfill():
    today = date.today()
    start = today - timedelta(days=183)  # ~6 months back

    print(f"\n=== Bearprint Backfill: {start} → {today} ===\n")

    # Get dates already in DB — skip those
    existing = get_existing_dates()
    print(f"Already in DB: {len(existing)} dates — will skip these\n")

    # Generate all weekdays in range
    all_days = []
    d = start
    while d <= today:
        if d.weekday() < 5:  # Mon-Fri only
            all_days.append(d)
        d += timedelta(days=1)

    to_fetch = [d for d in all_days if d.isoformat() not in existing]
    print(f"Days to fetch: {len(to_fetch)}\n")

    processed = 0
    skipped = 0

    for trade_date in to_fetch:
        print(f"[{processed+skipped+1}/{len(to_fetch)}] {trade_date} ...", end=" ", flush=True)

        rows = fetch_bhavcopy(trade_date)
        if rows is None:
            print("→ no data (holiday/weekend)")
            skipped += 1
            time.sleep(1)  # be polite to NSE
            continue

        result = compute(rows)
        if result is None:
            print("→ compute failed (no EQ stocks)")
            skipped += 1
            continue

        prev_nav = get_prev_nav(trade_date)
        if prev_nav:
            bpx_change = round(((result["bpx_nav"] - prev_nav) / prev_nav) * 100, 2)
        else:
            bpx_change = 0.0

        status = save(trade_date, result, bpx_change)
        avg = update_avg7d(trade_date)

        print(f"→ BP={result['bp_value']} zone={result['zone']} NAV=₹{result['bpx_nav']} avg7d={avg} DB={status}")
        processed += 1

        time.sleep(1.5)  # 1.5s delay between requests — don't hammer NSE

    print(f"\n=== Done ===")
    print(f"Processed: {processed} days")
    print(f"Skipped:   {skipped} days (holidays/no data)")
    print(f"Total in DB now: {len(existing) + processed} days\n")

if __name__ == "__main__":
    run_backfill()
