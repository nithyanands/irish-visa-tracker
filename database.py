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

# ── Supabase client ───────────────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def _sb(role: str = "anon"):
    try:
        from supabase import create_client
        key = st.secrets["supabase"]["service_key" if role=="service" else "anon_key"]
        return create_client(st.secrets["supabase"]["url"], key)
    except Exception:
        return None

def _sb_ok() -> bool:
    return _sb() is not None

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
