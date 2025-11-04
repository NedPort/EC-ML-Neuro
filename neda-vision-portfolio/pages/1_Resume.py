import streamlit as st
from pathlib import Path

st.set_page_config(page_title="Resume · Neda Vision", page_icon="📄", layout="wide")

st.title("Resume")
st.write("Upload your latest PDF resume below, and it will become downloadable on this page.")

uploaded = st.file_uploader("Upload resume PDF", type=["pdf"])
resume_path = Path("assets/resume.pdf")

if uploaded:
    resume_path.write_bytes(uploaded.getvalue())
    st.success("Resume uploaded successfully.")

if resume_path.exists():
    with open(resume_path, "rb") as f:
        st.download_button("Download Resume (PDF)", f, file_name="Neda_Resume.pdf")
else:
    st.warning("No resume uploaded yet.")

st.divider()
st.subheader("Skills Snapshot")
left, right = st.columns(2)
with left:
    st.markdown("- Transformers, MoE, GNNs")
    st.markdown("- fNIRS, EC (GPDC), signal processing")
    st.markdown("- Python, PyTorch, TensorFlow, Streamlit")
with right:
    st.markdown("- Time-series forecasting (Moirai/MoE)")
    st.markdown("- Visualization (Plotly/Matplotlib)")
    st.markdown("- Research writing and experimentation")
