"""
bearprint/backend/compute.py
Downloads NSE Bhavcopy, computes Bearprint index, saves to Supabase.
No pandas dependency — uses Python's built-in csv module.
"""

import os
import io
import csv
import zipfile
import requests
from datetime import date, timedelta
from supabase import create_client, Client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

BHAVCOPY_URL_TEMPLATE = (
    "https://nsearchives.nseindia.com/content/cm/"
    "BhavCopy_NSE_CM_0_0_0_{date_fmt}_F_0000.csv.zip"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Referer": "https://www.nseindia.com",
    "Accept-Language": "en-US,en;q=0.9",
}

def fetch_bhavcopy(trade_date: date) -> list:
    date_fmt = trade_date.strftime("%d%m%Y")
    url = BHAVCOPY_URL_TEMPLATE.format(date_fmt=date_fmt)
    print(f"Fetching Bhavcopy for {trade_date}: {url}")
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        csv_name = [n for n in z.namelist() if n.endswith(".csv")][0]
        with z.open(csv_name) as f:
            content = f.read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(content))
    rows = list(reader)
    print(f"  Loaded {len(rows)} rows")
    return rows

def compute_bearprint(rows: list) -> dict:
    eq_rows = [r for r in rows if r.get("SctySrs", "").strip() == "EQ"]
    total = 0
    losers = 0
    for r in eq_rows:
        try:
            prev = float(r.get("PrvsClsgPric", 0) or 0)
            close = float(r.get("ClsPric", 0) or 0)
            if prev <= 0:
                continue
            total += 1
            if close < prev:
                losers += 1
        except (ValueError, TypeError):
            continue
    bp_value = round((losers / total) * 100, 2) if total > 0 else 0.0
    zone = "crash" if bp_value >= 65 else "caution" if bp_value >= 45 else "calm"
    print(f"  Bearprint: {bp_value} | Losers: {losers}/{total} | Zone: {zone}")
    return {"bp_value": bp_value, "losers": losers, "total": total, "zone": zone}

def compute_avg7d(supabase: Client, today: date) -> float:
    since = (today - timedelta(days=10)).isoformat()
    resp = (
        supabase.table("bearprint_daily")
        .select("date, bp_value")
        .gte("date", since)
        .order("date", desc=True)
        .limit(7)
        .execute()
    )
    rows = resp.data
    if not rows:
        return 0.0
    return round(sum(r["bp_value"] for r in rows) / len(rows), 2)

def save_to_db(supabase: Client, trade_date: date, result: dict, avg7d: float):
    row = {
        "date":     trade_date.isoformat(),
        "bp_value": result["bp_value"],
        "losers":   result["losers"],
        "total":    result["total"],
        "zone":     result["zone"],
        "avg_7d":   avg7d,
    }
    supabase.table("bearprint_daily").upsert(row).execute()
    print(f"  Saved: {row}")

def run(trade_date: date = None):
    trade_date = trade_date or date.today()
    print(f"\n=== Bearprint compute: {trade_date} ===")
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    rows = fetch_bhavcopy(trade_date)
    result = compute_bearprint(rows)
    save_to_db(supabase, trade_date, result, avg7d=0.0)
    avg7d = compute_avg7d(supabase, trade_date)
    supabase.table("bearprint_daily").update({"avg_7d": avg7d}).eq("date", trade_date.isoformat()).execute()
    print(f"  avg_7d updated: {avg7d}")
    print(f"=== Done ===\n")

if __name__ == "__main__":
    run()
