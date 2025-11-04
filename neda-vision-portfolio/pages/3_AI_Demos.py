import streamlit as st
import numpy as np
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="AI Demos · Neda Vision", page_icon="🤖", layout="wide")
st.title("AI Demos")

tab1, tab2, tab3 = st.tabs(["EC-Transformer (fNIRS)", "Moirai-MoE Forecasting", "GNN Encoder"])

with tab1:
    st.subheader("EC-Transformer (Demo)")
    st.caption("Upload a tiny fNIRS trial; we visualize an example connectivity graph and a mock prediction.")
    file = st.file_uploader("Upload fNIRS trial (CSV: channels x time)", type=["csv"], key="fnirs_upload")
    if file:
        data = pd.read_csv(file, header=None)
        st.write("Shape:", data.shape)
        # Simple correlation as a stand-in connectivity
        corr = data.T.corr()
        fig = px.imshow(corr, title="Connectivity (correlation demo)")
        st.plotly_chart(fig, use_container_width=True)
        st.success("Mock classification: **Alert** (confidence 0.76)")
    else:
        st.info("Upload a small CSV to see the demo.")

with tab2:
    st.subheader("Moirai-MoE Forecasting Lab")
    st.caption("Demonstrates feature engineering with positional encodings + log transformation on toy data.")
    steps = st.slider("Horizon", 24, 240, 72, step=24)
    freq = st.selectbox("Seasonality", ["daily-ish", "weekly-ish", "yearly-ish"], index=1)
    n = 500
    t = np.arange(n + steps)
    if freq == "daily-ish":
        seasonal = np.sin(2 * np.pi * t / 24)
    elif freq == "weekly-ish":
        seasonal = np.sin(2 * np.pi * t / 168)
    else:
        seasonal = np.sin(2 * np.pi * t / 365)

    trend = 0.002 * t
    noise = 0.2 * np.random.randn(n + steps)
    series = 3 + trend + seasonal + noise
    series = np.maximum(series, 1e-3)  # avoid negative
    log_series = np.log(series)

    # Positional encoding (simple sin/cos)
    pe = np.column_stack([
        np.sin(2 * np.pi * t / 24),
        np.cos(2 * np.pi * t / 24),
        np.sin(2 * np.pi * t / 168),
        np.cos(2 * np.pi * t / 168),
    ])

    df = pd.DataFrame({
        "t": t,
        "y": series,
        "y_log": log_series,
        "pe_sin_24": pe[:,0],
        "pe_cos_24": pe[:,1],
        "pe_sin_168": pe[:,2],
        "pe_cos_168": pe[:,3],
    })

    st.markdown("**Feature preview (first 10 rows)**")
    st.dataframe(df.head(10))

    # Naive forecast baseline on log-scale + inverse
    hist = log_series[:n]
    future_pe = pe[n:]
    # simple baseline: last value + seasonal adjustment from pe
    last = hist[-1]
    pe_w = np.array([0.2, 0.2, 0.1, 0.1])
    adjustment = future_pe @ pe_w
    yhat_log = last + adjustment
    yhat = np.exp(yhat_log)

    fig = px.line(pd.DataFrame({
        "t": np.r_[t[:n], t[n:]],
        "value": np.r_[series[:n], yhat],
        "split": ["history"]*n + ["forecast"]*steps
    }), x="t", y="value", color="split", title="Toy Forecast with Log + PE features (demo)")
    st.plotly_chart(fig, use_container_width=True)

with tab3:
    st.subheader("GNN Encoder (Concept)")
    st.caption("Visualizes random node embeddings to illustrate graph representation learning outputs.")
    nodes = st.slider("Nodes", 12, 64, 24, step=4)
    emb = np.random.randn(nodes, 2)
    df = pd.DataFrame(emb, columns=["x", "y"])
    df["node"] = range(nodes)
    fig = px.scatter(df, x="x", y="y", text="node", title="Random Embeddings (placeholder)")
    fig.update_traces(textposition="top center")
    st.plotly_chart(fig, use_container_width=True)
