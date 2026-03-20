"""
database.py — Supabase layer for Irish Visa Tracker starter
Falls back to in-memory/empty if Supabase not configured.
All queries used by the app — no unused code.
"""

import streamlit as st
import pandas as pd
from datetime import date, timedelta
from typing import Optional
import json, os, re
from io import BytesIO
import requests
from bs4 import BeautifulSoup

# ── Constants ─────────────────────────────────────────────────────────────────
HOLIDAYS_2026 = {
    date(2026,1,1), date(2026,2,2), date(2026,3,17),
    date(2026,4,3), date(2026,4,6), date(2026,5,4),
    date(2026,6,1), date(2026,8,3), date(2026,10,26),
    date(2026,12,25), date(2026,12,26),
}
BRACKETS       = ["<7d","7-14d","14-21d","21-30d","30-40d","40d+"]
BRACKET_LABELS = {"<7d":"Under 7 days","7-14d":"7–14 days","14-21d":"14–21 days",
                  "21-30d":"21–30 days","30-40d":"30–40 days","40d+":"Over 40 days"}
ND_PAGE_URL    = "https://www.ireland.ie/en/india/newdelhi/services/visas/processing-times-and-decisions/"
DUBLIN_URL     = "https://www.irishimmigration.ie/visa-decisions/"
ODS_FOLDER     = "4526"
ODS_LINK_TXT   = "Visa decisions made from 1 January 2026 to"
SR05_UA        = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")
HEADERS        = {"User-Agent": SR05_UA}

# ── Helpers ───────────────────────────────────────────────────────────────────
def is_workday(d: date) -> bool:
    return d.weekday() < 5 and d not in HOLIDAYS_2026

def prev_workday(d: date) -> date:
    cur = d - timedelta(days=1)
    while not is_workday(cur): cur -= timedelta(days=1)
    return cur

def last_n_workdays(n: int = 10) -> list:
    days, cur = [], date.today()
    if not is_workday(cur): cur = prev_workday(cur)
    while len(days) < n:
        days.append(cur); cur = prev_workday(cur)
    return days

def calc_working_days(start: date, end: date = None) -> int:
    end = end or date.today()
    days, cur = 0, start
    while cur < end:
        cur += timedelta(days=1)
        if is_workday(cur): days += 1
    return days

def speed_bracket(wd: Optional[int]) -> Optional[str]:
    if wd is None: return None
    if wd <  7: return "<7d"
    if wd < 14: return "7-14d"
    if wd < 21: return "14-21d"
    if wd < 30: return "21-30d"
    if wd < 40: return "30-40d"
    return "40d+"

def add_workdays(d: date, n: int) -> date:
    cur, added = d, 0
    while added < n:
        cur += timedelta(days=1)
        if is_workday(cur): added += 1
    return cur

def parse_irl(s: str) -> dict | None:
    clean = re.sub(r"[^\d]","", str(s).lower().replace("irl",""))
    if len(clean) != 8: return None
    return {
        "irl": int(clean), "irl_str": clean,
        "series4d": int(clean[:4]),
        "suffix4":  int(clean[4:]),
        "prefix2":  int(clean[:2]),
    }

def norm_dec(raw) -> str:
    r = str(raw or "").strip().lower()
    if any(w in r for w in ("approv","grant")): return "Approved"
    if any(w in r for w in ("refus","reject")): return "Refused"
    if "withdr" in r: return "Withdrawn"
    return "Unknown"

# ── Supabase clients ──────────────────────────────────────────────────────────
# Two separate cached functions — one per key type.
# @st.cache_resource with parameters is unreliable across Streamlit versions;
# separate functions guarantee the correct client is always returned.

def _get_supabase_url() -> str:
    """Return normalised Supabase URL from secrets, or empty string."""
    try:
        url = st.secrets["supabase"].get("url", "").strip().rstrip("/")
        if "supabase.co" in url:
            parts = url.split("://", 1)
            if len(parts) == 2:
                url = parts[0] + "://" + parts[1].lower()
        return url
    except Exception:
        return ""

