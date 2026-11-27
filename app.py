"""Smart Buy Agent: Streamlit starter UI.  Run:  streamlit run app.py"""
import pandas as pd
import streamlit as st

from agent import decide
from cases import CASES

st.set_page_config(page_title="Smart Buy Agent", page_icon="🛒")
st.title("🛒 Smart Buy Agent")
st.caption("Should I buy this now? Decision made live by a Nebius Token Factory model.")

case_name = st.radio("Demo case", list(CASES), horizontal=True)
product, budget, offers = CASES[case_name]

st.subheader(f"{product}, budget €{budget}")
st.dataframe(pd.DataFrame(offers), hide_index=True, use_container_width=True)

if st.button("Ask the agent", type="primary"):
    with st.spinner("Nebius model is deciding..."):
        d = decide(product, budget, offers)

    color = {"BUY_NOW": "green", "WAIT": "orange", "AVOID": "red"}[d.decision]
    st.markdown(f"## :{color}[{d.decision}]")
    st.progress(d.confidence, text=f"Confidence {d.confidence:.0%}")
    st.info(f"**Next step:** {d.next_step}")

    st.markdown("**Reasons**")
    for r in d.reasons:
        st.markdown(f"- {r}")

    if d.conflicts_found:
        st.markdown("**⚠️ Conflicts found**")
        for c in d.conflicts_found:
            st.warning(c)

    st.markdown(f"**Cited offers:** {', '.join(d.cited_offers)}")
    st.caption(f"Decided by `{d.model_used}` on Nebius Token Factory · call `{d.nebius_call_id}`")
