"""
🇮🇪 Irish Visa Tracker — Starter Edition
Free, community-powered, honest.
"""

import streamlit as st
import pandas as pd
import re
from datetime import datetime, date, timedelta
import pytz

from database import (
    parse_irl, fetch_ods, fetch_dublin, get_community,
    get_cohort, get_percentile, submit_community, register_alert,
    calc_working_days, add_workdays, speed_bracket,
    BRACKETS, BRACKET_LABELS,
    load_hist, get_series_timeline, get_daily_velocity,
    lookup_irl_in_db, get_db_stats, get_connection_status,
)

# ── Config ────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="🇮🇪 Irish Visa Tracker",
    page_icon="🇮🇪",
    layout="centered",
    initial_sidebar_state="collapsed",
)
IST = pytz.timezone("Asia/Kolkata")

VISA_TYPES  = ["Study","Visit","Work","Join Family","Other"]
VFS_CITIES  = ["Chennai","Mumbai","Delhi","Bangalore","Hyderabad","Kolkata","Pune","Ahmedabad","Other"]
EMBASSIES   = ["New Delhi 🇮🇳","Dublin ISD 🇮🇪"]
PROC_RANGES = {"Study":(20,40),"Visit":(10,25),"Work":(25,50),"Join Family":(30,60),"Other":(15,45)}

# ── Update these before going live ───────────────────────────────────────────
KOFI_URL   = "https://ko-fi.com/yourname"
UPI_ID     = "yourname@upi"
WISE_AFF   = "https://wise.com/invite/u/yourref"
NIYO_AFF   = "https://goniyo.com/yourref"
INSURE_AFF = "https://www.policybazaar.com/?ref=visa"

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""<style>
.stApp { max-width: 780px; margin: 0 auto; }
h1 { font-size: 22px !important; }
h2 { font-size: 18px !important; }
h3 { font-size: 16px !important; }
.status-card {
    padding: 20px 24px; border-radius: 12px;
    text-align: center; margin: 16px 0; font-weight: 500;
}
.approved { background:var(--color-background-success);
            color:var(--color-text-success);
            border:1px solid var(--color-border-success); }
.refused  { background:var(--color-background-danger);
            color:var(--color-text-danger);
            border:1px solid var(--color-border-danger); }
.pending  { background:var(--color-background-warning);
            color:var(--color-text-warning);
            border:1px solid var(--color-border-warning); }
