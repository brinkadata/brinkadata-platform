# ---------------------------------------------------------
# landing.py  (FULL FILE)
# Brinkadata landing page (Streamlit)
# ---------------------------------------------------------

import streamlit as st

# ✅ Update this to your analyzer URL (local or deployed)
# Local analyzer is typically: http://localhost:8501
ANALYZER_URL = "http://localhost:8501"

st.set_page_config(
    page_title="Brinkadata Platform — Property & Business Intelligence",
    page_icon="📊",
    layout="wide",
)

# ---------- Styling ----------
PAGE_CSS = """
<style>
main { padding-top: 1.25rem; }

/* Hero */
.hero-wrap { display:flex; gap:1.5rem; align-items:flex-start; justify-content:space-between; }
.hero-left { max-width: 60%; }
.hero-right { width: 36%; }
.hero-title { font-size: 2rem; font-weight: 800; margin-bottom: 0.35rem; }
.hero-subtitle { font-size: 1.0rem; color: rgba(0,0,0,0.65); margin-bottom: 0.8rem; }
.kpi-card {
  border: 1px solid rgba(0,0,0,0.10);
  border-radius: 12px;
  padding: 0.9rem 1rem;
  background: rgba(0,0,0,0.02);
}
.small { font-size: 0.9rem; color: rgba(0,0,0,0.70); }

/* Platform cards */
.card-row { display:flex; gap: 0.9rem; }
.pcard {
  flex: 1;
  border: 1px solid rgba(0,0,0,0.10);
  border-radius: 14px;
  padding: 0.9rem 1rem;
  background: #fff;
}
.badge-live {
  display:inline-block; font-size: 0.75rem; padding: 0.1rem 0.5rem;
  border-radius: 999px; background: rgba(0,128,0,0.10); color: #146c2e;
  border: 1px solid rgba(0,128,0,0.18);
  margin-right: 0.4rem;
}
.badge-soon {
  display:inline-block; font-size: 0.75rem; padding: 0.1rem 0.5rem;
  border-radius: 999px; background: rgba(2,132,199,0.10); color: #075985;
  border: 1px solid rgba(2,132,199,0.18);
  margin-right: 0.4rem;
}
.pcard h4 { margin: 0.35rem 0 0.25rem 0; }
.pcard p { margin: 0.15rem 0; color: rgba(0,0,0,0.70); font-size: 0.92rem; }

/* Footer */
.footer { margin-top: 2.0rem; padding-top: 1rem; border-top: 1px solid rgba(0,0,0,0.10); }
</style>
"""
st.markdown(PAGE_CSS, unsafe_allow_html=True)

# ---------- Logo ----------
# Place Brink_1.jpg in the same folder as landing.py
try:
    st.image("Brink_1.jpg", width=78)
except Exception:
    pass