@st.cache_resource(show_spinner=False)
def _sb_anon():
    """Supabase client with anon key — for all read operations."""
    try:
        from supabase import create_client
        url = _get_supabase_url()
        key = st.secrets["supabase"].get("anon_key", "")
        if not url or not key:
            return None
        return create_client(url, key)
    except Exception:
        return None

@st.cache_resource(show_spinner=False)
def _sb_svc():
    """Supabase client with service_key — for all write operations."""
    try:
        from supabase import create_client
        url = _get_supabase_url()
        key = st.secrets["supabase"].get("service_key", "")
        if not url or not key:
            return None
        return create_client(url, key)
    except Exception:
        return None

# Backwards-compat shim — existing callers use _sb() and _sb("service")
def _sb(role: str = "anon"):
    return _sb_svc() if role == "service" else _sb_anon()

def _sb_ok() -> bool:
    return _sb_anon() is not None

def get_connection_status() -> dict:
    """
    Returns a dict describing the Supabase connection status.
    Used by the app to show clear error messages.
    """
    status = {"ok": False, "url_set": False, "anon_set": False, 
              "service_set": False, "url_value": "", "error": ""}
    try:
        if "supabase" not in st.secrets:
            status["error"] = "No [supabase] section in secrets"
            return status
        
        url = st.secrets["supabase"].get("url","").rstrip("/")
        anon = st.secrets["supabase"].get("anon_key","")
        svc  = st.secrets["supabase"].get("service_key","")
        
        status["url_set"]     = bool(url)
        status["anon_set"]    = bool(anon)
        status["service_set"] = bool(svc)
        status["url_value"]   = url[:40] if url else ""
        
        if not url:
            status["error"] = "url is empty in [supabase] secrets"
            return status
        if not url.startswith("https://"):
            status["error"] = f"url must start with https:// — got: {url[:30]}"
            return status
        if not url.endswith(".supabase.co"):
            status["error"] = f"url must end with .supabase.co — got: {url[-30:]}"
            return status
        if not anon:
            status["error"] = "anon_key is empty in [supabase] secrets"
            return status
        if not svc:
            status["error"] = "service_key is empty in [supabase] secrets"
            return status
        
        # Try actual connection
        # Test both keys
        from supabase import create_client
        anon_client = create_client(url, anon)
        anon_client.table("community").select("id").limit(1).execute()
        svc_client  = create_client(url, svc)
        svc_client.table("community").select("id").limit(1).execute()
        status["ok"] = True
        return status
    except Exception as e:
        status["error"] = str(e)
        return status

# ── ODS Fetch (New Delhi) ─────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_ods() -> tuple:
    """Returns (df, file_date, log)"""
    log = []
    try:
        import socket; socket.getaddrinfo("www.ireland.ie", 443)
        log.append("✅ Network OK")
    except Exception as e:
        log.append(f"❌ Network error: {e}")
        return None, None, log

    # Step 1: scan page for real href
    page_urls = []
    try:
        r = requests.get(ND_PAGE_URL, headers=HEADERS, timeout=15)
        log.append(f"Page → HTTP {r.status_code}")
        if r.status_code == 200:
            soup = BeautifulSoup(r.content, "html.parser")
            for link in soup.find_all("a", href=True):
                href, txt = link.get("href",""), link.get_text(strip=True)
                if href.endswith(".ods") or ODS_LINK_TXT in txt or f"/{ODS_FOLDER}/" in href:
                    full = href if href.startswith("http") else f"https://www.ireland.ie{href}"
                    m = re.search(r"(\d{8})_NDVO", full)
                    fd = __import__("datetime").datetime.strptime(m.group(1),"%Y%m%d").date() if m else date.today()
                    page_urls.append((fd, full))
                    log.append(f"✅ Found: {full.split('/')[-1]}")
    except Exception as e:
        log.append(f"⚠️ Page scan: {e}")

    # Step 2: date-walker
    walked = [(d, f"https://www.ireland.ie/{ODS_FOLDER}/{d.strftime('%Y%m%d')}_NDVO_Visa_Decisions.ods")
              for d in last_n_workdays(10)]
    seen, all_urls = set(), []
    for item in sorted(page_urls, key=lambda x: x[0], reverse=True) + walked:
        if item[1] not in seen: seen.add(item[1]); all_urls.append(item)

    for fd, url in all_urls:
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            log.append(f"[{fd.strftime('%a %d %b')}] {url.split('/')[-1]} → {r.status_code}")
            if r.status_code == 200:
                df = _parse_ods(r.content, log)
                if df is not None and len(df) > 0:
                    log.append(f"✅ {len(df):,} decisions loaded")
                    return df, fd, log
            elif r.status_code == 404:
                log.append(f"  (No file — weekend/holiday)")
        except requests.exceptions.ConnectionError as e:
            log.append(f"❌ Connection: {str(e)[:80]}")
            return None, None, log
        except Exception as e:
            log.append(f"⚠️ {str(e)[:60]}")

    log.append("❌ All strategies failed")
    return None, None, log

