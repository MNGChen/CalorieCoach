"""Reusable presentation helpers for the Streamlit interface."""
from __future__ import annotations

import streamlit as st


def apply_app_shell() -> None:
    """Apply a restrained, accessible visual system to every app page."""
    st.markdown("""
    <style>
      :root { --cc-green:#197a62; --cc-ink:#18332e; --cc-muted:#64748b; --cc-surface:#ffffff; --cc-line:#e4ebe8; }
      .stApp { background: linear-gradient(160deg, #f4faf7 0%, #ffffff 42%, #f6faf9 100%); color:var(--cc-ink); }
      .block-container { max-width:1180px; padding-top:2.4rem; padding-bottom:3rem; }
      [data-testid="stSidebar"] { background:#143c34; }
      [data-testid="stSidebar"] * { color:#f1faf6; }
      [data-testid="stMetric"] { background:var(--cc-surface); border:1px solid var(--cc-line); border-radius:16px; padding:1rem; box-shadow:0 4px 16px rgba(23, 57, 47, .05); }
      [data-testid="stTabs"] button { font-weight:650; padding:0.8rem 1rem; }
      [data-testid="stTabs"] button[aria-selected="true"] { color:var(--cc-green); }
      .stButton > button { border-radius:10px; font-weight:650; min-height:2.6rem; }
      .stDataFrame { border:1px solid var(--cc-line); border-radius:12px; overflow:hidden; }
      .cc-hero { background:linear-gradient(120deg,#123f35,#197a62); border-radius:22px; color:white; padding:1.7rem 1.8rem; margin:0 0 1.35rem; box-shadow:0 14px 30px rgba(20,60,52,.16); }
      .cc-kicker { font-size:.78rem; font-weight:750; letter-spacing:.09em; opacity:.78; text-transform:uppercase; margin-bottom:.45rem; }
      .cc-hero h1 { color:white; font-size:2rem; margin:0 0 .45rem; }
      .cc-hero p { margin:0; opacity:.9; font-size:1rem; }
      .cc-section { margin:1.8rem 0 .75rem; }
      .cc-section h2 { margin:0; font-size:1.28rem; color:var(--cc-ink); }
      .cc-section p { margin:.22rem 0 0; color:var(--cc-muted); }
      .cc-empty { border:1px dashed #b9d8cf; border-radius:16px; background:#fbfefd; padding:1.3rem; color:var(--cc-muted); }
      @media (max-width: 700px) { .block-container { padding:1.2rem .85rem 2rem; } .cc-hero { padding:1.3rem; } .cc-hero h1 { font-size:1.55rem; } }
    </style>
    """, unsafe_allow_html=True)


def page_header(title: str, subtitle: str, kicker: str = "CALORIECOACH") -> None:
    st.markdown(f"""<section class="cc-hero"><div class="cc-kicker">{kicker}</div><h1>{title}</h1><p>{subtitle}</p></section>""", unsafe_allow_html=True)


def section_header(title: str, subtitle: str = "") -> None:
    st.markdown(f"""<div class="cc-section"><h2>{title}</h2><p>{subtitle}</p></div>""", unsafe_allow_html=True)


def empty_state(message: str) -> None:
    st.markdown(f'<div class="cc-empty">{message}</div>', unsafe_allow_html=True)
