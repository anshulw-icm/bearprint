import os, io, csv
import requests
from datetime import date, timedelta

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Referer": "https://www.nseindia.com",
    "Accept-Language": "en-US,en;q=0.9",
}

def db(method, path, **kwargs):
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }
    r = requests.request(method, url, headers=headers, **kwargs)
    print(f"  DB {method} {path} -> {r.status_code}")
    return r

def fetch_bhavcopy(trade_date: date):
    date_fmt = trade_date.strftime("%d%m%Y")
    url = f"https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{date_fmt}.csv"
    print(f"Fetching: {url}")
    r = requests.get(url, headers=NSE_HEADERS, timeout=30)
    if r.status_code == 404:
        print(f"  Bhavcopy not yet available for {trade_date} — market may still be open or holiday.")
        return None
    r.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(r.text)))
    rows = [{k.strip(): v.strip() for k, v in row.items()} for row in rows]
    print(f"  Loaded {len(rows)} rows")
    return rows

def compute_bearprint(rows):
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
    bp = round((losers / total) * 100, 2) if total > 0 else 0.0
    zone = "crash" if bp >= 65 else "caution" if bp >= 45 else "calm"
    bpx_nav = round(max(1.0, 100 + (bp - 50) * 2.5), 2)
    print(f"  BP={bp} losers={losers}/{total} zone={zone} BPX_NAV={bpx_nav}")
    return {"bp_value": bp, "losers": losers, "total": total, "zone": zone, "bpx_nav": bpx_nav}

def compute_avg7d(trade_date: date):
    since = (trade_date - timedelta(days=10)).isoformat()
    rows = db("GET", "bearprint_daily", params={
        "select": "bp_value",
        "date": f"gte.{since}",
        "order": "date.desc",
        "limit": "7"
    }).json()
    if not rows or not isinstance(rows, list):
        return 0.0
    return round(sum(r["bp_value"] for r in rows) / len(rows), 2)

def compute_bpx_prev_nav(trade_date: date):
    yesterday = (trade_date - timedelta(days=1)).isoformat()
    rows = db("GET", "bearprint_daily", params={
        "select": "bpx_nav",
        "date": f"lte.{yesterday}",
        "order": "date.desc",
        "limit": "1"
    }).json()
    if not rows or not isinstance(rows, list) or not rows[0].get("bpx_nav"):
        return 100.0
    return float(rows[0]["bpx_nav"])

def run(trade_date: date = None):
    trade_date = trade_date or date.today()
    print(f"\n=== Bearprint compute: {trade_date} ===")
    rows = fetch_bhavcopy(trade_date)
    if rows is None:
        print(f"  Skipping — no data available for {trade_date}. Will retry tomorrow.")
        return
    result = compute_bearprint(rows)
    prev_nav = compute_bpx_prev_nav(trade_date)
    bpx_change = round(((result["bpx_nav"] - prev_nav) / prev_nav) * 100, 2) if prev_nav else 0.0
    db("POST", "bearprint_daily", json={
        "date": trade_date.isoformat(),
        **result,
        "avg_7d": 0.0,
        "bpx_change": bpx_change,
    })
    avg7d = compute_avg7d(trade_date)
    db("PATCH", f"bearprint_daily?date=eq.{trade_date.isoformat()}", json={"avg_7d": avg7d})
    print(f"  avg_7d={avg7d} bpx_change={bpx_change}%")
    print("=== Done ===\n")

if __name__ == "__main__":
    run()
