import streamlit as st

st.set_page_config(page_title="About", page_icon="ℹ️", layout="wide")

# Bigger, cleaner UI styling
st.markdown(
    """
    <style>
      /* Make the whole app feel bigger */
      .block-container { padding-top: 2rem; padding-bottom: 2rem; max-width: 1200px; }
      h1 { font-size: 2.2rem !important; }
      h2 { font-size: 1.6rem !important; margin-top: 1.2rem !important; }
      h3 { font-size: 1.2rem !important; margin-top: 1rem !important; }
      p, li, div { font-size: 1.05rem !important; line-height: 1.6 !important; }

      /* Make sidebar text slightly bigger */
      section[data-testid="stSidebar"] * { font-size: 1.03rem !important; }

      /* Card look */
      .card {
        border: 1px solid rgba(255,255,255,0.12);
        border-radius: 14px;
        padding: 16px 18px;
        margin: 12px 0;
        background: rgba(255,255,255,0.03);
      }
      .muted { opacity: 0.85; }
    </style>
    """,
    unsafe_allow_html=True
)

st.title("ℹ️ About / How It Works")

st.markdown(
    """
<div class="card">
  <h3 style="margin:0;">What this tool is</h3>
  <p class="muted" style="margin:0.5rem 0 0;">
    This is an <b>NBA player props research tool</b>. It helps you evaluate props with trends, distributions, and context so you can make better decisions.
  </p>
</div>

<div class="card">
  <h3 style="margin:0;">What this tool is not</h3>
  <ul class="muted" style="margin:0.5rem 0 0;">
    <li>Not guaranteed picks</li>
    <li>Not a sportsbook</li>
    <li>Not betting advice</li>
  </ul>
</div>

<div class="card">
  <h3 style="margin:0;">Who it is for?</h3>
  <ul class="muted" style="margin:0.5rem 0 0;">
    <li>NBA bettors who want research and context</li>
    <li>Users who want to understand risk, not just averages</li>
    <li>People who prefer evidence over “locks”</li>
  </ul>
</div>

<div class="card">
  <h3 style="margin:0;">How to use it in 30 seconds</h3>
  <ol class="muted" style="margin:0.5rem 0 0;">
    <li>Select a player and stat</li>
    <li>Choose a timeframe (last 5, 10, 15, season)</li>
    <li>Check trends and distributions</li>
    <li>Compare to the line you are considering</li>
    <li>Decide based on what the data shows</li>
  </ol>
</div>

<div class="card">
  <h3 style="margin:0;">Why this is different</h3>
  <p class="muted" style="margin:0.5rem 0 0;">
    Most apps show picks. This tool is built to show the <b>why</b>. It is a research assistant for NBA props.
  </p>
</div>
"""
,
    unsafe_allow_html=True
)

