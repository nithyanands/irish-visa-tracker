"""
🇮🇪 Irish Visa Tracker — Starter Edition
Free, community-powered, honest.

Stack: Streamlit Cloud + Supabase (free tiers)
Revenue: Ko-fi tips + UPI donations + ethical affiliates post-decision
"""

import streamlit as st
import pandas as pd
import re
from datetime import datetime, date, timedelta
import pytz

from database import (
    parse_irl, fetch_ods, fetch_dublin, get_community,
    get_cohort, get_percentile, submit_community, register_alert,
    calc_working_days, add_workdays, speed_bracket, is_workday,
    prev_workday, BRACKETS, BRACKET_LABELS,
)

# ── Config ────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="🇮🇪 Irish Visa Tracker",
    page_icon="🇮🇪",
    layout="centered",          # centred — better mobile experience
    initial_sidebar_state="collapsed",
)
IST = pytz.timezone("Asia/Kolkata")

VISA_TYPES    = ["Study","Visit","Work","Join Family","Other"]
VFS_CITIES    = ["Chennai","Mumbai","Delhi","Bangalore","Hyderabad","Kolkata","Pune","Ahmedabad","Other"]
EMBASSIES     = ["New Delhi 🇮🇳","Dublin ISD 🇮🇪"]
PROC_RANGES   = {"Study":(20,40),"Visit":(10,25),"Work":(25,50),"Join Family":(30,60),"Other":(15,45)}

# ── KOFI / UPI — update these with your actual links ─────────────────────────
KOFI_URL      = "https://ko-fi.com/yourname"          # ← update
UPI_ID        = "yourname@upi"                         # ← update
WISE_AFF      = "https://wise.com/invite/u/yourref"    # ← update with affiliate link
NIYO_AFF      = "https://goniyo.com/yourref"           # ← update with affiliate link
INSURE_AFF    = "https://www.policybazaar.com/?ref=visa" # ← update

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.stApp { max-width: 760px; margin: 0 auto; }
h1 { font-size: 22px !important; }
h2 { font-size: 18px !important; }
h3 { font-size: 16px !important; }
.status-card {
    padding: 20px 24px; border-radius: 12px;
    text-align: center; margin: 16px 0; font-weight: 500;
}
.approved { background: var(--color-background-success);
            color: var(--color-text-success);
            border: 1px solid var(--color-border-success); }
.refused  { background: var(--color-background-danger);
            color: var(--color-text-danger);
            border: 1px solid var(--color-border-danger); }
.pending  { background: var(--color-background-warning);
            color: var(--color-text-warning);
            border: 1px solid var(--color-border-warning); }