def _parse_ods(content: bytes, log: list) -> pd.DataFrame | None:
    try:
        df_raw = pd.read_excel(BytesIO(content), engine="odf", header=None)
        app_col, dec_col, hr = None, None, None
        for ri in range(min(20, len(df_raw))):
            vals = [str(v).strip() for v in df_raw.iloc[ri].tolist()]
            for ci, v in enumerate(vals):
                if "application number" in v.lower() and app_col is None: app_col = ci
                if v.lower() == "decision" and dec_col is None: dec_col = ci
            if app_col is not None and dec_col is not None: hr = ri; break
        if app_col is None: app_col, dec_col, hr = 2, 3, 10
        ds = hr + 1
        while ds < len(df_raw):
            v = str(df_raw.iloc[ds, app_col]).strip().lower()
            if "application" in v or v in ("nan","none",""): ds += 1
            else: break
        df = df_raw.iloc[ds:, [app_col, dec_col]].copy()
        df.columns = ["Application Number","Decision"]
        df.dropna(how="all", inplace=True)
        df["Application Number"] = (df["Application Number"].astype(str).str.strip()
                                     .str.replace(r"\.0+$","",regex=True)
                                     .str.replace(r"\s+","",regex=True))
        df = df[df["Application Number"].str.match(r"^\d{8}$")].copy()
        df["Application Number"] = df["Application Number"].astype(int)
        df["Decision"] = df["Decision"].astype(str).apply(norm_dec)
        df = df[df["Decision"] != "Unknown"].copy()
        return df.reset_index(drop=True)
    except Exception as e:
        log.append(f"  Parse error: {e}"); return None

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_dublin() -> pd.DataFrame:
    decisions, seen = [], set()
    try:
        r = requests.get(DUBLIN_URL, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.content, "html.parser")
            for table in soup.find_all("table"):
                for row in table.find_all("tr"):
                    cells = [td.get_text(strip=True) for td in row.find_all(["td","th"])]
                    for i, cell in enumerate(cells):
                        n = re.sub(r"\s+","",cell)
                        if re.match(r"^\d{8}$",n) and n not in seen:
                            dec = norm_dec(cells[i+1] if i+1<len(cells) else "")
                            if dec != "Unknown":
                                seen.add(n)
                                decisions.append({"Application Number":int(n),"Decision":dec})
    except Exception: pass
    return pd.DataFrame(decisions) if decisions else pd.DataFrame(columns=["Application Number","Decision"])

