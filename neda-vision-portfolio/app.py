import streamlit as st
from pathlib import Path

st.set_page_config(
    page_title="Neda Vision · NeuroAI Portfolio",
    page_icon="🧠",
    layout="wide"
)

# Sidebar brand
col1, col2 = st.columns([1,3])
with col1:
    st.image("assets/logo.svg", use_column_width=True)
with col2:
    st.markdown("### **Neda Vision**")
    st.caption("NeuroAI · fNIRS · Transformers · Forecasting")

st.sidebar.image("assets/logo.svg")
st.sidebar.markdown("## Neda Vision")
st.sidebar.caption("Interactive AI Portfolio")

st.title("Neda Vision · Interactive AI Portfolio")
st.write(
    "Welcome to my research & engineering portfolio. Explore publications, live AI demos, forecasting labs, and visualizations."
)

st.markdown("#### Quick Links")
c1, c2, c3 = st.columns(3)
with c1:
    st.page_link("pages/1_Resume.py", label="Resume", icon="📄")
with c2:
    st.page_link("pages/2_Publications.py", label="Publications", icon="🧪")
with c3:
    st.page_link("pages/3_AI_Demos.py", label="AI Demos", icon="🤖")

st.divider()
st.markdown("##### Featured Highlights")
a, b, c = st.columns(3)
with a:
    st.metric("EC-Transformer", "fNIRS", "Gating + EC")
with b:
    st.metric("Moirai-MoE", "Forecasting", "+PE + log-features")
with c:
    st.metric("GNN Encoder", "Graphs", "Contrastive")

st.info("Tip: Use the sidebar or the quick links above to navigate.")
st.caption("© 2025-10-28 · Built with Streamlit")