.insight-card {
    background: var(--color-background-secondary);
    border-radius: 8px; padding: 16px; margin: 8px 0;
    border-left: 3px solid var(--color-border-info);
}
.affiliate-card {
    background: var(--color-background-secondary);
    border: 0.5px solid var(--color-border-tertiary);
    border-radius: 8px; padding: 14px; margin: 8px 0;
}
.support-btn {
    display: inline-block; padding: 10px 20px;
    border-radius: 8px; text-decoration: none;
    font-weight: 500; font-size: 14px; margin: 4px;
}
.kofi  { background: #FF5E5B; color: white; }
.divider { border: none; border-top: 0.5px solid var(--color-border-tertiary); margin: 20px 0; }
div[data-testid="metric-container"] {
    background: var(--color-background-secondary);
    padding: 12px; border-radius: 8px;
}
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────
for k, v in {
    "irl_str":"","parsed":None,"embassy":"New Delhi 🇮🇳",
    "visa_type":"Study","vfs_city":"Chennai",
    "vfs_date":None,"emb_date":None,"searched":False,
}.items():
    if k not in st.session_state: st.session_state[k] = v

# URL param restore
p = st.query_params
if "irl" in p and not st.session_state.searched:
    parsed = parse_irl(p["irl"])
    if parsed:
        st.session_state.update({
            "irl_str": p["irl"], "parsed": parsed,
            "embassy": p.get("office","New Delhi 🇮🇳"),
            "visa_type": p.get("type","Study"),
            "vfs_city": p.get("city","Chennai"),
        })
        try: st.session_state.vfs_date = date.fromisoformat(p["vfs"])
        except: pass
        try: st.session_state.emb_date = date.fromisoformat(p["emb"])
        except: pass
        st.session_state.searched = True

# ── Load data ─────────────────────────────────────────────────────────────────
with st.spinner("Loading live embassy data..."):
    ods_df, ods_date, ods_log = fetch_ods()
    dub_df                    = fetch_dublin()

nd_n  = len(ods_df)  if ods_df  is not None else 0
dub_n = len(dub_df)  if dub_df  is not None and len(dub_df)>0 else 0

# ── Header ────────────────────────────────────────────────────────────────────
col_h1, col_h2 = st.columns([3,1])
with col_h1:
    st.markdown("# 🇮🇪 Irish Visa Tracker")
    file_str = ods_date.strftime("%d %b %Y") if ods_date else "unavailable"
    st.caption(f"Live data: New Delhi {nd_n:,} decisions · Dublin {dub_n:,} · File: {file_str}")
with col_h2:
    if st.button("🔄 Refresh", use_container_width=True):
        fetch_ods.clear(); fetch_dublin.clear(); get_community.clear(); st.rerun()

st.divider()

# ════════════════════════════════════════════════════════════════════════════
#  TABS
# ════════════════════════════════════════════════════════════════════════════
t1, t2, t3 = st.tabs(["🔍 Track My Application", "👥 Community", "☕ Support"])

# ════════════════════════════════════════════════════════════════════════════
#  TAB 1: TRACK
# ════════════════════════════════════════════════════════════════════════════
with t1:

    # ── IRL INPUT ────────────────────────────────────────────────────────────
    st.markdown("### Enter your application number")
    st.caption("8-digit IRL from your AVATS account — e.g. 81818952")

    irl_in = st.text_input(
        "IRL / Application Number",
        value=st.session_state.irl_str,
        placeholder="Enter 8-digit IRL number",
        max_chars=12,
        label_visibility="collapsed",
    )

    c1, c2, c3 = st.columns(3)
    with c1: emb_in   = st.selectbox("Embassy",   EMBASSIES,    index=EMBASSIES.index(st.session_state.embassy) if st.session_state.embassy in EMBASSIES else 0, label_visibility="visible")
    with c2: vtype_in = st.selectbox("Visa type",  VISA_TYPES,   index=VISA_TYPES.index(st.session_state.visa_type) if st.session_state.visa_type in VISA_TYPES else 0)
    with c3: city_in  = st.selectbox("VFS city",   VFS_CITIES,   index=VFS_CITIES.index(st.session_state.vfs_city) if st.session_state.vfs_city in VFS_CITIES else 0)

    d1, d2 = st.columns(2)
    with d1: vfs_in  = st.date_input("VFS submitted date",  value=st.session_state.vfs_date,  min_value=date(2025,1,1), max_value=date.today(), format="DD/MM/YYYY", help="Date you submitted at VFS counter")
    with d2: emb_in2 = st.date_input("Embassy received date", value=st.session_state.emb_date, min_value=date(2025,1,1), max_value=date.today(), format="DD/MM/YYYY", help="Date in your AVATS account")

    go = st.button("🔍 Check Status", type="primary", use_container_width=True)

    # Process input
    clean = re.sub(r"[^\d]", "", irl_in.lower().replace("irl",""))
    parsed = parse_irl(clean)

    if go or (parsed and irl_in != st.session_state.irl_str):
        st.session_state.update({
            "irl_str": irl_in, "parsed": parsed,
            "embassy": emb_in, "visa_type": vtype_in, "vfs_city": city_in,
            "vfs_date": vfs_in if isinstance(vfs_in, date) else None,
            "emb_date": emb_in2 if isinstance(emb_in2, date) else None,
            "searched": True,
        })
        if parsed:
            qp = {"irl": parsed["irl_str"], "office": emb_in, "type": vtype_in, "city": city_in}
            if isinstance(vfs_in,  date): qp["vfs"] = str(vfs_in)
            if isinstance(emb_in2, date): qp["emb"] = str(emb_in2)
            st.query_params.update(qp)

    up       = st.session_state.parsed
    emb_date = st.session_state.emb_date
    vfs_date = st.session_state.vfs_date

    if go and not parsed:
        st.warning("Please enter a valid 8-digit IRL number")

    if not up and not go:
        st.info("Enter your IRL number above and click Check Status")

    # ── RESULT ───────────────────────────────────────────────────────────────
    if up:
        st.divider()

        # Check decision
        my_dec, my_source = None, None
        if ods_df is not None:
            r = ods_df[ods_df["Application Number"] == up["irl"]]
            if len(r) > 0: my_dec, my_source = r.iloc[0]["Decision"], "New Delhi ODS"
        if my_dec is None and len(dub_df) > 0:
            r = dub_df[dub_df["Application Number"] == up["irl"]]
            if len(r) > 0: my_dec, my_source = r.iloc[0]["Decision"], "Dublin ISD"

        wd = calc_working_days(emb_date) if emb_date else None

        # ── APPROVED ─────────────────────────────────────────────────────────
        if my_dec == "Approved":
            st.balloons()
            st.markdown(f"""
<div class="status-card approved">
<div style="font-size:32px;margin-bottom:8px">🎉</div>
<div style="font-size:20px">Visa Approved</div>
<div style="font-size:14px;margin-top:6px;opacity:0.85">
IRL {up["irl_str"]} · Source: {my_source}
</div>
</div>""", unsafe_allow_html=True)

            st.markdown("### What happens next")
            steps = [
                ("📦","VFS passport dispatch","VFS Chennai will courier your passport with the visa sticker. Allow 5–7 working days from today. You'll receive an SMS with a tracking number."),
                ("📄","Your eICR document","Carry the eICR (Embassy Immigration Clearance Record) you received at VFS. This is mandatory at Dublin Airport immigration — not optional."),
                ("✈️","Booking your flight","Book only after your passport arrives and you've verified the sticker dates. Check: validity start date, validity end date, entry type (single/multiple)."),
                ("🏠","First week in Ireland","Book at least your first week's accommodation before flying. Dublin short-term options: studentaccommodation.ie, daft.ie, Facebook groups for your college."),
                ("🏛️","GNIB / IRP registration","Within 90 days of arrival, register at Burgh Quay (Dublin) or your local Garda station. Bring: passport, eICR, college letter, proof of address, €300 fee."),
            ]
            for icon, title, detail in steps:
                with st.expander(f"{icon} {title}"):
                    st.write(detail)

            st.divider()
            st.markdown("### Useful services for your move")
            st.caption("These are services other Irish students have found genuinely useful. Links may be affiliate — disclosed.")

            a1, a2, a3 = st.columns(3)
            with a1:
                st.markdown(f"""<div class="affiliate-card">
<div style="font-size:13px;font-weight:500">Wise card</div>
<div style="font-size:12px;color:var(--color-text-secondary);margin:4px 0">Best forex rates for India→Ireland transfers. No hidden fees.</div>
<a href="{WISE_AFF}" target="_blank" style="font-size:12px">Open account →</a>
</div>""", unsafe_allow_html=True)
            with a2:
                st.markdown(f"""<div class="affiliate-card">
<div style="font-size:13px;font-weight:500">Niyo Global card</div>
<div style="font-size:12px;color:var(--color-text-secondary);margin:4px 0">Zero forex markup. Works at all ATMs in Ireland.</div>
<a href="{NIYO_AFF}" target="_blank" style="font-size:12px">Get card →</a>
</div>""", unsafe_allow_html=True)
            with a3:
                st.markdown(f"""<div class="affiliate-card">
<div style="font-size:13px;font-weight:500">Travel insurance</div>
<div style="font-size:12px;color:var(--color-text-secondary);margin:4px 0">Required for Ireland student visa. Compare plans.</div>
<a href="{INSURE_AFF}" target="_blank" style="font-size:12px">Compare →</a>
</div>""", unsafe_allow_html=True)

            st.divider()
            st.markdown("### Help others who are still waiting")
            st.info("You know your exact dates. Sharing them (anonymously) helps other applicants predict their own decision date. Takes 30 seconds.")
            if st.button("➕ Share my timeline in Community", use_container_width=True):
                st.session_state["jump_to_community"] = True
                st.rerun()

        # ── REFUSED ──────────────────────────────────────────────────────────
        elif my_dec == "Refused":
            st.markdown(f"""
<div class="status-card refused">
<div style="font-size:22px;margin-bottom:8px">Application Refused</div>
<div style="font-size:14px;opacity:0.85">IRL {up["irl_str"]} · Source: {my_source}</div>
</div>""", unsafe_allow_html=True)
            st.markdown("### Your options")
            st.markdown("""
**Appeal (free, within 2 months):**
Email **newdelhivisa@dfa.ie** quoting your IRL number.
Subject: "Appeal — Application {IRL} — Visa Refused"
Attach: any additional evidence addressing the refusal reason.

**Re-apply:**
You can re-apply immediately with stronger documentation.
A refusal does not permanently bar you from applying again.

**Get the refusal reason:**
The embassy must provide a reason. If none was given, request it in your appeal email.
""".replace("{IRL}", up["irl_str"]))

        # ── PENDING ──────────────────────────────────────────────────────────
        else:
            # Status card
            wd_str  = f" · Day {wd}" if wd else ""
            typ     = PROC_RANGES.get(st.session_state.visa_type,(20,40))
            exp_str = f" · Expected: {add_workdays(emb_date,typ[0]).strftime('%d %b')}–{add_workdays(emb_date,typ[1]).strftime('%d %b %Y')}" if emb_date else ""

            st.markdown(f"""
<div class="status-card pending">
<div style="font-size:22px;margin-bottom:8px">⏳ Application Pending</div>
<div style="font-size:14px;opacity:0.9">IRL {up["irl_str"]}{wd_str}{exp_str}</div>
</div>""", unsafe_allow_html=True)

            # Key metrics
            if emb_date:
                mc1, mc2, mc3 = st.columns(3)
                mc1.metric("Working days", f"Day {wd}")
                mc2.metric("Visa type",    st.session_state.visa_type)
                mc3.metric("Embassy",      st.session_state.embassy.split()[0])

            st.divider()

            # ── IS MY WAIT NORMAL? ────────────────────────────────────────────
            if wd and emb_date:
                pct_data = get_percentile(wd, st.session_state.visa_type, st.session_state.embassy)
                if pct_data:
                    pct = pct_data["percentile"]
                    total = pct_data["total"]
                    median = pct_data["median_days"]
                    if pct <= 40:
                        note = "Your wait is on the shorter side — good sign."
                        color = "var(--color-text-success)"
                    elif pct <= 70:
                        note = "Your wait is completely normal."
                        color = "var(--color-text-warning)"
                    else:
                        note = "Your wait is longer than average — consider contacting the embassy soon."
                        color = "var(--color-text-danger)"

                    st.markdown(f"""
<div class="insight-card">
<div style="font-size:13px;color:var(--color-text-secondary);margin-bottom:6px">Is my wait normal?</div>
<div style="font-size:22px;font-weight:500;color:{color}">{pct}%</div>
<div style="font-size:13px;color:var(--color-text-secondary);margin-top:4px">
of similar {st.session_state.visa_type} visa applicants were decided by Day {wd}
(based on {total} community reports · median: Day {median})
</div>
<div style="font-size:13px;margin-top:8px">{note}</div>
</div>""", unsafe_allow_html=True)

                    # Bracket bar
                    dist = pct_data.get("distribution",{})
                    if dist and sum(dist.values()) > 0:
                        bar_df = pd.DataFrame({
                            "Bracket": [BRACKET_LABELS[b] for b in BRACKETS if b in dist],
                            "Count":   [dist.get(b,0) for b in BRACKETS if b in dist],
                        })
                        st.bar_chart(bar_df.set_index("Bracket")["Count"], height=150)
                else:
                    st.info("No community data yet for your visa type. Be the first to submit your dates in the Community tab!")

            st.divider()

            # ── WHEN WILL MINE BE DECIDED? ────────────────────────────────────
            if emb_date:
                cohort = get_cohort(emb_date, st.session_state.visa_type, st.session_state.embassy)
                if cohort:
                    median_date = add_workdays(emb_date, cohort["median_days"])
                    p80_date    = add_workdays(emb_date, cohort["p80_days"])
                    st.markdown(f"""
<div class="insight-card">
<div style="font-size:13px;color:var(--color-text-secondary);margin-bottom:6px">When will mine be decided?</div>
<div style="font-size:20px;font-weight:500">
~{median_date.strftime('%d %b %Y')} <span style="font-size:14px;font-weight:400">(median)</span>
</div>
<div style="font-size:13px;color:var(--color-text-secondary);margin-top:6px">
80% of similar applications decided by {p80_date.strftime('%d %b %Y')} ·
Range: Day {cohort["min_days"]}–{cohort["max_days"]} ·
Based on {cohort["total"]} reports ({cohort["filter_note"]})
</div>
</div>""", unsafe_allow_html=True)
                else:
                    # Fallback: typical range
                    typ = PROC_RANGES.get(st.session_state.visa_type,(20,40))
                    early = add_workdays(emb_date, typ[0])
                    late  = add_workdays(emb_date, typ[1])
                    st.markdown(f"""
<div class="insight-card">
<div style="font-size:13px;color:var(--color-text-secondary);margin-bottom:6px">Typical processing window</div>
<div style="font-size:18px;font-weight:500">{early.strftime('%d %b')} – {late.strftime('%d %b %Y')}</div>
<div style="font-size:13px;color:var(--color-text-secondary);margin-top:4px">
Days {typ[0]}–{typ[1]} from your embassy received date ·
<strong>Submit your dates in the Community tab</strong> to get a more precise prediction.
</div>
</div>""", unsafe_allow_html=True)

            st.divider()

            # ── NEAREST DECIDED ───────────────────────────────────────────────
            if ods_df is not None:
                st.markdown("### Nearest decided numbers (from live ODS)")
                tmp = ods_df.copy()
                tmp["Diff"] = (tmp["Application Number"] - up["irl"]).abs()
                nr  = tmp.nsmallest(5,"Diff")[["Application Number","Decision","Diff"]]
                nr["Decision"] = nr["Decision"].map({"Approved":"✅ Approved","Refused":"❌ Refused"}).fillna(nr["Decision"])
                st.dataframe(nr, use_container_width=True, hide_index=True)

                bl = ods_df[ods_df["Application Number"] < up["irl"]]["Application Number"].max() if len(ods_df[ods_df["Application Number"]<up["irl"]])>0 else None
                ab = ods_df[ods_df["Application Number"] > up["irl"]]["Application Number"].min() if len(ods_df[ods_df["Application Number"]>up["irl"]])>0 else None
                if bl and ab:
                    g1, g2 = st.columns(2)
                    g1.info(f"Closest below: **{bl}**\nGap: {up['irl']-bl} numbers")
                    g2.info(f"Closest above: **{ab}**\nGap: {ab-up['irl']} numbers")
                st.caption("Note: Processing is non-sequential (batched by VFS submission date). Numeric proximity is less predictive than your embassy received date.")

            st.divider()

            # ── EMAIL ALERT ───────────────────────────────────────────────────
            st.markdown("### Get notified when your decision appears")
            st.caption("We check the embassy file daily and email you the moment your IRL number is found. Free.")
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
                            st.success(f"✅ Registered! We'll email {alert_email} when IRL {up['irl_str']} appears in the decision file.")
                        else:
                            st.info("Registration saved locally. Set up Supabase to enable cloud notifications.")
                    else:
                        st.error("Please enter a valid email address")

        # ── SHAREABLE LINK ────────────────────────────────────────────────────
        st.divider()
        share = f"?irl={up['irl_str']}&office={st.session_state.embassy}&type={st.session_state.visa_type}"
        if isinstance(vfs_in, date):  share += f"&vfs={vfs_in}"
        if isinstance(emb_in2, date): share += f"&emb={emb_in2}"
        st.caption(f"🔗 Bookmark or share your tracker: `{share}`")


# ════════════════════════════════════════════════════════════════════════════
#  TAB 2: COMMUNITY
# ════════════════════════════════════════════════════════════════════════════
with t2:

    comm_df = get_community()
    n_comm  = len(comm_df)

    # Jump here if coming from approved tab
    if st.session_state.get("jump_to_community"):
        st.session_state["jump_to_community"] = False

    st.markdown("### Share your timeline")
    st.markdown(f"**{n_comm} applicants** have shared their dates. Each submission makes predictions more accurate for everyone.")
    st.caption("Your full IRL number is never stored. Only series prefix + suffix are saved, matched with your dates.")

    with st.form("community_form", clear_on_submit=True):
        st.markdown("**Your application details**")
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            f_irl  = st.text_input("Your IRL number", value=st.session_state.irl_str or "", help="Used to identify your series and suffix only")
            f_emb  = st.selectbox("Embassy", EMBASSIES, key="f_emb")
        with fc2:
            f_type = st.selectbox("Visa type", VISA_TYPES, key="f_type")
            f_city = st.selectbox("VFS city",  VFS_CITIES, key="f_city")
        with fc3:
            f_vfs    = st.date_input("VFS submitted", format="DD/MM/YYYY", min_value=date(2025,1,1), max_value=date.today(), key="f_vfs")
            f_emb_d  = st.date_input("Embassy received", format="DD/MM/YYYY", min_value=date(2025,1,1), max_value=date.today(), key="f_emb_d")

        st.markdown("**Decision (if received)**")
        fo1, fo2 = st.columns(2)
        with fo1: f_outcome = st.selectbox("Outcome", ["Pending","Approved","Refused"], key="f_outcome")
        with fo2: f_dec_d = st.date_input("Decision date", format="DD/MM/YYYY",
                                           min_value=date(2025,1,1), max_value=date.today(), key="f_dec_d",
                                           help="Leave as today if still pending")

        submitted = st.form_submit_button("Submit my timeline", type="primary", use_container_width=True)

        if submitted:
            f_parsed = parse_irl(f_irl)
            if not f_parsed:
                st.error("Please enter a valid 8-digit IRL number")
            else:
                ok = submit_community(
                    irl_series=f_parsed["series4d"],
                    irl_suffix=f_parsed["suffix4"],
                    embassy=f_emb,
                    visa_type=f_type,
                    vfs_city=f_city,
                    vfs_date=f_vfs if isinstance(f_vfs, date) else None,
                    emb_received=f_emb_d if isinstance(f_emb_d, date) else None,
                    outcome=f_outcome,
                    decision_date=f_dec_d if f_outcome != "Pending" and isinstance(f_dec_d, date) else None,
                )
                if ok:
                    st.success("✅ Thank you! Here's what community data says about your wait:")
                    # Instant reward: show cohort data
                    if isinstance(f_emb_d, date):
                        reward = get_cohort(f_emb_d, f_type, f_emb)
                        if reward and reward["total"] >= 2:
                            st.markdown(f"""
Applications received around **{f_emb_d.strftime('%d %b %Y')}** for **{f_type}** visa at **{f_emb.split()[0]}**:

- **{reward['total']} reports** — {reward['decided']} decided, {reward['pending']} still pending
- **Earliest decision:** Day {reward['min_days']}
- **Median decision:** Day {reward['median_days']}
- **80th percentile:** Day {reward['p80_days']}
""")
                        else:
                            st.info("You're one of the first to submit for your dates — check back as more people contribute.")

    st.divider()

    # ── COMMUNITY STATS ───────────────────────────────────────────────────────
    if n_comm >= 3:
        st.markdown("### Community insights")

        decided = comm_df[comm_df["outcome"].isin(["Approved","Refused"])].copy() if len(comm_df)>0 else pd.DataFrame()
        decided_wd = decided.dropna(subset=["working_days"]) if len(decided)>0 else pd.DataFrame()

        s1, s2, s3 = st.columns(3)
        s1.metric("Total submissions",  n_comm)
        s2.metric("Decisions reported", len(decided_wd))
        if len(decided_wd) > 0:
            s3.metric("Median working days", f"{int(decided_wd['working_days'].median())} days")

        # Speed bracket chart
        if len(decided_wd) >= 3:
            st.markdown("#### Processing time distribution")
            bracket_counts = decided_wd["speed_bracket"].value_counts().reindex(BRACKETS, fill_value=0)
            bc_df = pd.DataFrame({
                "Time bracket": [BRACKET_LABELS.get(b,b) for b in bracket_counts.index],
                "Applications": bracket_counts.values,
            })
            st.bar_chart(bc_df.set_index("Time bracket")["Applications"])

        # VFS city transit
        if "vfs_to_emb_days" in comm_df.columns:
            transit = comm_df.dropna(subset=["vfs_to_emb_days"])
            transit = transit[transit["vfs_to_emb_days"].between(0,10)]
            if len(transit) >= 3:
                st.markdown("#### VFS city → embassy transit time")
                city_t = transit.groupby("vfs_city")["vfs_to_emb_days"].agg(
                    Count="count", Median="median", Min="min", Max="max"
                ).round(1).reset_index()
                city_t.columns = ["VFS City","Reports","Median days","Min","Max"]
                st.dataframe(city_t, use_container_width=True, hide_index=True)

        # Recent submissions (anonymised)
        if n_comm > 0:
            st.markdown("#### Recent submissions")
            show = comm_df.head(10)[[c for c in ["submitted_at","irl_series","visa_type","vfs_city","embassy","outcome","working_days"] if c in comm_df.columns]].copy()
            show.columns = [c.replace("_"," ").title() for c in show.columns]
            st.dataframe(show, use_container_width=True, hide_index=True)
    else:
        st.info(f"Community has {n_comm} submission(s) so far. Charts will appear once there are 3+ submissions.")


# ════════════════════════════════════════════════════════════════════════════
#  TAB 3: SUPPORT
# ════════════════════════════════════════════════════════════════════════════
with t3:
    st.markdown("### Support this tool")
    st.markdown("""
This tracker is free for every applicant — now and always.
The core status check, community comparisons, and email alerts will never be gated behind a paywall.

If this tool reduced your anxiety or saved you time, consider supporting the running costs.
""")

    st.markdown("#### Choose how to support")
    sup1, sup2 = st.columns(2)

    with sup1:
        st.markdown(f"""
<div style="background:var(--color-background-secondary);border-radius:8px;padding:20px;text-align:center">
<div style="font-size:20px;margin-bottom:8px">☕</div>
<div style="font-weight:500;margin-bottom:6px">Buy us a chai</div>
<div style="font-size:13px;color:var(--color-text-secondary);margin-bottom:12px">
One-time tip via Ko-fi.<br>Any amount helps. 0% fees.
</div>
<a href="{KOFI_URL}" target="_blank" style="display:block;padding:10px;background:#FF5E5B;color:white;border-radius:6px;text-decoration:none;font-weight:500;font-size:14px">
Support on Ko-fi →
</a>
</div>""", unsafe_allow_html=True)

    with sup2:
        st.markdown(f"""
<div style="background:var(--color-background-secondary);border-radius:8px;padding:20px;text-align:center">
<div style="font-size:20px;margin-bottom:8px">📲</div>
<div style="font-weight:500;margin-bottom:6px">UPI (India)</div>
<div style="font-size:13px;color:var(--color-text-secondary);margin-bottom:12px">
Instant, no signup.<br>UPI ID: <strong>{UPI_ID}</strong>
</div>
<div style="font-size:12px;background:var(--color-background-primary);border-radius:6px;padding:10px;border:0.5px solid var(--color-border-tertiary)">
Scan QR in your UPI app<br>or search UPI ID above
</div>
</div>""", unsafe_allow_html=True)

    st.divider()
    st.markdown("### What your support pays for")
    costs = [
        ("Streamlit Cloud hosting",  "₹0/month","Free forever for public apps"),
        ("Supabase database",        "₹0/month","Free tier — 500MB, plenty for years"),
        ("Email alerts (Resend)",    "₹0 → ₹1,660","Free up to 3,000 emails/month"),
        ("Domain name (optional)",   "₹66/month","Optional — app works without it"),
        ("Developer time",           "Your support","Maintaining, improving, adding features"),
    ]
    for service, cost, note in costs:
        c1, c2, c3 = st.columns([3,1.5,3])
        c1.write(service)
        c2.write(f"**{cost}**")
        c3.write(note)
    st.divider()

    st.markdown("### Coming soon — Ireland Arrival Guide")
    st.markdown("""
A comprehensive guide for Indian students arriving in Ireland:

- GNIB registration step-by-step
- Opening a bank account in your first week (Bank of Ireland, AIB, Revolut)
- Getting your PPS number
- Dublin neighbourhoods by budget and college proximity
- Student transport (Leap card, Dublin Bus, Luas)
- Grocery shopping (Lidl > Tesco for students)
- SIM cards (Three Ireland best for students)
- Student discounts and how to access them

**₹199 one-time · launching soon**
""")
    if st.button("Notify me when the guide is ready", use_container_width=True):
        st.info("Add your email in the Track tab's alert form — we'll notify you when the guide launches.")

    st.divider()
    st.caption("This tool is independent and not affiliated with the Irish Embassy, ISD, or any immigration authority. Data sourced directly from official embassy websites.")