# ── Community reads ────────────────────────────────────────────────────────────
@st.cache_data(ttl=180, show_spinner=False)
def get_community() -> pd.DataFrame:
    sb = _sb()
    if sb is None:
        if os.path.exists("community.json"):
            try:
                with open("community.json") as f:
                    return pd.DataFrame(json.load(f))
            except: pass
        return pd.DataFrame()
    try:
        data = sb.table("community").select("*").order("submitted_at", desc=True).execute().data
        df = pd.DataFrame(data) if data else pd.DataFrame()
        for col in ["vfs_date","emb_received","decision_date","submitted_at"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
        for col in ["working_days","calendar_days","vfs_to_emb_days"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df
    except Exception:
        return pd.DataFrame()

def get_cohort(emb_received: date, visa_type: str, embassy: str) -> dict:
    """
    Find community submissions with same/nearby embassy received date.
    Returns stats for the 'When will mine be decided?' answer.
    """
    comm = get_community()
    if len(comm) == 0 or "emb_received" not in comm.columns:
        return {}
    # Same week ±3 days
    mask = (
        (pd.to_datetime(comm["emb_received"]).dt.date >= emb_received - timedelta(days=3)) &
        (pd.to_datetime(comm["emb_received"]).dt.date <= emb_received + timedelta(days=3)) &
        (comm["visa_type"] == visa_type) &
        (comm["embassy"] == embassy)
    )
    cohort = comm[mask].dropna(subset=["working_days"])
    if len(cohort) < 2:
        # Widen to same week
        week_start = emb_received - timedelta(days=emb_received.weekday())
        mask2 = (
            (pd.to_datetime(comm["emb_received"]).dt.date >= week_start) &
            (pd.to_datetime(comm["emb_received"]).dt.date < week_start + timedelta(days=7)) &
            (comm["visa_type"] == visa_type) &
            (comm["embassy"] == embassy)
        )
        cohort = comm[mask2].dropna(subset=["working_days"])
    if len(cohort) == 0:
        # Fall back to visa_type + embassy only
        mask3 = (comm["visa_type"] == visa_type) & (comm["embassy"] == embassy)
        cohort = comm[mask3].dropna(subset=["working_days"])
    if len(cohort) == 0:
        return {}
    days = sorted(cohort["working_days"].tolist())
    decided = cohort[cohort["outcome"].isin(["Approved","Refused"])]
    pending = cohort[cohort["outcome"] == "Pending"]
    return {
        "total":       len(cohort),
        "decided":     len(decided),
        "pending":     len(pending),
        "min_days":    days[0],
        "median_days": days[len(days)//2],
        "p80_days":    days[int(len(days)*0.8)] if len(days) >= 5 else days[-1],
        "max_days":    days[-1],
        "filter_note": "same receipt date ±3 days" if len(cohort)>=2 else "all similar applications",
    }

def get_percentile(working_days_now: int, visa_type: str, embassy: str) -> dict:
    comm = get_community()
    if len(comm) == 0: return {}
    mask = (
        (comm["visa_type"] == visa_type) &
        (comm["embassy"]   == embassy)   &
        (~comm["outcome"].isin(["Pending"])) &
        comm["working_days"].notna()
    )
    similar = comm[mask]["working_days"].tolist()
    if len(similar) < 3: return {}
    days = sorted(similar)
    pct = round(sum(1 for d in days if d <= working_days_now) / len(days) * 100)
    dist = {b: sum(1 for d in days if speed_bracket(int(d))==b) for b in BRACKETS}
    return {
        "percentile":    pct,
        "total":         len(days),
        "median_days":   days[len(days)//2],
        "your_day":      working_days_now,
        "distribution":  dist,
    }

# ── Community write ────────────────────────────────────────────────────────────
def submit_community(
    irl_series: int, irl_suffix: int,
    embassy: str, visa_type: str, vfs_city: str,
    vfs_date: date, emb_received: date,
    outcome: str, decision_date: date = None,
) -> bool:
    wd  = calc_working_days(emb_received, decision_date) if decision_date else None
    cd  = (decision_date - emb_received).days            if decision_date else None
    vtd = (emb_received  - vfs_date).days                if vfs_date      else None
    entry = {
        "submitted_at":  str(date.today()),
        "irl_series":    irl_series,
        "irl_suffix":    irl_suffix,
        "embassy":       embassy,
        "visa_type":     visa_type,
        "vfs_city":      vfs_city,
        "vfs_date":      str(vfs_date)      if vfs_date      else None,
        "emb_received":  str(emb_received),
        "decision_date": str(decision_date) if decision_date else None,
        "outcome":       outcome,
        "working_days":  wd,
        "calendar_days": cd,
        "vfs_to_emb_days": vtd,
        "speed_bracket": speed_bracket(wd),
    }
    sb = _sb("service")
    if sb:
        try:
            sb.table("community").insert(entry).execute()
            get_community.clear()
            return True
        except Exception as e:
            st.error(f"DB error: {e}")
    # Fallback local JSON
    data = []
    if os.path.exists("community.json"):
        try:
            with open("community.json") as f: data = json.load(f)
        except: pass
    data.append(entry)
    with open("community.json","w") as f:
        json.dump(data, f, indent=2, default=str)
    get_community.clear()
    return True

# ── Email alert ────────────────────────────────────────────────────────────────
def register_alert(email: str, irl_series: int, irl_suffix: int, embassy: str) -> bool:
    sb = _sb("service")
    entry = {
        "email":       email,
        "irl_series":  irl_series,
        "irl_suffix":  irl_suffix,
        "embassy":     embassy,
        "registered":  str(date.today()),
        "notified":    False,
    }
    if sb:
        try:
            sb.table("alerts").upsert(entry, on_conflict="email,irl_series,irl_suffix").execute()
            return True
        except Exception as e:
            st.warning(f"Alert registration: {e}")
    return False

# ── Historical dated decisions (from your Excel, seeded to Supabase) ──────────
@st.cache_data(ttl=3600, show_spinner=False)
def load_hist() -> pd.DataFrame:
    """
    Load date-labelled decisions from Supabase ods_dates table.
    Seeded once by running seed_supabase.py with your Excel.
    Returns DataFrame with: irl_series, irl_suffix, decision, decision_date, decision_week
    Falls back to empty DataFrame if Supabase not configured.
    """
    sb = _sb()
    if sb is None:
        return pd.DataFrame(columns=["irl_series","irl_suffix","decision","decision_date","decision_week"])
    try:
        data = (sb.table("ods_dates")
                  .select("irl_series,irl_suffix,decision,decision_date,decision_week")
                  .execute().data)
        df = pd.DataFrame(data) if data else pd.DataFrame()
        if len(df) > 0:
            df["decision_date"] = pd.to_datetime(df["decision_date"]).dt.date
            df["irl_series"]    = pd.to_numeric(df["irl_series"],    errors="coerce")
            df["irl_suffix"]    = pd.to_numeric(df["irl_suffix"],    errors="coerce")
        return df
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=3600, show_spinner=False)
def get_series_timeline(series4d: int) -> pd.DataFrame:
    """
    Day-by-day decision history for a series from ods_dates.
    Used for: velocity chart, series analysis.
    Returns: decision_date, count, approved, refused, min_suffix, max_suffix
    """
    sb = _sb()
    if sb is None:
        return pd.DataFrame()
    try:
        data = (sb.table("ods_dates")
                  .select("irl_suffix,decision,decision_date,decision_week")
                  .eq("irl_series", series4d)
                  .order("decision_date")
                  .execute().data)
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data)
        df["decision_date"] = pd.to_datetime(df["decision_date"]).dt.date
        df["irl_suffix"]    = pd.to_numeric(df["irl_suffix"], errors="coerce")
        # Aggregate by date
        agg = df.groupby("decision_date").agg(
            count      = ("irl_suffix","count"),
            approved   = ("decision", lambda x:(x=="Approved").sum()),
            refused    = ("decision", lambda x:(x=="Refused").sum()),
            min_suffix = ("irl_suffix","min"),
            max_suffix = ("irl_suffix","max"),
        ).reset_index()
        return agg
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=3600, show_spinner=False)
def get_daily_velocity() -> pd.DataFrame:
    """
    Overall daily decision counts from ods_dates.
    Used for: daily velocity chart on community page.
    """
    sb = _sb()
    if sb is None:
        return pd.DataFrame()
    try:
        data = (sb.table("ods_dates")
                  .select("decision_date,decision")
                  .eq("is_baseline", False)   # exclude 16 Feb cumulative batch
                  .execute().data)
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data)
        df["decision_date"] = pd.to_datetime(df["decision_date"]).dt.date
        daily = df.groupby("decision_date").agg(
            total    = ("decision","count"),
            approved = ("decision", lambda x:(x=="Approved").sum()),
            refused  = ("decision", lambda x:(x=="Refused").sum()),
        ).reset_index()
        daily["rate_pct"] = (daily["approved"] / daily["total"] * 100).round(1)
        return daily
    except Exception:
        return pd.DataFrame()

