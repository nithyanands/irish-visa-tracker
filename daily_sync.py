"""
daily_sync.py — Irish Visa Tracker daily ODS sync
Run by GitHub Actions every weekday at 11:30 IST.

What it does:
  1. Fetches the latest ODS from Irish Embassy New Delhi
  2. Parses all Application Numbers + Decisions
  3. Queries Supabase for IRLs already in ods_dates
  4. Finds genuinely new rows
  5. Assigns the ODS file date as decision_date
  6. Upserts new rows to ods_dates with is_baseline=False
  7. Writes a log file (picked up by GitHub Actions artifacts)

Environment variables required:
  SUPABASE_URL         — your project URL
  SUPABASE_KEY         — service role key (not anon key)
"""

import os
import re
import sys
import requests
import pandas as pd
from io import BytesIO
from bs4 import BeautifulSoup
from datetime import date, timedelta, datetime
from zoneinfo import ZoneInfo

# ── Config ────────────────────────────────────────────────────────────────────
SUPABASE_URL  = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY  = os.environ.get("SUPABASE_KEY", "")
ND_PAGE_URL   = "https://www.ireland.ie/en/india/newdelhi/services/visas/processing-times-and-decisions/"
ODS_FOLDER    = "4526"
ODS_LINK_TXT  = "Visa decisions made from 1 January 2026 to"
BATCH_SIZE    = 500
IST           = ZoneInfo("Asia/Kolkata")

HOLIDAYS_2026 = {
    date(2026,1,1), date(2026,2,2), date(2026,3,17),
    date(2026,4,3), date(2026,4,6), date(2026,5,4),
    date(2026,6,1), date(2026,8,3), date(2026,10,26),
    date(2026,12,25), date(2026,12,26),
}
HOLIDAYS_2027 = {
    date(2027,1,1), date(2027,2,1), date(2027,3,17),
    date(2027,3,26), date(2027,3,29), date(2027,5,3),
    date(2027,6,7), date(2027,8,2), date(2027,10,25),
    date(2027,12,25), date(2027,12,26),
}
HOLIDAYS = HOLIDAYS_2026 | HOLIDAYS_2027

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/114.0.0.0 Safari/537.36")
}

LOG_LINES = []

def log(msg: str):
    ts = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    LOG_LINES.append(line)

def save_log():
    with open("sync_log.txt", "w") as f:
        f.write("\n".join(LOG_LINES))

# ── Helpers ───────────────────────────────────────────────────────────────────
def is_workday(d: date) -> bool:
    return d.weekday() < 5 and d not in HOLIDAYS

def prev_workday(d: date) -> date:
    cur = d - timedelta(days=1)
    while not is_workday(cur):
        cur -= timedelta(days=1)
    return cur

def last_n_workdays(n: int = 10) -> list:
    days, cur = [], date.today()
    if not is_workday(cur): cur = prev_workday(cur)
    while len(days) < n:
        days.append(cur)
        cur = prev_workday(cur)
    return days

def iso_week(d: date) -> str:
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"

# ── ODS fetch ─────────────────────────────────────────────────────────────────
def fetch_ods() -> tuple:
    """Returns (df, file_date) or (None, None)"""
    log("Fetching ODS from Irish Embassy New Delhi...")

    # Step 1: scan page for actual href
    page_urls = []
    try:
        r = requests.get(ND_PAGE_URL, headers=HEADERS, timeout=20)
        log(f"  Embassy page → HTTP {r.status_code}")
        if r.status_code == 200:
            soup = BeautifulSoup(r.content, "html.parser")
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                txt  = link.get_text(strip=True)
                if href.endswith(".ods") or ODS_LINK_TXT in txt or f"/{ODS_FOLDER}/" in href:
                    full = href if href.startswith("http") else f"https://www.ireland.ie{href}"
                    m = re.search(r"(\d{8})_NDVO", full)
                    if m:
                        fd = datetime.strptime(m.group(1), "%Y%m%d").date()
                        page_urls.append((fd, full))
                        log(f"  Found on page: {full.split('/')[-1]}")
    except Exception as e:
        log(f"  Page scan error: {e}")

    # Step 2: date-walker fallback
    walked = [
        (d, f"https://www.ireland.ie/{ODS_FOLDER}/{d.strftime('%Y%m%d')}_NDVO_Visa_Decisions.ods")
        for d in last_n_workdays(10)
    ]

    seen, all_urls = set(), []
    for item in sorted(page_urls, key=lambda x: x[0], reverse=True) + walked:
        if item[1] not in seen:
            seen.add(item[1])
            all_urls.append(item)

    # Step 3: try each URL
    for fd, url in all_urls:
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            log(f"  [{fd.strftime('%a %d %b')}] {url.split('/')[-1]} → HTTP {r.status_code}")
            if r.status_code == 200:
                df = parse_ods(r.content)
                if df is not None and len(df) > 0:
                    log(f"  ✅ Parsed {len(df):,} decisions from {url.split('/')[-1]}")
                    return df, fd
            elif r.status_code == 404:
                log(f"  (No file — weekend/holiday)")
        except requests.exceptions.ConnectionError as e:
            log(f"  ❌ Connection error: {str(e)[:100]}")
            return None, None
        except Exception as e:
            log(f"  ⚠️ {str(e)[:80]}")

    log("❌ Could not fetch ODS from any URL")
    return None, None

