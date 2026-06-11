"""
bearprint/backend/compute.py
Downloads NSE Bhavcopy, computes Bearprint index, saves to Supabase.
Run daily at 4pm IST via GitHub Actions (see scheduler/cron.yml).
"""

import os
import io
import zipfile
import requests
import pandas as pd
from datetime import date, timedelta
from supabase import create_client, Client

# ── CONFIG ────────────────────────────────────────────────────────────────────
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

# Nifty 500 constituent symbols (loaded from file or env)
# For POC, we use all EQ series stocks as a proxy (typically ~1800 stocks)
# In production: replace with exact Nifty 500 list from NSE
NIFTY500_URL = "https://raw.githubusercontent.com/your-repo/bearprint/main/data/nifty500.csv"

BHAVCOPY_URL_TEMPLATE = (
    "https://nsearchives.nseindia.com/content/cm/"
    "BhavCopy_NSE_CM_0_0_0_{date_fmt}_F_0000.csv.zip"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Referer": "https://www.nseindia.com",
    "Accept-Language": "en-US,en;q=0.9",
}

# ── FETCH BHAVCOPY ─────────────────────────────────────────────────────────────
def fetch_bhavcopy(trade_date: date) -> pd.DataFrame:
    """
    Downloads NSE Bhavcopy ZIP for a given date and returns a DataFrame.
    Columns we care about: TckrSymb, PrvsClsgPric, ClsPric, SctySrs
    """
    date_fmt = trade_date.strftime("%d%m%Y")
    url = BHAVCOPY_URL_TEMPLATE.format(date_fmt=date_fmt)

    print(f"Fetching Bhavcopy for {trade_date}: {url}")

    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    # Unzip in memory
    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        csv_name = [n for n in z.namelist() if n.endswith(".csv")][0]
        with z.open(csv_name) as f:
            df = pd.read_csv(f)

    print(f"  Loaded {len(df)} rows from Bhavcopy")
    return df


# ── COMPUTE BEARPRINT ─────────────────────────────────────────────────────────
def compute_bearprint(df: pd.DataFrame) -> dict:
    """
    Given a raw Bhavcopy DataFrame, computes the Bearprint index value.

    Returns a dict with:
      - bp_value     : float (0-100)
      - losers       : int   (stocks that closed below prev close)
      - total        : int   (universe size)
      - zone         : str   ('calm' | 'caution' | 'crash')
    """
    # Filter to EQ series only (excludes ETFs, bonds, SME)
    eq = df[df["SctySrs"] == "EQ"].copy()

    # Rename for clarity
    eq = eq.rename(columns={
        "TckrSymb":    "symbol",
        "PrvsClsgPric": "prev_close",
        "ClsPric":      "close",
    })

    # Drop rows with missing prices
    eq = eq.dropna(subset=["prev_close", "close"])
    eq = eq[eq["prev_close"] > 0]

    total = len(eq)
    losers = int((eq["close"] < eq["prev_close"]).sum())
    bp_value = round((losers / total) * 100, 2) if total > 0 else 0.0

    zone = (
        "crash"   if bp_value >= 65 else
        "caution" if bp_value >= 45 else
        "calm"
    )

    print(f"  Bearprint: {bp_value} | Losers: {losers}/{total} | Zone: {zone}")

    return {
        "bp_value": bp_value,
        "losers":   losers,
        "total":    total,
        "zone":     zone,
    }


# ── ROLLING 7-DAY AVERAGE ─────────────────────────────────────────────────────
def compute_avg7d(supabase: Client, today: date) -> float:
    """
    Fetches last 6 days of Bearprint from DB, averages with today's value.
    Called AFTER today's row is inserted.
    """
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
    avg = round(sum(r["bp_value"] for r in rows) / len(rows), 2)
    return avg


# ── SAVE TO SUPABASE ──────────────────────────────────────────────────────────
def save_to_db(supabase: Client, trade_date: date, result: dict, avg7d: float):
    """
    Upserts today's Bearprint row into bearprint_daily table.
    Uses upsert so re-runs are idempotent.
    """
    row = {
        "date":     trade_date.isoformat(),
        "bp_value": result["bp_value"],
        "losers":   result["losers"],
        "total":    result["total"],
        "zone":     result["zone"],
        "avg_7d":   avg7d,
    }
    supabase.table("bearprint_daily").upsert(row).execute()
    print(f"  Saved to DB: {row}")


# ── MAIN ──────────────────────────────────────────────────────────────────────
def run(trade_date: date = None):
    trade_date = trade_date or date.today()

    print(f"\n=== Bearprint compute run: {trade_date} ===")

    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    # 1. Fetch raw data
    df = fetch_bhavcopy(trade_date)

    # 2. Compute index
    result = compute_bearprint(df)

    # 3. Save preliminary row (avg_7d=0 placeholder)
    save_to_db(supabase, trade_date, result, avg7d=0.0)

    # 4. Now compute rolling avg including today and update
    avg7d = compute_avg7d(supabase, trade_date)
    supabase.table("bearprint_daily").update({"avg_7d": avg7d}).eq("date", trade_date.isoformat()).execute()

    print(f"  Updated avg_7d: {avg7d}")
    print(f"=== Done ===\n")

    return {**result, "date": trade_date.isoformat(), "avg_7d": avg7d}


if __name__ == "__main__":
    run()
