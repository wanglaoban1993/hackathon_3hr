"""Smart Buy Agent, live/cached idealo evidence -> Nebius decision.  Run:  streamlit run app_live.py"""
import pandas as pd
import streamlit as st

from agent import decide
from run_live import default_budget, list_cached

st.set_page_config(page_title="Smart Buy Agent (live)", page_icon="🛒", layout="wide")
st.title("🛒 Smart Buy Agent")
st.caption("Should I buy this now? idealo evidence → decision made by a live Nebius Token Factory model.")

# ---------- Sidebar: choose the evidence source ----------
with st.sidebar:
    source = st.radio("Evidence source", ["Cached idealo products", "New idealo search"])
    evidence = None
    if source == "Cached idealo products":
        cached = list_cached()
        key = st.selectbox("Product", list(cached),
                           format_func=lambda k: f"{cached[k].get('product_name') or k}")
        evidence = cached[key]
    else:
        st.caption("Uses the idealo API (500 calls/day). Find the pick number with "
                   "`python idealo_client.py \"<query>\" --search`.")
        q = st.text_input("Search query", "27 zoll monitor")
        pick = st.number_input("Pick result #", min_value=0, value=1, step=1)
        country = st.selectbox("Country", ["DE", "AT", "GB", "FR", "IT", "ES"])
        if st.button("Fetch from idealo"):
            from idealo_client import get_evidence
            with st.spinner("Fetching idealo data..."):
                st.session_state["fetched"] = get_evidence(q, country=country, pick=int(pick)).model_dump(exclude_none=True)
        evidence = st.session_state.get("fetched")

if not evidence:
    st.info("Choose a product in the sidebar.")
    st.stop()

# ---------- Evidence ----------
budget = st.number_input("Budget (€)", min_value=0, value=default_budget(evidence), step=10,
                         key=f"budget_{evidence.get('product_name')}",
                         help="Default: 110% of the median offer price")
st.subheader(evidence.get("product_name", "Product"))
ph = evidence.get("price_history") or {}
c1, c2, c3, c4 = st.columns(4)
c1.metric("idealo 'from' price", f"€{evidence.get('list_price')}")
c2.metric("29-day avg", f"€{ph.get('avg')}",
          f"{ph.get('change_percent') or 0:+.1f}% in {ph.get('period_days')} days", delta_color="off")
c3.metric("Product rating", f"{evidence.get('user_rating')} ★", f"{evidence.get('user_review_count')} reviews",
          delta_color="off")
c4.metric("Offers shown", f"{len(evidence.get('offers', []))} of {evidence.get('total_offers_on_idealo')}")

cols = ["shop", "total_price", "shop_rating", "shop_rating_count", "delivery_status", "delivery_text"]
offers = evidence.get("offers", [])
offers_df = pd.DataFrame(offers).reindex(columns=cols) if offers else pd.DataFrame(columns=cols)
table = st.empty()
table.dataframe(offers_df, hide_index=True, width="stretch")
for g in evidence.get("gaps", []):
    st.caption(f"Data gap: {g}")

# ---------- Decision ----------
if st.button("Ask the agent", type="primary"):
    with st.spinner("Nebius model is weighing the evidence..."):
        try:
            d = decide(evidence, budget or None)
        except RuntimeError as e:
            st.error(str(e))
            st.stop()

    if len(offers_df):
        table.dataframe(
            offers_df.style.apply(
                lambda r: ["background-color: rgba(46,160,67,0.2)" if r["shop"] in d.cited_offers else ""] * len(r),
                axis=1),
            hide_index=True, width="stretch")

    color = {"BUY_NOW": "green", "WAIT": "orange", "AVOID": "red"}[d.decision]
    st.markdown(f"## :{color}[{d.decision}]")
    st.progress(d.confidence, text=f"Confidence {d.confidence:.0%}")
    st.info(f"**Next step:** {d.next_step}")

    left, right = st.columns(2)
    with left:
        st.markdown("**Reasons**")
        for r in d.reasons:
            st.markdown(f"- {r}")
    with right:
        st.markdown("**⚠️ Conflicts found**" if d.conflicts_found else "**✅ No conflicts found**")
        for c in d.conflicts_found:
            st.warning(c)

    with st.expander("Pre-check flags (computed by code before the model decides)"):
        for f in d.flags or ["none"]:
            st.markdown(f"- {f}")

    st.caption(f"Decided by `{d.model_used}` on Nebius Token Factory · call `{d.nebius_call_id}`")