# ── Lookup IRL in ods_dates (date-labelled DB) ────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def lookup_irl_in_db(irl_series: int, irl_suffix: int) -> dict | None:
    """
    Check ods_dates for a specific IRL.
    Returns {decision, decision_date, decision_week} or None.
    Used to show decision date alongside status.
    """
    sb = _sb()
    if sb is None: return None
    try:
        data = (sb.table("ods_dates")
                  .select("decision,decision_date,decision_week,is_baseline")
                  .eq("irl_series", irl_series)
                  .eq("irl_suffix", irl_suffix)
                  .limit(1)
                  .execute().data)
        if data:
            r = data[0]
            return {
                "decision":      r["decision"],
                "decision_date": r["decision_date"],
                "decision_week": r.get("decision_week",""),
                "is_baseline":   r.get("is_baseline", False),
            }
        return None
    except Exception:
        return None

@st.cache_data(ttl=3600, show_spinner=False)
def get_db_stats() -> dict:
    """
    Overall ods_dates stats for display.
    Returns totals, date range, last sync date.
    """
    sb = _sb()
    if sb is None: return {}
    try:
        # Total rows
        total_res = sb.table("ods_dates").select("id", count="exact").execute()
        total = total_res.count or 0

        # Latest decision date (non-baseline only)
        latest_res = (sb.table("ods_dates")
                        .select("decision_date")
                        .eq("is_baseline", False)
                        .order("decision_date", desc=True)
                        .limit(1)
                        .execute().data)
        latest = latest_res[0]["decision_date"] if latest_res else None

        # Earliest decision date
        earliest_res = (sb.table("ods_dates")
                          .select("decision_date")
                          .eq("is_baseline", False)
                          .order("decision_date", desc=False)
                          .limit(1)
                          .execute().data)
        earliest = earliest_res[0]["decision_date"] if earliest_res else None

        # Approval rate (non-baseline)
        approved_res = (sb.table("ods_dates")
                          .select("id", count="exact")
                          .eq("is_baseline", False)
                          .eq("decision", "Approved")
                          .execute())
        approved = approved_res.count or 0

        daily_total_res = (sb.table("ods_dates")
                             .select("id", count="exact")
                             .eq("is_baseline", False)
                             .execute())
        daily_total = daily_total_res.count or 0

        return {
            "total":        total,
            "daily_total":  daily_total,
            "approved":     approved,
            "rate":         round(approved / daily_total * 100, 1) if daily_total > 0 else 0,
            "latest_date":  latest,
            "earliest_date": earliest,
        }
    except Exception:
        return {}

