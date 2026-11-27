"""Smart Buy Agent: Streamlit UI.  Run:  streamlit run app.py"""
import html
import json

import altair as alt
import pandas as pd
import streamlit as st

from agent import LOG_PATH, LOW_SHOP_RATING, decide
from cases import CASES

st.set_page_config(page_title="Smart Buy Agent", page_icon="🛒", layout="wide")
st.title("🛒 Smart Buy Agent")
st.caption("Should I buy this now? Live idealo evidence in, a decision out. "
           "The decision is made by a live model call on Nebius Token Factory.")

LABELS = {"routine": "Routine · Samsung Odyssey G50F", "conflicting": "Conflicting · GigaByte M27UP Ice"}
GREEN, RED, AMBER = "rgba(46,160,67,0.25)", "rgba(248,81,73,0.22)", "rgba(210,153,34,0.22)"


def log_entries(call_id: str) -> list[dict]:
    """All logged attempts that belong to the run ending in call_id (usually one)."""
    if not LOG_PATH.exists():
        return []
    entries = [json.loads(line) for line in LOG_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    for i, entry in enumerate(entries):
        if entry.get("call_id") == call_id:
            start = i - (entry.get("attempt", 1) - 1)
            return entries[max(start, 0):i + 1]
    return []


def row_style(row, cited):
    if row["shop"] in cited:
        color = GREEN
    elif pd.notna(row["shop_rating"]) and row["shop_rating"] < LOW_SHOP_RATING:
        color = RED
    elif row["delivery_status"] in (None, "UNKNOWN") or pd.isna(row["delivery_status"]):
        color = AMBER
    else:
        color = ""
    return [f"background-color: {color}" if color else ""] * len(row)


def offer_chart(df, cited, median, budget):
    """Total price per shop, coloured the same way as the table."""
    def status(row):
        if row["shop"] in cited:
            return "Agent relied on"
        if pd.notna(row["shop_rating"]) and row["shop_rating"] < LOW_SHOP_RATING:
            return "Low shop rating"
        if row["delivery_status"] in (None, "UNKNOWN") or pd.isna(row["delivery_status"]):
            return "Delivery unknown"
        return "OK"
    data = df.assign(status=df.apply(status, axis=1))
    low = float(data["total_price"].min()) * 0.9
    scale = alt.Scale(domain=["Agent relied on", "OK", "Delivery unknown", "Low shop rating"],
                      range=["#2ea043", "#8b949e", "#d29922", "#f85149"])
    bars = alt.Chart(data).mark_bar(cornerRadiusEnd=4).encode(
        y=alt.Y("shop:N", sort="x", title=None),
        x=alt.X("total_price:Q", title="Total price incl. shipping (€)", scale=alt.Scale(domainMin=low, clamp=True)),
        color=alt.Color("status:N", scale=scale, legend=alt.Legend(orient="bottom", title=None)),
        tooltip=["shop", "total_price", "shop_rating", "shop_rating_count", "delivery_text"])
    labels = bars.mark_text(align="left", dx=4).encode(text=alt.Text("total_price:Q", format=".2f"), color=alt.value("gray"))
    lines = pd.DataFrame([{"x": v, "what": n} for n, v in (("median", median), ("budget", budget)) if v])
    rules = alt.Chart(lines).mark_rule(strokeDash=[5, 4]).encode(x="x:Q", color=alt.value("gray"), tooltip=["what", "x"])
    return (bars + labels + rules).properties(height=32 * len(data) + 60)


# ---------------------------------------------------------------- evidence
st.markdown("### 1 · Evidence from idealo")
case_name = st.radio("Demo case", list(CASES), horizontal=True, format_func=lambda k: LABELS.get(k, k))
evidence, default_budget = CASES[case_name]
budget = st.number_input("Budget (€)", min_value=0, value=default_budget, step=10, key=f"budget_{case_name}")

st.subheader(evidence.get("product_name", "Product"))
ph = evidence.get("price_history") or {}
stats = evidence.get("market_stats") or {}
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("idealo 'from' price", f"€{evidence.get('list_price')}")
c2.metric("Median offer", f"€{stats.get('median_total')}")
c3.metric("29-day avg", f"€{ph.get('avg')}", f"{ph.get('change_percent', 0):+.1f}% in {ph.get('period_days')} days",
          delta_color="off")
c4.metric("Product rating", f"{evidence.get('user_rating')} ★", f"{evidence.get('user_review_count')} reviews",
          delta_color="off")
c5.metric("Offers shown", f"{len(evidence.get('offers', []))} of {evidence.get('total_offers_on_idealo')}")

result = st.session_state.get("result")
if result and result["key"] != (case_name, budget):
    result = None  # the case or budget changed: the old decision no longer applies
d = result["decision"] if result else None

cols = ["shop", "total_price", "shop_rating", "shop_rating_count", "delivery_status", "delivery_text"]
offers_df = pd.DataFrame(evidence.get("offers", [])).reindex(columns=cols).sort_values("total_price")
cited = d.cited_offers if d else []
chart_col, table_col = st.columns([5, 6])
chart_col.altair_chart(offer_chart(offers_df, cited, stats.get("median_total"), budget), width="stretch")
table_col.dataframe(
    offers_df.style.apply(row_style, axis=1, cited=cited)
    .format({"total_price": "€{:.2f}", "shop_rating": "{:.2f}", "shop_rating_count": "{:,.0f}"}, na_rep="unknown"),
    hide_index=True, width="stretch", height=38 * len(offers_df) + 40,
    column_config={"shop": "Shop", "total_price": "Total", "shop_rating": "Shop rating", "shop_rating_count": "Ratings",
                   "delivery_status": "Delivery", "delivery_text": "Delivery detail"})
st.caption(f"🟥 shop rating under {LOW_SHOP_RATING}/5 · 🟧 delivery unknown · 🟩 offer the agent relied on (after it decides) · dashed lines: median and budget. "
           + " ".join(f"Data gap: {g}" for g in evidence.get("gaps", [])))

# ---------------------------------------------------------------- decision
if st.button("Ask the agent", type="primary"):
    try:
        with st.spinner("Calling the Nebius model: it is weighing the evidence (10-20 s)..."):
            decision = decide(evidence, budget)
        st.session_state["result"] = {"key": (case_name, budget), "decision": decision}
        st.rerun()
    except Exception as error:  # show the real reason on screen instead of a stack trace
        st.error(f"The agent could not decide: {error}")

if d:
    st.divider()
    st.markdown("### 2 · Decision by the Nebius model")
    tone = {"BUY_NOW": "#2ea043", "WAIT": "#d29922", "AVOID": "#f85149"}[d.decision]
    note = "lowered: the evidence conflicts" if d.conflicts_found else "evidence is consistent"
    st.markdown(
        f"""<div style="border:1px solid {tone};border-left:10px solid {tone};border-radius:12px;padding:18px 22px;margin-bottom:14px">
        <div style="display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px">
          <span style="font-size:2.4rem;font-weight:800;color:{tone};letter-spacing:.02em">{d.decision.replace('_', ' ')}</span>
          <span style="font-size:1.05rem"><b>{d.confidence:.0%}</b> confidence · {note}</span>
        </div>
        <div style="height:8px;border-radius:4px;background:rgba(128,128,128,.25);margin:10px 0 14px">
          <div style="height:8px;border-radius:4px;width:{d.confidence:.0%};background:{tone}"></div></div>
        <div style="font-size:1.15rem"><b>Next step:</b> {html.escape(d.next_step)}</div>
        <div style="opacity:.7;margin-top:8px;font-size:.9rem">Decided live by <code>{html.escape(d.model_used)}</code> on Nebius Token Factory</div>
        </div>""", unsafe_allow_html=True)

    left, right = st.columns(2)
    with left:
        st.markdown("**Reasons**")
        for r in d.reasons:
            st.markdown(f"- {r}")
    with right:
        st.markdown(f"**⚠️ {len(d.conflicts_found)} conflict(s) in the evidence**" if d.conflicts_found
                    else "**✅ No conflicts in the evidence**")
        for c in d.conflicts_found:
            st.warning(c)

    with st.expander(f"Pre-check flags ({len(d.flags)}): facts spotted by code. Code flags, the model decides."):
        for f in d.flags:
            st.markdown(f"- {f}")

    # ------------------------------------------------------------ proof of the call
    st.markdown("### 3 · Proof: the Token Factory call behind this decision")
    calls = log_entries(d.nebius_call_id)
    if not calls:
        st.caption(f"Decided by `{d.model_used}` · call `{d.nebius_call_id}`")
    for call in calls:
        usage = call.get("usage") or {}
        reasoning = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
        m1, m2, m3, m4, m5 = st.columns([3, 1, 1, 1, 1])
        m1.metric("Model", call.get("model_reported") or call.get("model_requested"))
        m2.metric("Latency", f"{call.get('latency_s')} s")
        m3.metric("Tokens in", usage.get("prompt_tokens", "–"))
        m4.metric("Tokens out", usage.get("completion_tokens", "–"))
        m5.metric("of which reasoning", reasoning if reasoning is not None else "–")
        st.caption(f"Call ID `{call.get('call_id')}` · {call.get('timestamp')} · attempt {call.get('attempt')} · "
                   f"endpoint `https://api.tokenfactory.nebius.com/v1/chat/completions` · logged in `{LOG_PATH.name}`")
        with st.expander("Request sent to the model (prompt and evidence)"):
            for message in call.get("request_messages", []):
                st.markdown(f"**{message['role']}**")
                st.code(message["content"], language="json" if message["role"] == "user" else None, wrap_lines=True)
        with st.expander("Raw response from the model"):
            st.code(call.get("response_text", ""), language="json", wrap_lines=True)