def parse_ods(content: bytes) -> pd.DataFrame | None:
    try:
        df_raw = pd.read_excel(BytesIO(content), engine="odf", header=None)
        app_col, dec_col, hr = None, None, None
        for ri in range(min(20, len(df_raw))):
            vals = [str(v).strip() for v in df_raw.iloc[ri].tolist()]
            for ci, v in enumerate(vals):
                if "application number" in v.lower() and app_col is None: app_col = ci
                if v.lower() == "decision" and dec_col is None:           dec_col = ci
            if app_col is not None and dec_col is not None:
                hr = ri; break
        if app_col is None: app_col, dec_col, hr = 2, 3, 10

        ds = hr + 1
        while ds < len(df_raw):
            v = str(df_raw.iloc[ds, app_col]).strip().lower()
            if "application" in v or v in ("nan", "none", ""): ds += 1
            else: break

        df = df_raw.iloc[ds:, [app_col, dec_col]].copy()
        df.columns = ["Application Number", "Decision"]
        df.dropna(how="all", inplace=True)
        df = df[df["Application Number"].notna()].copy()
        df["Application Number"] = (df["Application Number"].astype(str).str.strip()
                                     .str.replace(r"\.0+$", "", regex=True)
                                     .str.replace(r"\s+", "", regex=True))
        df = df[df["Application Number"].str.match(r"^\d{8}$")].copy()
        df["Application Number"] = df["Application Number"].astype(int)

        def norm(raw):
            r = str(raw or "").strip().lower()
            if any(w in r for w in ("approv","grant")): return "Approved"
            if any(w in r for w in ("refus","reject")):  return "Refused"
            if "withdr" in r: return "Withdrawn"
            return "Unknown"

        df["Decision"] = df["Decision"].astype(str).apply(norm)
        df = df[df["Decision"] != "Unknown"].copy()
        return df.reset_index(drop=True)
    except Exception as e:
        log(f"  Parse error: {e}")
        return None

# ── Supabase ──────────────────────────────────────────────────────────────────
def get_supabase():
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def get_existing_irls(sb) -> set:
    """Fetch all (irl_series, irl_suffix) pairs already in ods_dates."""
    log("Querying Supabase for existing IRL pairs...")
    existing = set()
    page_size = 1000
    offset    = 0
    while True:
        data = (sb.table("ods_dates")
                  .select("irl_series,irl_suffix")
                  .range(offset, offset + page_size - 1)
                  .execute().data)
        if not data:
            break
        for row in data:
            existing.add((int(row["irl_series"]), int(row["irl_suffix"])))
        if len(data) < page_size:
            break
        offset += page_size
    log(f"  {len(existing):,} existing IRL pairs in ods_dates")
    return existing

def upsert_new_rows(sb, rows: list) -> int:
    """Upsert rows in batches. Returns count inserted."""
    ok = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        try:
            sb.table("ods_dates").upsert(
                batch, on_conflict="irl_series,irl_suffix"
            ).execute()
            ok += len(batch)
        except Exception as e:
            log(f"  ⚠️ Batch error at offset {i}: {e}")
    return ok

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    now_ist = datetime.now(IST)
    log("=" * 55)
    log(f"Irish Visa Tracker — Daily Sync")
    log(f"Run time: {now_ist.strftime('%A %d %b %Y %H:%M IST')}")
    log("=" * 55)

    # Validate credentials
    if not SUPABASE_URL or not SUPABASE_KEY:
        log("❌ SUPABASE_URL or SUPABASE_KEY not set. Exiting.")
        save_log()
        sys.exit(1)

    # 1. Fetch ODS
    ods_df, file_date = fetch_ods()
    if ods_df is None:
        log("❌ ODS fetch failed. Exiting.")
        save_log()
        sys.exit(1)

    log(f"ODS file date: {file_date}")
    log(f"ODS total decisions: {len(ods_df):,}")

    # 2. Connect to Supabase
    log("Connecting to Supabase...")
    try:
        sb = get_supabase()
        log("  ✅ Connected")
    except Exception as e:
        log(f"  ❌ Connection failed: {e}")
        save_log()
        sys.exit(1)

    # 3. Get existing IRL pairs
    try:
        existing = get_existing_irls(sb)
    except Exception as e:
        log(f"❌ Could not query ods_dates: {e}")
        save_log()
        sys.exit(1)

    # 4. Find new rows
    new_rows = []
    for _, row in ods_df.iterrows():
        irl_str = str(int(row["Application Number"]))
        if len(irl_str) != 8: continue
        series = int(irl_str[:4])
        suffix = int(irl_str[4:])
        if (series, suffix) in existing:
            continue  # already in DB
        new_rows.append({
            "irl_series":    series,
            "irl_suffix":    suffix,
            "decision":      str(row["Decision"]),
            "decision_date": str(file_date),
            "decision_week": iso_week(file_date),
            "is_baseline":   False,   # daily additions are never baseline
        })

    log(f"New decisions to add: {len(new_rows):,}")

    if len(new_rows) == 0:
        log("✅ No new decisions — database is already up to date.")
        log(f"   (ODS has {len(ods_df):,} total, all already in DB)")
        save_log()
        return

    # 5. Upsert new rows
    log(f"Upserting {len(new_rows):,} new rows to ods_dates...")
    inserted = upsert_new_rows(sb, new_rows)

    # 6. Summary
    log("=" * 55)
    log(f"✅ Sync complete")
    log(f"   New decisions added:  {inserted:,}")
    log(f"   Decision date:        {file_date}")
    log(f"   Total in ods_dates:   ~{len(existing) + inserted:,}")

    # 7. Series breakdown of new rows
    if new_rows:
        series_counts = {}
        for r in new_rows:
            s = r["irl_series"]
            series_counts[s] = series_counts.get(s, 0) + 1
        top = sorted(series_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        log(f"   Top series in today's batch:")
        for s, c in top:
            log(f"     Series {s}: {c} new decisions")

    log("=" * 55)
    save_log()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        log(f"❌ Unhandled exception: {e}")
        log(traceback.format_exc())
        save_log()
        sys.exit(1)
