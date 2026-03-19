"""
seed_supabase.py — Run ONCE to seed Supabase from your Excel.

Key handling:
  - 16 Feb 2026 rows = BASELINE (cumulative decisions before tracking started)
    → is_baseline = True, kept for IRL lookup and stats
    → EXCLUDED from velocity chart (not a real single-day count)
  - 18 Feb 2026 onwards = TRUE DAILY decisions
    → is_baseline = False, shown in velocity chart

Run from your computer:
  pip install supabase pandas openpyxl
  
  Windows:   set SUPABASE_URL=https://xxx.supabase.co
             set SUPABASE_KEY=your-service-role-key
  Mac/Linux: export SUPABASE_URL=https://xxx.supabase.co
             export SUPABASE_KEY=your-service-role-key
  
  python seed_supabase.py
"""

import os, sys, pandas as pd
from datetime import date

try:
    from supabase import create_client
except ImportError:
    print("Run: pip install supabase pandas openpyxl")
    sys.exit(1)

SUPABASE_URL = os.environ.get("SUPABASE_URL","")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY","")
EXCEL_FILE   = "VISA_DECISONS_2026_FILTERED.xlsx"
BATCH_SIZE   = 500
BASELINE_DATE = date(2026, 2, 16)   # all rows on this date = baseline

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Set SUPABASE_URL and SUPABASE_KEY env variables first.")
    sys.exit(1)

if not os.path.exists(EXCEL_FILE):
    print(f"File not found: {EXCEL_FILE}")
    print("Place VISA_DECISONS_2026_FILTERED.xlsx next to this script.")
    sys.exit(1)

print(f"Reading {EXCEL_FILE}...")
df = pd.read_excel(EXCEL_FILE, sheet_name="Sheet1")
df["Application Number"] = df["Application Number"].astype(int)
df["VISA Decision Date"]  = pd.to_datetime(df["VISA Decision Date"]).dt.date
df["irl_series"]          = df["Application Number"].astype(str).str[:4].astype(int)
df["irl_suffix"]          = df["Application Number"].astype(str).str[4:].astype(int)
df["is_baseline"]         = df["VISA Decision Date"] == BASELINE_DATE
df["decision_week"]       = pd.to_datetime(df["VISA Decision Date"]).apply(
    lambda d: f"{d.isocalendar().year}-W{d.isocalendar().week:02d}")

total      = len(df)
baseline_n = df["is_baseline"].sum()
daily_n    = total - baseline_n

print(f"\nFile summary:")
print(f"  Total rows:          {total:,}")
print(f"  Baseline (16 Feb):   {baseline_n:,}  ← cumulative, not one day's work")
print(f"  True daily (18 Feb+): {daily_n:,}  ← real day-by-day decisions")
print(f"  Date range:          {df['VISA Decision Date'].min()} → {df['VISA Decision Date'].max()}")
print(f"  Unique true dates:   {df[~df['is_baseline']]['VISA Decision Date'].nunique()}")

print(f"\nConnecting to Supabase...")
sb = create_client(SUPABASE_URL, SUPABASE_KEY)
print("  Connected")

rows = [
    {
        "irl_series":    int(r["irl_series"]),
        "irl_suffix":    int(r["irl_suffix"]),
        "decision":      str(r["Decision"]),
        "decision_date": str(r["VISA Decision Date"]),
        "decision_week": str(r["decision_week"]),
        "is_baseline":   bool(r["is_baseline"]),
    }
    for _, r in df.iterrows()
]

print(f"\nUploading {len(rows):,} rows to ods_dates table...")
ok = 0
for i in range(0, len(rows), BATCH_SIZE):
    batch = rows[i : i + BATCH_SIZE]
    try:
        sb.table("ods_dates").upsert(
            batch, on_conflict="irl_series,irl_suffix"
        ).execute()
        ok += len(batch)
        print(f"  {ok:,}/{len(rows):,} ({round(ok/len(rows)*100)}%)", end="\r")
    except Exception as e:
        print(f"\n  Batch error at row {i}: {e}")

print(f"\n  Done — {ok:,} rows uploaded")
print(f"\n{'='*55}")
print(f"Seed complete.")
print(f"  {baseline_n:,} rows marked is_baseline=True (excluded from velocity chart)")
print(f"  {daily_n:,} rows marked is_baseline=False (shown in velocity chart)")
print(f"  ALL rows available for: IRL lookup, approval stats, series analysis")
print(f"{'='*55}")