# ── Debug / admin stats ────────────────────────────────────────────────────────
@st.cache_data(ttl=60, show_spinner=False)   # short cache so refresh works
def get_debug_stats(ods_df=None) -> dict:
    """
    Comprehensive system status for the debug panel.
    Returns a dict with all sections.
    """
    stats = {
        "supabase_anon":    False,
        "supabase_svc":     False,
        "url_masked":       "",
        "ods_dates":        {},
        "community_stats":  {},
        "alerts_stats":     {},
        "integrity":        {},
        "errors":           [],
    }

    # ── Supabase connectivity ─────────────────────────────────────────────
    try:
        url = _get_supabase_url()
        stats["url_masked"] = url[:22] + "..." + url[-12:] if len(url) > 34 else url
        anon = _sb_anon()
        if anon:
            anon.table("ods_dates").select("id").limit(1).execute()
            stats["supabase_anon"] = True
    except Exception as e:
        stats["errors"].append(f"Anon client: {e}")

    try:
        svc = _sb_svc()
        if svc:
            svc.table("community").select("id").limit(1).execute()
            stats["supabase_svc"] = True
    except Exception as e:
        stats["errors"].append(f"Service client: {e}")

    if not stats["supabase_anon"]:
        return stats   # nothing else will work without a connection

    sb = _sb_anon()

    # ── ods_dates stats ───────────────────────────────────────────────────
    try:
        total_r   = sb.table("ods_dates").select("id", count="exact").execute()
        base_r    = sb.table("ods_dates").select("id", count="exact").eq("is_baseline", True).execute()
        daily_r   = sb.table("ods_dates").select("id", count="exact").eq("is_baseline", False).execute()
        latest_r  = (sb.table("ods_dates")
                       .select("decision_date")
                       .eq("is_baseline", False)
                       .order("decision_date", desc=True)
                       .limit(1).execute().data)
        earliest_r= (sb.table("ods_dates")
                       .select("decision_date")
                       .eq("is_baseline", False)
                       .order("decision_date", desc=False)
                       .limit(1).execute().data)
        appr_r    = (sb.table("ods_dates")
                       .select("id", count="exact")
                       .eq("is_baseline", False)
                       .eq("decision", "Approved")
                       .execute())
        stats["ods_dates"] = {
            "total":        total_r.count  or 0,
            "baseline":     base_r.count   or 0,
            "daily":        daily_r.count  or 0,
            "approved":     appr_r.count   or 0,
            "latest_date":  latest_r[0]["decision_date"]   if latest_r   else None,
            "earliest_date":earliest_r[0]["decision_date"] if earliest_r else None,
        }
        d = stats["ods_dates"]
        d["approval_rate"] = round(d["approved"] / d["daily"] * 100, 1) if d["daily"] > 0 else 0
    except Exception as e:
        stats["errors"].append(f"ods_dates query: {e}")

    # ── community stats ───────────────────────────────────────────────────
    try:
        comm_total  = sb.table("community").select("id", count="exact").execute()
        comm_pend   = sb.table("community").select("id", count="exact").eq("outcome", "Pending").execute()
        comm_appr   = sb.table("community").select("id", count="exact").eq("outcome", "Approved").execute()
        comm_ref    = sb.table("community").select("id", count="exact").eq("outcome", "Refused").execute()
        # By visa type
        all_comm    = sb.table("community").select("visa_type, outcome, working_days").execute().data
        by_type = {}
        for row in all_comm:
            vt = row.get("visa_type","Other")
            if vt not in by_type: by_type[vt] = {"count":0,"decided":0,"days":[]}
            by_type[vt]["count"] += 1
            if row.get("outcome") not in ("Pending", None):
                by_type[vt]["decided"] += 1
                if row.get("working_days"): by_type[vt]["days"].append(row["working_days"])
        for vt in by_type:
            days = by_type[vt]["days"]
            by_type[vt]["median"] = sorted(days)[len(days)//2] if days else None
        stats["community_stats"] = {
            "total":   comm_total.count or 0,
            "pending": comm_pend.count  or 0,
            "approved":comm_appr.count  or 0,
            "refused": comm_ref.count   or 0,
            "by_type": by_type,
        }
    except Exception as e:
        stats["errors"].append(f"community query: {e}")

    # ── alerts stats ──────────────────────────────────────────────────────
    try:
        alerts_total  = sb.table("alerts").select("id", count="exact").execute()
        alerts_pend   = sb.table("alerts").select("id", count="exact").eq("notified", False).execute()
        alerts_done   = sb.table("alerts").select("id", count="exact").eq("notified", True).execute()
        stats["alerts_stats"] = {
            "total":     alerts_total.count or 0,
            "pending":   alerts_pend.count  or 0,
            "notified":  alerts_done.count  or 0,
        }
    except Exception as e:
        stats["errors"].append(f"alerts query: {e}")

    # ── data integrity ────────────────────────────────────────────────────
    try:
        if ods_df is not None and len(stats["ods_dates"]) > 0:
            live_count = len(ods_df)
            db_count   = stats["ods_dates"]["total"]
            gap        = live_count - db_count
            stats["integrity"] = {
                "live_ods_count": live_count,
                "db_count":       db_count,
                "gap":            gap,
                "gap_status":     "✅ In sync" if gap <= 0 else f"⚠️ {gap} rows in ODS not yet in DB",
            }
    except Exception as e:
        stats["errors"].append(f"integrity check: {e}")

    return stats