.insight-card {
    background:var(--color-background-secondary);
    border-radius:8px; padding:16px; margin:10px 0;
    border-left:3px solid var(--color-border-info);
}
.aff-card {
    background:var(--color-background-secondary);
    border:0.5px solid var(--color-border-tertiary);
    border-radius:8px; padding:14px; margin:6px 0;
}
div[data-testid="metric-container"] {
    background:var(--color-background-secondary);
    padding:12px; border-radius:8px;
}
</style>""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────
DEFAULTS = {
    "irl_str": "", "parsed": None,
    "embassy": "New Delhi 🇮🇳", "visa_type": "Study",
    "vfs_city": "Chennai", "vfs_date": None, "emb_date": None,
    "searched": False,
    # resolved from ODS after search
    "my_dec": None, "my_source": None, "my_dec_date": None,
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# URL param restore ─────────────────────────────────────────────────────────
p = st.query_params
if "irl" in p and not st.session_state.searched:
    parsed = parse_irl(p["irl"])
    if parsed:
        st.session_state.update({
            "irl_str":   p["irl"],
            "parsed":    parsed,
            "embassy":   p.get("office", "New Delhi 🇮🇳"),
            "visa_type": p.get("type",   "Study"),
            "vfs_city":  p.get("city",   "Chennai"),
        })
        try: st.session_state.vfs_date = date.fromisoformat(p["vfs"])
        except: pass
        try: st.session_state.emb_date = date.fromisoformat(p["emb"])
        except: pass
        st.session_state.searched = True

# ── Load live data ─────────────────────────────────────────────────────────────
with st.spinner("Loading live embassy data..."):
    ods_df, ods_date, ods_log = fetch_ods()
    dub_df                    = fetch_dublin()

nd_n  = len(ods_df)  if ods_df  is not None else 0
dub_n = len(dub_df)  if dub_df  is not None and len(dub_df) > 0 else 0

# ── Header ────────────────────────────────────────────────────────────────────
hc1, hc2 = st.columns([3, 1])
with hc1:
    st.markdown("# 🇮🇪 Irish Visa Tracker")
    file_str = ods_date.strftime("%d %b %Y") if ods_date else "unavailable"
    db_stats = get_db_stats()
    db_str = f" · DB: {db_stats["daily_total"]:,} dated decisions" if db_stats else ""
    st.caption(f"Live data: New Delhi {nd_n:,} decisions · Dublin {dub_n:,} · File: {file_str}{db_str}")
with hc2:
    if st.button("🔄 Refresh", use_container_width=True):
        fetch_ods.clear(); fetch_dublin.clear(); get_community.clear()
        st.session_state.my_dec    = None
        st.session_state.my_source = None
        st.rerun()

st.divider()

# ════════════════════════════════════════════════════════════════════════════
#  2 TABS: Track  |  Support
#  Community submission is inline in Track tab — no separate tab needed
# ════════════════════════════════════════════════════════════════════════════

def _show_community_form(up, emb_date, vfs_date, my_dec, ods_df,
                         vtype_sel, emb_sel, city_sel,
                         heading, caption):
    """
    Inline submission form that pre-fills from session state.
    Decision outcome is auto-resolved from ODS; falls back to Pending.
    """
    comm_df = get_community()
    n_comm  = len(comm_df)

    st.markdown(f"### {heading}")
    st.caption(caption)
    if n_comm > 0:
        st.caption(f"{n_comm} applicant(s) have already shared their timeline.")

    # Auto-resolve outcome from what we know
    auto_outcome = my_dec if my_dec in ("Approved","Refused") else "Pending"

    # Auto-resolve decision_date from ODS ods_dates if available
    auto_dec_date = None
    if ods_df is not None and up and my_dec in ("Approved","Refused"):
        # Use today as proxy — the actual date comes from ods_dates seed
        auto_dec_date = date.today()

    with st.form("community_form", clear_on_submit=True):
        st.markdown("**Confirm your details — pre-filled from your search**")

        cf1, cf2, cf3 = st.columns(3)
        with cf1:
            f_irl  = st.text_input(
                "Your IRL number",
                value=up["irl_str"] if up else "",
                help="Series and suffix stored — not the full number",
            )
            f_emb  = st.selectbox(
                "Embassy", EMBASSIES,
                index=EMBASSIES.index(emb_sel) if emb_sel in EMBASSIES else 0,
            )
        with cf2:
            f_type = st.selectbox(
                "Visa type", VISA_TYPES,
                index=VISA_TYPES.index(vtype_sel) if vtype_sel in VISA_TYPES else 0,
            )
            f_city = st.selectbox(
                "VFS city", VFS_CITIES,
                index=VFS_CITIES.index(city_sel) if city_sel in VFS_CITIES else 0,
            )
        with cf3:
            # Pre-fill dates from session state — not today
            f_vfs = st.date_input(
                "VFS submitted date",
                value=vfs_date,           # ← from session, not date.today()
                min_value=date(2025, 1, 1),
                max_value=date.today(),
                format="DD/MM/YYYY",
            )
            f_emb_d = st.date_input(
                "Embassy received date",
                value=emb_date,           # ← from session, not date.today()
                min_value=date(2025, 1, 1),
                max_value=date.today(),
                format="DD/MM/YYYY",
            )

        st.markdown("**Decision details**")
        fo1, fo2 = st.columns(2)
        with fo1:
            # Outcome pre-filled from ODS — user can override
            outcome_options = ["Pending","Approved","Refused"]
            f_outcome = st.selectbox(
                "Outcome",
                outcome_options,
                index=outcome_options.index(auto_outcome),
                help="Auto-filled from live embassy data if your IRL was found",
            )
        with fo2:
            # Decision date: only relevant if decided
            f_dec_d = st.date_input(
                "Decision date (if known)",
                value=auto_dec_date,
                min_value=date(2025, 1, 1),
                max_value=date.today(),
                format="DD/MM/YYYY",
                help="Approximate date your decision appeared in the embassy file",
            )

        st.caption("✅ Your full IRL is never stored — only series prefix and suffix (e.g. 8181 + 8952)")
        submitted = st.form_submit_button(
            "Submit my timeline", type="primary", use_container_width=True
        )

        if submitted:
            f_parsed = parse_irl(f_irl)
            if not f_parsed:
                st.error("Please enter a valid 8-digit IRL number")
            elif not isinstance(f_emb_d, date):
                st.error("Please enter your embassy received date")
            else:
                dec_date_val = f_dec_d if (f_outcome != "Pending" and isinstance(f_dec_d, date)) else None
                ok = submit_community(
                    irl_series=f_parsed["series4d"],
                    irl_suffix=f_parsed["suffix4"],
                    embassy=f_emb,
                    visa_type=f_type,
                    vfs_city=f_city,
                    vfs_date=f_vfs if isinstance(f_vfs, date) else None,
                    emb_received=f_emb_d,
                    outcome=f_outcome,
                    decision_date=dec_date_val,
                )
                if ok:
                    st.success("✅ Thank you! Here's what community data says about your wait:")
                    reward = get_cohort(f_emb_d, f_type, f_emb)
                    if reward and reward.get("total", 0) >= 2:
                        st.markdown(
                            f"**{reward['total']} reports** for {f_type} visa received around "
                            f"{f_emb_d.strftime('%d %b %Y')} at {f_emb.split()[0]}:\n\n"
                            f"- Earliest decision: Day **{reward['min_days']}**\n"
                            f"- Median: Day **{reward['median_days']}**\n"
                            f"- 80th percentile: Day **{reward['p80_days']}**"
                        )
                    else:
                        st.info("You're among the first for your dates — your submission helps future applicants. Check back soon.")

                    # Community stats inline
                    comm_fresh = get_community()
                    if len(comm_fresh) >= 3:
                        st.divider()
                        st.markdown("#### Community processing times")
                        decided = comm_fresh[
                            comm_fresh["outcome"].isin(["Approved","Refused"])
                        ].dropna(subset=["working_days"])
                        if len(decided) >= 3:
                            bc = decided["speed_bracket"].value_counts().reindex(BRACKETS, fill_value=0)
                            bc_df = pd.DataFrame({
                                "Bracket":      [BRACKET_LABELS.get(b, b) for b in bc.index],
                                "Applications": bc.values,
                            })
                            st.bar_chart(bc_df.set_index("Bracket")["Applications"])

                else:
                    st.error("Could not save your submission. Check Supabase connection.")

    # Daily velocity + series timeline (below form, always visible)
    st.divider()
    daily_vel = get_daily_velocity()
    if len(daily_vel) > 0:
        st.markdown("#### Daily decision velocity (your date-labelled data)")
        vel = daily_vel.set_index("decision_date")[["approved","refused"]].copy()
        vel.index = vel.index.astype(str)
        st.bar_chart(vel, color=["#1a6b3c","#c0392b"])

    if up:
        series_tl = get_series_timeline(up["series4d"])
        if len(series_tl) > 0:
            st.markdown(f"#### Series {up['series4d']} — decision timeline")
            tl = series_tl.set_index("decision_date")[["count"]].copy()
            tl.index = tl.index.astype(str)
            st.bar_chart(tl)


# ════════════════════════════════════════════════════════════════════════════
#  TAB 2: SUPPORT
# ════════════════════════════════════════════════════════════════════════════

t1, t2 = st.tabs(["🔍 Track My Application", "☕ Support"])

# ════════════════════════════════════════════════════════════════════════════
#  TAB 1: TRACK
# ════════════════════════════════════════════════════════════════════════════
with t1:

    # ── INPUT PANEL ──────────────────────────────────────────────────────────
    st.markdown("### Enter your application number")
    st.caption("8-digit IRL from your AVATS account")

    irl_in = st.text_input(
        "IRL / Application Number",
        value=st.session_state.irl_str,
        placeholder="e.g. 81818952",
        max_chars=12,
        label_visibility="collapsed",
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        emb_sel = st.selectbox(
            "Embassy", EMBASSIES,
            index=EMBASSIES.index(st.session_state.embassy)
                  if st.session_state.embassy in EMBASSIES else 0,
        )
    with c2:
        vtype_sel = st.selectbox(
            "Visa type", VISA_TYPES,
            index=VISA_TYPES.index(st.session_state.visa_type)
                  if st.session_state.visa_type in VISA_TYPES else 0,
        )
    with c3:
        city_sel = st.selectbox(
            "VFS city", VFS_CITIES,
            index=VFS_CITIES.index(st.session_state.vfs_city)
                  if st.session_state.vfs_city in VFS_CITIES else 0,
        )

    d1, d2 = st.columns(2)
    with d1:
        vfs_sel = st.date_input(
            "VFS submitted date",
            value=st.session_state.vfs_date,
            min_value=date(2025, 1, 1), max_value=date.today(),
            format="DD/MM/YYYY",
            help="Date you submitted at VFS counter",
        )
    with d2:
        emb_sel2 = st.date_input(
            "Embassy received date",
            value=st.session_state.emb_date,
            min_value=date(2025, 1, 1), max_value=date.today(),
            format="DD/MM/YYYY",
            help="Date shown in your AVATS account",
        )

    go = st.button("🔍 Check Status", type="primary", use_container_width=True)

    # ── Parse & store ──────────────────────────────────────────────────────
    clean  = re.sub(r"[^\d]", "", irl_in.lower().replace("irl", ""))
    parsed = parse_irl(clean)

    if go or (parsed and irl_in != st.session_state.irl_str):
        vfs_val = vfs_sel  if isinstance(vfs_sel,  date) else None
        emb_val = emb_sel2 if isinstance(emb_sel2, date) else None
        st.session_state.update({
            "irl_str":   irl_in,   "parsed":    parsed,
            "embassy":   emb_sel,  "visa_type": vtype_sel,
            "vfs_city":  city_sel, "vfs_date":  vfs_val,
            "emb_date":  emb_val,  "searched":  True,
            # reset resolved decision so it re-checks
            "my_dec": None, "my_source": None, "my_dec_date": None,
        })
        if parsed:
            qp = {"irl": parsed["irl_str"], "office": emb_sel,
                  "type": vtype_sel, "city": city_sel}
            if vfs_val: qp["vfs"] = str(vfs_val)
            if emb_val: qp["emb"] = str(emb_val)
            st.query_params.update(qp)

    if go and not parsed:
        st.warning("Please enter a valid 8-digit IRL number")

    if not parsed:
        st.info("Enter your IRL number above and click Check Status")
        st.stop()

    # ── Shorthand aliases ─────────────────────────────────────────────────
    up       = st.session_state.parsed
    emb_date = st.session_state.emb_date
    vfs_date = st.session_state.vfs_date

    st.divider()

    # ── Resolve decision (check ODS + Dublin) ─────────────────────────────
    if st.session_state.my_dec is None:
        my_dec, my_source, my_dec_date = None, None, None
        # Check live ODS first
        if ods_df is not None:
            r = ods_df[ods_df["Application Number"] == up["irl"]]
            if len(r) > 0:
                my_dec, my_source = r.iloc[0]["Decision"], "New Delhi ODS"
        if my_dec is None and dub_df is not None and len(dub_df) > 0:
            r = dub_df[dub_df["Application Number"] == up["irl"]]
            if len(r) > 0:
                my_dec, my_source = r.iloc[0]["Decision"], "Dublin ISD"
        # Check ods_dates DB for decision date
        db_rec = lookup_irl_in_db(up["series4d"], up["suffix4"])
        if db_rec:
            if my_dec is None: my_dec = db_rec["decision"]  # DB as fallback
            my_dec_date = db_rec["decision_date"]
        st.session_state.my_dec      = my_dec
        st.session_state.my_source   = my_source
        st.session_state.my_dec_date = my_dec_date
    else:
        my_dec_date = st.session_state.get("my_dec_date")

    my_dec    = st.session_state.my_dec
    my_source = st.session_state.my_source
    wd        = calc_working_days(emb_date) if emb_date else None

    # ══════════════════════════════════════════════════════════════════════
    #  APPROVED
    # ══════════════════════════════════════════════════════════════════════
    if my_dec == "Approved":
        st.balloons()
        st.markdown(f"""
<div class="status-card approved">
<div style="font-size:32px;margin-bottom:8px">🎉</div>
<div style="font-size:20px">Visa Approved</div>
<div style="font-size:14px;margin-top:6px;opacity:0.85">
IRL {up["irl_str"]} · Source: {my_source}{(" · Decided: " + str(my_dec_date)) if my_dec_date else ""}
</div></div>""", unsafe_allow_html=True)

        st.markdown("### What happens next")
        for icon, title, detail in [
            ("📦","VFS passport dispatch",
             "VFS will courier your passport with the visa sticker. Allow 5–7 working days. You'll get an SMS tracking number."),
            ("📄","Your eICR document",
             "Carry the eICR you received at VFS — mandatory at Dublin Airport immigration, not optional."),
            ("✈️","Booking your flight",
             "Book only after passport arrives. Check: validity start date, validity end date, entry type (single/multiple)."),
            ("🏠","First week in Ireland",
             "Book at least your first week's accommodation before flying. Options: studentaccommodation.ie, daft.ie, college Facebook groups."),
            ("🏛️","GNIB / IRP registration",
             "Within 90 days of arrival, register at Burgh Quay, Dublin 2. Bring: passport, eICR, college letter, proof of address, €300 fee."),
        ]:
            with st.expander(f"{icon} {title}"): st.write(detail)

        st.divider()
        st.markdown("### Useful services for your move")
        st.caption("Services other Irish-bound students use. Links may be affiliate — disclosed.")
        a1, a2, a3 = st.columns(3)
        with a1:
            st.markdown(f'<div class="aff-card"><div style="font-weight:500;font-size:13px">Wise card</div>'
                        f'<div style="font-size:12px;color:var(--color-text-secondary);margin:4px 0">Best forex rates. No hidden fees.</div>'
                        f'<a href="{WISE_AFF}" target="_blank" style="font-size:12px">Open account →</a></div>',
                        unsafe_allow_html=True)
        with a2:
            st.markdown(f'<div class="aff-card"><div style="font-weight:500;font-size:13px">Niyo Global</div>'
                        f'<div style="font-size:12px;color:var(--color-text-secondary);margin:4px 0">Zero forex markup at all ATMs.</div>'
                        f'<a href="{NIYO_AFF}" target="_blank" style="font-size:12px">Get card →</a></div>',
                        unsafe_allow_html=True)
        with a3:
            st.markdown(f'<div class="aff-card"><div style="font-weight:500;font-size:13px">Travel insurance</div>'
                        f'<div style="font-size:12px;color:var(--color-text-secondary);margin:4px 0">Required for student visa.</div>'
                        f'<a href="{INSURE_AFF}" target="_blank" style="font-size:12px">Compare →</a></div>',
                        unsafe_allow_html=True)

        # ── Inline community submission (approved) ────────────────────────
        st.divider()
        _show_community_form(
            up, emb_date, vfs_date, my_dec, ods_df,
            vtype_sel, emb_sel, city_sel,
            heading="Help others — share your timeline",
            caption="You know your exact dates. Sharing them anonymously helps applicants still waiting predict their own decision.",
        )

    # ══════════════════════════════════════════════════════════════════════
    #  REFUSED
    # ══════════════════════════════════════════════════════════════════════
    elif my_dec == "Refused":
        st.markdown(f"""
<div class="status-card refused">
<div style="font-size:22px;margin-bottom:8px">Application Refused</div>
<div style="font-size:14px;opacity:0.85">IRL {up["irl_str"]} · Source: {my_source}</div>
</div>""", unsafe_allow_html=True)
        st.markdown("""
### Your options
**Appeal (free, within 2 months)**
Email **newdelhivisa@dfa.ie** quoting your IRL. Attach any additional evidence.

**Re-apply**
You can re-apply immediately with stronger documentation. Refusal is not a permanent bar.

**Get the refusal reason**
If no reason was given, request it in your appeal email.
""")

    # ══════════════════════════════════════════════════════════════════════
    #  PENDING
    # ══════════════════════════════════════════════════════════════════════
    else:
        typ     = PROC_RANGES.get(st.session_state.visa_type, (20, 40))
        wd_str  = f" · Day {wd}" if wd else ""
        exp_str = (f" · Expected: {add_workdays(emb_date, typ[0]).strftime('%d %b')}"
                   f"–{add_workdays(emb_date, typ[1]).strftime('%d %b %Y')}") if emb_date else ""

        st.markdown(f"""
<div class="status-card pending">
<div style="font-size:22px;margin-bottom:8px">⏳ Application Pending</div>
<div style="font-size:14px;opacity:0.9">IRL {up["irl_str"]}{wd_str}{exp_str}</div>
</div>""", unsafe_allow_html=True)

        if emb_date:
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("Working days",  f"Day {wd}")
            mc2.metric("Visa type",     st.session_state.visa_type)
            mc3.metric("Embassy",       st.session_state.embassy.split()[0])

        st.divider()

        # Is my wait normal?
        if wd and emb_date:
            pct_data = get_percentile(wd, st.session_state.visa_type, st.session_state.embassy)
            if pct_data:
                pct    = pct_data["percentile"]
                total  = pct_data["total"]
                median = pct_data["median_days"]
                color  = ("var(--color-text-success)" if pct <= 40
                          else "var(--color-text-warning)" if pct <= 70
                          else "var(--color-text-danger)")
                note   = ("Your wait is on the shorter side — good sign." if pct <= 40
                          else "Your wait is completely normal." if pct <= 70
                          else "Your wait is longer than average — consider contacting the embassy.")
                st.markdown(f"""
<div class="insight-card">
<div style="font-size:13px;color:var(--color-text-secondary);margin-bottom:4px">Is my wait normal?</div>
<div style="font-size:24px;font-weight:500;color:{color}">{pct}% decided by Day {wd}</div>
<div style="font-size:13px;color:var(--color-text-secondary);margin-top:4px">
Among {total} similar {st.session_state.visa_type} visa applicants · median: Day {median}
</div>
<div style="font-size:13px;margin-top:8px">{note}</div>
</div>""", unsafe_allow_html=True)
            else:
                st.info("No community data yet for your visa type. Submit your dates below to help build this.")

        # When will mine be decided?
        if emb_date:
            cohort = get_cohort(emb_date, st.session_state.visa_type, st.session_state.embassy)
            if cohort and cohort.get("total", 0) >= 2:
                med_date = add_workdays(emb_date, cohort["median_days"])
                p80_date = add_workdays(emb_date, cohort["p80_days"])
                st.markdown(f"""
<div class="insight-card">
<div style="font-size:13px;color:var(--color-text-secondary);margin-bottom:4px">When will mine be decided?</div>
<div style="font-size:20px;font-weight:500">~{med_date.strftime('%d %b %Y')} <span style="font-size:14px;font-weight:400">(median)</span></div>
<div style="font-size:13px;color:var(--color-text-secondary);margin-top:6px">
80% decided by {p80_date.strftime('%d %b %Y')} · Range Day {cohort['min_days']}–{cohort['max_days']} · {cohort['total']} reports ({cohort['filter_note']})
</div>
</div>""", unsafe_allow_html=True)
            else:
                st.markdown(f"""
<div class="insight-card">
<div style="font-size:13px;color:var(--color-text-secondary);margin-bottom:4px">Typical processing window</div>
<div style="font-size:18px;font-weight:500">{add_workdays(emb_date, typ[0]).strftime('%d %b')} – {add_workdays(emb_date, typ[1]).strftime('%d %b %Y')}</div>
<div style="font-size:13px;color:var(--color-text-secondary);margin-top:4px">
Days {typ[0]}–{typ[1]} from your embassy received date
</div>
</div>""", unsafe_allow_html=True)

        st.divider()

        # Nearest decided
        if ods_df is not None:
            st.markdown("### Nearest decided numbers")
            tmp = ods_df.copy()
            tmp["Diff"] = (tmp["Application Number"] - up["irl"]).abs()
            nr = tmp.nsmallest(5, "Diff")[["Application Number", "Decision", "Diff"]].copy()
            nr["Decision"] = nr["Decision"].map({"Approved":"✅ Approved","Refused":"❌ Refused"}).fillna(nr["Decision"])
            st.dataframe(nr, use_container_width=True, hide_index=True)

            bl = ods_df[ods_df["Application Number"] < up["irl"]]["Application Number"].max() \
                 if (ods_df["Application Number"] < up["irl"]).any() else None
            ab = ods_df[ods_df["Application Number"] > up["irl"]]["Application Number"].min() \
                 if (ods_df["Application Number"] > up["irl"]).any() else None
            if bl and ab:
                g1, g2 = st.columns(2)
                g1.info(f"Closest below: **{bl}**\nGap: {up['irl'] - bl} numbers")
                g2.info(f"Closest above: **{ab}**\nGap: {ab - up['irl']} numbers")
            st.caption("Processing is non-sequential (batched by VFS date). Numeric proximity is less reliable than your embassy received date.")

        st.divider()

        # Email alert
        st.markdown("### Get notified when your decision appears")
        st.caption("We check the embassy file daily and email you the moment your IRL appears. Free.")
        with st.form("alert_form"):
            alert_email = st.text_input("Your email address", placeholder="name@email.com")
            alert_go    = st.form_submit_button("Notify me", type="primary", use_container_width=True)
            if alert_go:
                if "@" in alert_email and "." in alert_email:
                    ok = register_alert(
                        email=alert_email,
                        irl_series=up["series4d"],
                        irl_suffix=up["suffix4"],
                        embassy=st.session_state.embassy,
                    )
                    if ok:
                        st.success(f"✅ Registered! We'll email {alert_email} when IRL {up['irl_str']} appears.")
                    else:
                        st.info("Saved locally. Connect Supabase to enable cloud notifications.")
                else:
                    st.error("Please enter a valid email address")

        st.divider()

        # ── Inline community submission (pending) ─────────────────────────
        _show_community_form(
            up, emb_date, vfs_date, my_dec, ods_df,
            vtype_sel, emb_sel, city_sel,
            heading="Share your dates — get better predictions",
            caption="Your dates help us give more accurate 'when?' estimates. Takes 30 seconds. Anonymous.",
        )

    # ── Shareable link ────────────────────────────────────────────────────
    st.divider()
    share = f"?irl={up['irl_str']}&office={st.session_state.embassy}&type={st.session_state.visa_type}"
    if isinstance(vfs_sel,  date): share += f"&vfs={vfs_sel}"
    if isinstance(emb_sel2, date): share += f"&emb={emb_sel2}"
    st.caption(f"🔗 Bookmark or share: `{share}`")


# ── Community form helper (shared by APPROVED and PENDING flows) ──────────────
with t2:
    st.markdown("### Support this tool")
    st.markdown(
        "This tracker is free for every applicant — now and always. "
        "The status check, community comparisons, and email alerts will never be gated behind a paywall.\n\n"
        "If it reduced your anxiety or saved you time, a small tip keeps the lights on."
    )

    s1, s2 = st.columns(2)
    with s1:
        st.markdown(f"""
<div style="background:var(--color-background-secondary);border-radius:8px;padding:20px;text-align:center">
<div style="font-size:20px;margin-bottom:8px">☕</div>
<div style="font-weight:500;margin-bottom:6px">Buy us a chai</div>
<div style="font-size:13px;color:var(--color-text-secondary);margin-bottom:12px">
One-time tip via Ko-fi. Any amount. 0% fees.
</div>
<a href="{KOFI_URL}" target="_blank"
   style="display:block;padding:10px;background:#FF5E5B;color:white;
          border-radius:6px;text-decoration:none;font-weight:500;font-size:14px">
Support on Ko-fi →
</a></div>""", unsafe_allow_html=True)

    with s2:
        st.markdown(f"""
<div style="background:var(--color-background-secondary);border-radius:8px;padding:20px;text-align:center">
<div style="font-size:20px;margin-bottom:8px">📲</div>
<div style="font-weight:500;margin-bottom:6px">UPI (India)</div>
<div style="font-size:13px;color:var(--color-text-secondary);margin-bottom:12px">
Instant, no signup needed.<br>UPI ID: <strong>{UPI_ID}</strong>
</div>
<div style="font-size:12px;background:var(--color-background-primary);border-radius:6px;
            padding:10px;border:0.5px solid var(--color-border-tertiary)">
Search UPI ID above in any UPI app
</div></div>""", unsafe_allow_html=True)

    st.divider()
    st.markdown("### What your support pays for")
    for service, cost, note in [
        ("Streamlit Cloud hosting",  "₹0/month",     "Free forever for public apps"),
        ("Supabase database",        "₹0/month",     "Free tier — 500MB, enough for years"),
        ("Email alerts (Resend)",    "₹0→₹1,660",   "Free up to 3,000 emails/month"),
        ("Domain (optional)",        "₹66/month",    "Optional — app works without it"),
        ("Developer time",           "Your support", "Keeping it running, adding features"),
    ]:
        r1, r2, r3 = st.columns([3, 1.5, 3])
        r1.write(service); r2.write(f"**{cost}**"); r3.write(note)

    st.divider()
    st.markdown("### Coming soon — Ireland Arrival Guide")
    st.markdown(
        "Comprehensive guide for Indian students arriving in Ireland: "
        "GNIB registration, bank account, PPS number, SIM cards, student transport, "
        "Dublin neighbourhoods by budget, student discounts, and more.\n\n"
        "**₹199 one-time · launching soon**"
    )
    if st.button("Notify me when the guide is ready", use_container_width=True):
        st.info("Enter your email in the Track tab's alert form — we'll use that to notify you.")

    st.divider()
    # ── Connection diagnostic ─────────────────────────────────────────────
    with st.expander("🔧 Connection status (for setup verification)"):
        conn = get_connection_status()
        if conn["ok"]:
            st.success("✅ Supabase connected successfully")
        else:
            st.error(f"❌ Supabase not connected: {conn['error']}")
            st.markdown("""
**How to fix:**

Go to your Streamlit Cloud app → **⋮ (three dots)** → **Settings** → **Secrets**

Make sure your secrets look EXACTLY like this (copy and paste):
```toml
[supabase]
url         = "https://YOUR-PROJECT-REF.supabase.co"
anon_key    = "eyJhbGc..."
service_key = "eyJhbGc..."
```

Common mistakes:
- `url` named as `SUPABASE_URL` → wrong, must be `url`
- `anon_key` named as `anon` or `ANON_KEY` → wrong, must be `anon_key`  
- `service_key` named as `service_role` → wrong, must be `service_key`
- Missing `[supabase]` section header
- Trailing slash on the URL: `https://xxx.supabase.co/` → remove the `/`
""")
        st.markdown(f"""
| Check | Status |
|---|---|
| `[supabase]` section exists | {"✅" if "supabase" in (st.secrets if hasattr(st, "secrets") else {}) else "❌"} |
| `url` key set | {"✅" if conn["url_set"] else "❌"} |
| `anon_key` set | {"✅" if conn["anon_set"] else "❌"} |
| `service_key` set | {"✅" if conn["service_set"] else "❌"} |
| URL value | `{conn["url_value"] or "empty"}` |
""")

    st.caption("Independent tool. Not affiliated with the Irish Embassy, ISD, or any immigration authority.")
