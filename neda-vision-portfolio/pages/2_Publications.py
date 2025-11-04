import streamlit as st
import json
from pathlib import Path

st.set_page_config(page_title="Publications · Neda Vision", page_icon="🧪", layout="wide")
st.title("Publications")

data_file = Path("assets/publications.json")
placeholder = [
    {
        "title": "EC-Transformer: Effective Connectivity-aware Transformers for fNIRS",
        "venue": "Preprint / Under Review",
        "year": "2025",
        "links": {"arXiv": "", "DOI": ""},
        "highlights": [
            "Novel channel-wise + time-wise embeddings",
            "Gating fusion; EC-driven features"
        ]
    },
    {
        "title": "Moirai-MoE for Multi-Office Healthcare Forecasting",
        "venue": "In preparation",
        "year": "2025",
        "links": {"Demo": ""},
        "highlights": [
            "Positional encodings + log-feature engineering",
            "Interactive Streamlit dashboards"
        ]
    }
]

if not data_file.exists():
    data_file.write_text(json.dumps(placeholder, indent=2))

db = json.loads(data_file.read_text())

for i, p in enumerate(db, start=1):
    with st.container(border=True):
        st.markdown(f"**{i}. {p['title']}**  
*{p['venue']} ({p['year']})*")
        if p.get("links"):
            link_strs = []
            for k, v in p["links"].items():
                if v:
                    link_strs.append(f"[{k}]({v})")
            if link_strs:
                st.markdown(" | ".join(link_strs))
        if p.get("highlights"):
            st.markdown("**Highlights:**")
            for h in p["highlights"]:
                st.markdown(f"- {h}")
st.info("Edit `assets/publications.json` to update this list.")
