# Neda Vision · Interactive AI Portfolio

Dark-mode Streamlit app to showcase papers, MoE forecasting, EC-Transformer demos, and visualizations.

## Quickstart

```bash
# 1) Create & activate env (optional)
python -m venv .venv && source .venv/bin/activate  # (Linux/Mac)
# On Windows:
# python -m venv .venv && .venv\Scripts\activate

# 2) Install
pip install -r requirements.txt

# 3) Run
streamlit run app.py
```

## Structure

```
neda-vision-portfolio/
├── app.py
├── pages/
│   ├── 1_Resume.py
│   ├── 2_Publications.py
│   ├── 3_AI_Demos.py
│   └── 4_Contact.py
├── assets/
│   ├── logo.svg
│   └── publications.json  (auto-created on first run)
├── .streamlit/
│   └── config.toml
├── requirements.txt
└── README.md
```

## Customize

- Replace `assets/logo.svg` with your own minimal geometric brain logo if desired.
- Upload your resume on the **Resume** page to make it downloadable.
- Edit `assets/publications.json` to add papers, links, and highlights.
- Add real model code to **AI Demos** tabs when ready (EC-Transformer, Moirai-MoE).

## Deploy (Free)
- Push this folder to a GitHub repo.
- Go to [Streamlit Community Cloud](https://share.streamlit.io/), connect your repo, and deploy.
- The dark theme is configured in `.streamlit/config.toml`.

© 2025-10-28 Neda Vision