# ---------- Header / Hero ----------
st.markdown(
    """
<div class="hero-wrap">
  <div class="hero-left">
    <div class="hero-title">Property & Business Intelligence for Real Estate Investors.</div>
    <div class="hero-subtitle">
      Brinkadata – Property Intelligence turns deals into clear grades, KPIs, flip/BRRRR metrics, and AI explanations — so you can compare rentals, flips, and BRRRR projects in one unified view.
    </div>
  </div>
  <div class="hero-right">
    <div class="kpi-card">
      <div class="small"><b>Live today:</b><br/>Brinkadata – Property Intelligence</div>
      <ul class="small" style="margin-top:0.6rem;">
        <li>Deal grades (A–F)</li>
        <li>NOI, cap rate, cash-on-cash, DSCR</li>
        <li>Flip & BRRRR metrics (ARV / holding costs / velocity)</li>
        <li>Saved portfolio view + deal highlights</li>
        <li>AI summaries tuned to investor profile</li>
      </ul>
    </div>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

# ---------- Deep-link buttons ----------
c1, c2, c3, c4 = st.columns([1.1, 1.1, 1.1, 2.0])
with c1:
    st.link_button("Analyze a Deal (Rental)", f"{ANALYZER_URL}/?preset=rental")
with c2:
    st.link_button("Analyze a Deal (Flip)", f"{ANALYZER_URL}/?preset=flip")
with c3:
    st.link_button("Analyze a Deal (BRRRR)", f"{ANALYZER_URL}/?preset=brrrr")
with c4:
    st.markdown(f"[See how it works →](#how-it-works)")

st.caption("Built by an analyst for data-driven investors — designed to grow into a full property + business intelligence platform.")

st.markdown("## The Brinkadata Platform")
st.write("A growing suite of intelligence modules for underwriting, projects, operations, and market scouting.")

st.markdown(
    """
<div class="card-row">
  <div class="pcard">
    <span class="badge-live">LIVE</span>
    <h4>Brinkadata – Property Intelligence</h4>
    <p>Real estate underwriting & deal intelligence: grades, KPIs, flip/BRRRR metrics, portfolio views, and AI summaries.</p>
  </div>
  <div class="pcard">
    <span class="badge-soon">COMING SOON</span>
    <h4>Brinkadata – Project Intelligence</h4>
    <p>Project task and cost tracking for rehabs and capital projects, with timelines, budgets, and progress dashboards.</p>
  </div>
  <div class="pcard">
    <span class="badge-soon">COMING SOON</span>
    <h4>Brinkadata – Operations Intelligence</h4>
    <p>Property management analytics: collections, expenses, and efficiency insights across units, properties, and portfolios.</p>
  </div>
  <div class="pcard">
    <span class="badge-soon">COMING SOON</span>
    <h4>Brinkadata – Search Intelligence</h4>
    <p>Market and deal scouting: filters, watchlists, and saved searches to help you identify promising markets and properties faster.</p>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

st.markdown(
    """
<a id="how-it-works"></a>
## How Brinkadata – Property Intelligence Works
""",
    unsafe_allow_html=True,
)

st.markdown(
    """
**1) Enter the deal**  
Label the property, add city and state, and plug in your purchase price, rehab budget, rent, hold period, and strategy.

**2) Let Brinkadata analyze it**  
Behind the scenes, Brinkadata calculates NOI, cap rate, cash-on-cash, DSCR, break-even occupancy, flip profit / velocity, and more — then wraps it in an AI summary that matches your investor profile.

**3) Save, filter, and compare**  
Save deals to your portfolio, filter by grade / strategy / ROI, compare deals side-by-side, and load a deal back into the analyzer to iterate.
"""
)

st.markdown("## Where Brinkadata Is Going")
st.write("Brinkadata starts with Property Intelligence, but the long-term vision is a modular platform for your entire investing and operations stack.")

colA, colB = st.columns(2)
with colA:
    st.markdown("**Near-term focus**")
    st.markdown(
        """
- Deepen Brinkadata – Property Intelligence  
- Add Project Intelligence for rehabs & CapEx  
- Add Operations Intelligence for property management analytics  
- Add Search Intelligence for market and deal scouting  
"""
    )
with colB:
    st.markdown("**Future concept verticals**")
    st.markdown(
        """
- Brinkadata – Finance  
- Brinkadata – Energy  
- Brinkadata – Transport  
"""
    )
    st.caption("As the core stabilizes, these modules can extend the same “Brinkadata mindset” into other parts of your business and portfolio.")

st.markdown("---")
st.markdown("## Ready to see your next deal in a new light?")
st.write("Use Brinkadata – Property Intelligence to turn raw numbers into a decision-ready story in just a few minutes.")

st.link_button("Launch Analyzer", f"{ANALYZER_URL}/?preset=rental")

st.markdown(
    """
<div class="footer small">
Brinkadata is an educational analytics tool and does not provide legal, tax, or investment advice. Always verify numbers with your own professionals before making investment decisions.
<br/><br/>
© Brinkadata — All rights reserved.
</div>
""",
    unsafe_allow_html=True,
)
