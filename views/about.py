"""About / How it works. Content adapted from the original pages/about.py."""
import streamlit as st

st.header("ℹ️ About / How it works")
st.markdown(
    """
<div class="card">
  <h3 style="margin:0;">What this tool is</h3>
  <p class="muted" style="margin:0.5rem 0 0;">
    A <b>player props research tool</b> for the NBA, NFL and MLB. It shows how a player has performed
    against a line in past games, with trends, distributions and context.
  </p>
</div>

<div class="card">
  <h3 style="margin:0;">What this tool is not</h3>
  <ul class="muted" style="margin:0.5rem 0 0;">
    <li>Not guaranteed picks or predictions</li>
    <li>Not a sportsbook, and it shows no odds</li>
    <li>Not betting advice</li>
  </ul>
</div>

<div class="card">
  <h3 style="margin:0;">How the numbers work</h3>
  <ul class="muted" style="margin:0.5rem 0 0;">
    <li><b>Over</b>: stat above the line. <b>Under</b>: below it. <b>Push</b>: exactly equal.</li>
    <li><b>Historical over rate</b> = overs ÷ (overs + unders). Pushes are shown separately and left out.</li>
    <li>Season, season type, opponent and home/away filters are applied first. The recent-games window
        then keeps the most recent games that remain.</li>
    <li>Everything is calculated from exact values and only rounded for display. Missing values show as
        “Unavailable”, never as 0.</li>
    <li>Hit rates describe the past. They are not calibrated probabilities for the next game.</li>
  </ul>
</div>

<div class="card">
  <h3 style="margin:0;">How to use it in 30 seconds</h3>
  <ol class="muted" style="margin:0.5rem 0 0;">
    <li>Pick a sport at the top</li>
    <li>Choose seasons, a player and a stat</li>
    <li>Pick a recent-games window and any filters</li>
    <li>Enter the line you are researching</li>
    <li>Read the summary, chart and game log, and download the games as CSV if you like</li>
  </ol>
</div>

<div class="card">
  <h3 style="margin:0;">Data sources</h3>
  <ul class="muted" style="margin:0.5rem 0 0;">
    <li><b>NBA</b>: stats.nba.com player game logs via <code>nba_api</code>.</li>
    <li><b>NFL</b>: weekly player stats and schedules from <b>nflverse</b> via <code>nflreadpy</code> (CC-BY 4.0).</li>
    <li><b>MLB</b>: MLB Stats API boxscores, © MLB Advanced Media, used for individual, non-commercial research.</li>
  </ul>
  <p class="muted" style="margin:0.5rem 0 0;">The app reads stored copies of this data; refreshes run separately.</p>
</div>
""",
    unsafe_allow_html=True,
)
