"""Smart Buy Agent: Streamlit starter UI.  Run:  streamlit run app.py"""
import pandas as pd
import streamlit as st

from agent import decide
from cases import CASES

st.set_page_config(page_title="Smart Buy Agent", page_icon="🛒", layout="wide")
st.title("🛒 Smart Buy Agent")
st.caption("Should I buy this now? Live idealo evidence → decision made by a Nebius Token Factory model.")

case_name = st.radio("Demo case", list(CASES), horizontal=True)
evidence, default_budget = CASES[case_name]
budget = st.number_input("Budget (€)", min_value=0, value=default_budget, step=10)

st.subheader(evidence.get("product_name", "Product"))
ph = evidence.get("price_history") or {}
c1, c2, c3, c4 = st.columns(4)
c1.metric("idealo 'from' price", f"€{evidence.get('list_price')}")
c2.metric("29-day avg", f"€{ph.get('avg')}", f"{ph.get('change_percent', 0):+.1f}% in {ph.get('period_days')} days",
          delta_color="off")
c3.metric("Product rating", f"{evidence.get('user_rating')} ★", f"{evidence.get('user_review_count')} reviews",
          delta_color="off")
c4.metric("Offers shown", f"{len(evidence.get('offers', []))} of {evidence.get('total_offers_on_idealo')}")

cols = ["shop", "total_price", "shop_rating", "shop_rating_count", "delivery_status", "delivery_text"]
offers_df = pd.DataFrame(evidence.get("offers", []))[cols]
table = st.empty()
table.dataframe(offers_df, hide_index=True, use_container_width=True)
for g in evidence.get("gaps", []):
    st.caption(f"Data gap: {g}")

if st.button("Ask the agent", type="primary"):
    with st.spinner("Nebius model is weighing the evidence..."):
        d = decide(evidence, budget)

    # Highlight the shops the model cited
    table.dataframe(
        offers_df.style.apply(lambda r: ["background-color: rgba(46,160,67,0.2)" if r["shop"] in d.cited_offers else ""] * len(r), axis=1),
        hide_index=True, use_container_width=True)

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
        for f in d.flags:
            st.markdown(f"- {f}")

    st.caption(f"Decided by `{d.model_used}` on Nebius Token Factory · call `{d.nebius_call_id}`")
