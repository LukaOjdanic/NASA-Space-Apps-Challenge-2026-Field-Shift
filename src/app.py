"""
RowShift — Field Shift for the vineyard: rotate the alley, not the vine.
NASA Space Apps Challenge 2026 · Podgorica local event · Ćemovsko polje

Run from the repo root:
    uv add streamlit plotly pandas numpy requests folium streamlit-folium
    uv run streamlit run app.py

The app reads only data/. When the AppEEARS SMAP CSV lands in data/
(name it smap_l4.csv, or anything containing "SMAP"), it is detected
automatically on the next rerun — or press "Refresh data" in the sidebar.
"""
from __future__ import annotations

import html
import inspect
import json
import os
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
os.chdir(ROOT)  # score.py / indicators.py resolve data/ relative to cwd
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
DATA.mkdir(exist_ok=True)

# ---------------------------------------------------------------- palette
C = {
    "bg": "#160d18", "surface": "#221427", "surface2": "#2b1a31", "line": "#3d2a44",
    "ink": "#f3e9dc", "muted": "#b9a8c4", "leaf": "#8fbf6a", "water": "#5aa7d6",
    "heat": "#f2a541", "danger": "#e4572e", "wine": "#a2456e", "gold": "#d9a441",
    "clover": "#c65b8a", "violet": "#b48ede",
}
CRITERIA = [
    ("vine_water", "Vine water", C["water"], "💧"),
    ("erosion", "Erosion control", C["gold"], "🛡️"),
    ("fertility", "Fertility · N+OM", C["leaf"], "🌿"),
    ("heat", "Heat buffering", C["danger"], "🌡️"),
    ("labor", "Labor & cost", C["violet"], "🧺"),
]
STRAT = {
    "bare":   {"color": C["gold"],   "icon": "🟫"},
    "grass":  {"color": C["leaf"],   "icon": "🌾"},
    "legume": {"color": C["clover"], "icon": "🌸"},
}
PERSONAS = {
    "💧 Water-first": {"w_water": 5, "w_erosion": 1, "w_fertility": 1, "w_heat": 0, "w_labor": 1},
    "🌱 Soil-first":  {"w_water": 1, "w_erosion": 5, "w_fertility": 4, "w_heat": 2, "w_labor": 0},
    "⚖️ Balanced":    {"w_water": 3, "w_erosion": 3, "w_fertility": 2, "w_heat": 1, "w_labor": 1},
}
DEFAULT_W = PERSONAS["⚖️ Balanced"]
WKEY = {"vine_water": "w_water", "erosion": "w_erosion", "fertility": "w_fertility",
        "heat": "w_heat", "labor": "w_labor"}

STRATEGIES_DEFAULT = """id,label,summer_water_use,summer_cover,winter_cover,n_fix_low,n_fix_high,om_input,erosion_c,heat_buffer,labor_passes,establish_cost,termination_doy,main_benefit,main_risk,key_assumption
bare,"Bare cultivated alley (current)",0,0.0,0.0,0,0,0,0.35,0,4,0,,"No water competition with vines; familiar management","Winter-storm erosion on bare ground; no N or organic-matter input; hot bare surface","Tillage keeps alley bare year-round (3-5 passes/yr)"
grass,"Permanent resident grass",3,0.9,0.9,0,0,3,0.03,2,3,1,,"Strong erosion control; organic matter; cooler alley surface","Season-long water competition with vines on shallow soil in dry summers","Cover kept year-round; mown 2-4 times/yr; no irrigation assumed"
legume,"Winter legume then summer mulch",0,0.2,0.9,20,60,2,0.10,1,2,2,135,"Winter erosion control + free nitrogen; avoids summer water competition","Establishment cost; late termination in wet springs still costs water; N range uncertain","Subterranean clover/medic self-reseeds; terminated ~15 May or natural summer die-back"
"""

FALLBACK = {
    "hot_days_ripening": 42, "hot_days_flowering": 6, "warm_nights_ripening": 49,
    "dry_spell_days": 45, "winter_storm_days": 21, "smap_pct": 50.0, "smap_date": None,
    "awc_mm": 50.5, "soc_g_kg": 68.0,
    "meta": {"year": 2026, "power_file": "POWER_Point_Daily_19900101_20261113_042d38N_019d28E_LST.csv",
             "rooting_depth_cm": 30, "gaps": [
                 "Showing the cached Nov-15 indicator snapshot (live compute unavailable).",
                 "Elevation adjustment: POWER grid mean 933 m vs vineyard ~50 m; +5.7 C applied (lapse 6.5 C/km).",
                 "SMAP file not present; neutral percentile (50) assumed.",
                 "SoilGrids 250 m grid under-resolves karst; local soils likely shallower/stonier."],
             "sources": ["NASA POWER daily (AG; PRECTOTCORR = GPM IMERG-corrected)",
                         "SMAP L4 root-zone soil moisture (pending)", "ISRIC SoilGrids v2"]},
}

# ---------------------------------------------------------------- setup
st.set_page_config(page_title="RowShift · Ćemovsko polje", page_icon="🍇", layout="wide")

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600;9..144,700&family=Inter:wght@400;500;600&family=IBM+Plex+Mono:wght@500;600&display=swap');
:root{--bg:#160d18;--s1:#221427;--s2:#2b1a31;--line:#3d2a44;--ink:#f3e9dc;--mut:#b9a8c4;
--leaf:#8fbf6a;--water:#5aa7d6;--heat:#f2a541;--danger:#e4572e;--wine:#a2456e;--gold:#d9a441;--clover:#c65b8a;--violet:#b48ede;}
html,body,[class*="css"]{font-family:'Inter',system-ui,sans-serif;}
.stApp{background:
 radial-gradient(1100px 700px at 88% -12%, rgba(162,69,110,.28), transparent 60%),
 radial-gradient(900px 650px at -8% 108%, rgba(90,167,214,.14), transparent 55%),
 radial-gradient(700px 500px at 55% 115%, rgba(143,191,106,.08), transparent 60%),
 linear-gradient(160deg,#1c1022 0%,#160d18 55%,#110a13 100%);color:var(--ink);}
.stApp::before{content:'';position:fixed;inset:0;pointer-events:none;z-index:0;opacity:.045;
 background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2'/%3E%3C/filter%3E%3Crect width='140' height='140' filter='url(%23n)' opacity='0.6'/%3E%3C/svg%3E");}
#MainMenu,footer,[data-testid="stToolbarActions"],[data-testid="stAppDeployButton"],[data-testid="stStatusWidget"]{visibility:hidden;display:none;}
[data-testid="stExpandSidebarButton"],[data-testid="stSidebarCollapsedControl"],[data-testid="collapsedControl"]{display:flex!important;visibility:visible!important;color:#f3e9dc!important;}header[data-testid="stHeader"]{background:transparent;}
.block-container{padding-top:1.2rem;padding-bottom:3rem;max-width:1280px;position:relative;z-index:1;}
section[data-testid="stSidebar"]{background:linear-gradient(180deg,#1d1122,#170e1b);border-right:1px solid var(--line);}
section[data-testid="stSidebar"] *{scrollbar-color:#6d3b57 #170e1b;}
*{scrollbar-width:thin;scrollbar-color:#6d3b57 #170e1b;}
*::-webkit-scrollbar{width:10px;height:10px;}
*::-webkit-scrollbar-track{background:#170e1b;}
*::-webkit-scrollbar-thumb{background:linear-gradient(180deg,#6d3b57,#3d2a44);border-radius:8px;border:2px solid #170e1b;}
*::-webkit-scrollbar-thumb:hover{background:linear-gradient(180deg,var(--wine),#6d3b57);}
@keyframes rise{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
@keyframes grow{from{transform:scaleX(0)}to{transform:scaleX(1)}}
.rs-hero{animation:rise .5s ease both;margin-bottom:.6rem;}
.rs-kicker{font-size:.72rem;letter-spacing:.28em;color:var(--mut);font-weight:600;}
.rs-title{font-family:'Fraunces',serif;font-size:3.4rem;line-height:1.05;font-weight:700;margin:.15rem 0;}
.rs-title span{background:linear-gradient(92deg,var(--heat),var(--wine) 70%,var(--clover));-webkit-background-clip:text;background-clip:text;color:transparent;}
.rs-sub{color:var(--mut);max-width:760px;font-size:.98rem;margin-bottom:.7rem;}
.rs-pills{display:flex;flex-wrap:wrap;gap:.4rem;}
.pill{font-size:.72rem;font-weight:600;padding:.22rem .6rem;border-radius:999px;border:1px solid var(--line);background:rgba(43,26,49,.7);color:var(--mut);}
.pill.ok{color:var(--leaf);border-color:rgba(143,191,106,.4);}
.pill.warn{color:var(--heat);border-color:rgba(242,165,65,.45);}
.pill.info{color:var(--water);border-color:rgba(90,167,214,.4);}
.tile{background:linear-gradient(180deg,var(--s1),var(--s2));border:1px solid var(--line);border-radius:14px;
 padding:.75rem .9rem;animation:rise .45s ease both;height:100%;}
.tile .tl{font-size:.68rem;letter-spacing:.08em;text-transform:uppercase;color:var(--mut);font-weight:600;}
.tile .tv{font-family:'IBM Plex Mono',monospace;font-size:1.75rem;font-weight:600;margin:.15rem 0;}
.tile .tv small{font-size:.85rem;color:var(--mut);font-weight:500;margin-left:.2rem;}
.tile .td{font-size:.72rem;color:var(--mut);}
.leader{border:1px solid var(--line);border-left:4px solid var(--sc,var(--gold));border-radius:12px;
 background:linear-gradient(90deg,rgba(43,26,49,.9),rgba(34,20,39,.6));padding:.7rem 1rem;margin:.9rem 0;
 animation:rise .4s ease both;font-size:.95rem;}
.leader .lm{color:var(--mut);font-size:.78rem;margin-left:.6rem;}
.rs-h{display:flex;align-items:center;gap:.7rem;margin:1.1rem 0 .6rem;font-weight:600;letter-spacing:.06em;
 text-transform:uppercase;font-size:.78rem;color:var(--mut);}
.rs-h::after{content:'';flex:1;height:1px;background:linear-gradient(90deg,var(--wine),transparent);}
.scard{background:linear-gradient(180deg,var(--s1),var(--s2));border:1px solid var(--line);border-top:3px solid var(--sc);
 border-radius:16px;padding:1rem 1.05rem;height:100%;animation:rise .5s ease both;}
.sc-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:.35rem;}
.sc-rank{font-size:.68rem;font-weight:700;letter-spacing:.08em;padding:.18rem .55rem;border-radius:999px;
 background:rgba(61,42,68,.8);color:var(--mut);}
.sc-rank.r1{background:linear-gradient(90deg,var(--gold),var(--heat));color:#241326;}
.sc-delta{font-family:'IBM Plex Mono',monospace;font-size:.72rem;color:var(--mut);}
.sc-delta.up{color:var(--leaf);} .sc-delta.down{color:var(--danger);}
.sc-name{font-weight:600;font-size:.95rem;min-height:2.4em;}
.sc-score{font-family:'Fraunces',serif;font-size:2.6rem;font-weight:700;color:var(--sc);line-height:1.1;}
.sc-score span{font-size:.9rem;color:var(--mut);font-family:'Inter',sans-serif;font-weight:500;}
.bar-row{display:flex;align-items:center;gap:.5rem;margin:.28rem 0;}
.bar-l{font-size:.68rem;color:var(--mut);width:88px;flex-shrink:0;}
.bar-track{flex:1;height:7px;border-radius:6px;background:rgba(61,42,68,.7);overflow:hidden;}
.bar-fill{height:100%;border-radius:6px;transform-origin:left;animation:grow .6s ease both;}
.bar-v{font-family:'IBM Plex Mono',monospace;font-size:.68rem;width:26px;text-align:right;color:var(--ink);}
.sc-txt{font-size:.76rem;margin-top:.5rem;line-height:1.35;}
.sc-txt.b{color:var(--leaf);} .sc-txt.r{color:var(--heat);} .sc-txt.a{color:var(--mut);font-style:italic;}
.gap{border:1px solid var(--line);border-radius:10px;padding:.55rem .8rem;margin:.35rem 0;font-size:.8rem;
 background:rgba(34,20,39,.6);animation:rise .4s ease both;}
.gap.warn{border-left:3px solid var(--heat);} .gap.info{border-left:3px solid var(--water);}
.rs-note{border:1px dashed var(--line);border-radius:12px;padding:.8rem 1rem;color:var(--mut);font-size:.85rem;
 background:rgba(34,20,39,.5);}
.rs-note b{color:var(--heat);}
table.rs-table{width:100%;border-collapse:collapse;font-size:.78rem;}
table.rs-table th{color:var(--mut);text-transform:uppercase;letter-spacing:.06em;font-size:.66rem;text-align:left;
 padding:.4rem .6rem;border-bottom:1px solid var(--line);}
table.rs-table td{padding:.4rem .6rem;border-bottom:1px solid rgba(61,42,68,.5);vertical-align:top;}
table.rs-table tr:hover td{background:rgba(162,69,110,.08);}
.kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.5rem;}
.kv .tile .tv{font-size:1.25rem;}
.rs-foot{margin-top:2rem;padding-top:1rem;border-top:1px solid var(--line);color:var(--mut);font-size:.72rem;line-height:1.5;}
.stTabs [data-baseweb="tab-list"]{gap:.2rem;border-bottom:1px solid var(--line);}
.stTabs [data-baseweb="tab"]{color:var(--mut);font-weight:600;font-size:.85rem;background:transparent;}
.stTabs [aria-selected="true"]{color:var(--ink);}
.stTabs [data-baseweb="tab-highlight"]{background:linear-gradient(90deg,var(--heat),var(--wine));height:3px;}
.stTabs [data-baseweb="tab-border"]{background:var(--line);}
.stButton>button{background:linear-gradient(135deg,#3a2140,#2b1a31);border:1px solid var(--line);color:var(--ink);
 border-radius:10px;font-weight:600;font-size:.8rem;transition:all .15s ease;}
.stButton>button:hover{border-color:var(--wine);transform:translateY(-1px);box-shadow:0 4px 14px rgba(162,69,110,.25);}
div[data-baseweb="slider"] [role="slider"]{background:var(--gold);box-shadow:0 0 0 4px rgba(217,164,65,.15);}
.stSelectbox [data-baseweb="select"]>div,.stNumberInput [data-baseweb="input"]>div{background:var(--s2);border-color:var(--line);}
[data-testid="stExpander"]{border:1px solid var(--line);border-radius:12px;background:rgba(34,20,39,.5);}
.stCodeBlock{border:1px solid var(--line);border-radius:12px;}
@media (max-width:900px){.rs-title{font-size:2.4rem;}.tile .tv{font-size:1.3rem;}.bar-l{width:70px;}}
"""
st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)

# ---------------------------------------------------------------- helpers
def esc(x): return html.escape(str(x))

def newest(*patterns):
    files = [p for pat in patterns for p in DATA.glob(pat)]
    return max(files, key=lambda p: p.stat().st_mtime) if files else None

def sig(p): return (p.name, p.stat().st_mtime) if p else None

def wide_kwargs(fn):
    return {"width": "stretch"} if "width" in inspect.signature(fn).parameters else {"use_container_width": True}

def show_fig(fig, **kw):
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(family="Inter", color=C["ink"], size=12),
                      margin=dict(l=10, r=10, t=30, b=10),
                      legend=dict(orientation="h", y=1.12, x=0, font=dict(size=11)))
    st.plotly_chart(fig, config={"displayModeBar": False}, **wide_kwargs(st.plotly_chart), **kw)

def table_html(df):
    head = "".join(f"<th>{esc(c)}</th>" for c in df.columns)
    rows = "".join("<tr>" + "".join(f"<td>{esc(v)}</td>" for v in r) + "</tr>"
                   for r in df.itertuples(index=False, name=None))
    return f'<table class="rs-table"><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>'

def tile(icon, label, value, unit="", sub="", color=None):
    col = f' style="color:{color}"' if color else ""
    return (f'<div class="tile"><div class="tl">{icon} {esc(label)}</div>'
            f'<div class="tv"{col}>{esc(value)}<small>{esc(unit)}</small></div>'
            f'<div class="td">{sub}</div></div>')

def section(title):
    st.markdown(f'<div class="rs-h"><span>{esc(title)}</span></div>', unsafe_allow_html=True)

# ---------------------------------------------------------------- data layer
if not (DATA / "strategies.csv").exists():
    (DATA / "strategies.csv").write_text(STRATEGIES_DEFAULT.strip() + "\n")
STRATS = pd.read_csv(DATA / "strategies.csv").set_index("id")

try:
    import scoring as score_mod
    score_fn, SCORE_SRC = score_mod.score, "src/score.py"
except Exception:
    SCORE_SRC = "embedded fallback (src/score.py not importable)"
    def score_fn(sid, i, w):
        s = STRATS.loc[sid]
        d = 1.0 + 0.2 * min(i["dry_spell_days"] / 40, 1)
        d += 0.2 * (1 - i["smap_pct"] / 100) - 0.2 * min(i["awc_mm"] / 120, 1)
        d = max(0.6, min(1.4, d))
        storm = min(i["winter_storm_days"] / 8, 1)
        heat = min(i["hot_days_ripening"] / 25, 1)
        lowC = 1 - min(i["soc_g_kg"] / 40, 1)
        o = {"vine_water": 100 - s["summer_water_use"] * 25 * d,
             "erosion": 100 * (1 - s["erosion_c"] / 0.35) * (0.4 + 0.6 * storm),
             "fertility": 100 * (0.5 * s["om_input"] / 3 + 0.5 * min(s["n_fix_high"] / 60, 1)) * (0.6 + 0.4 * lowC),
             "heat": 100 * (s["heat_buffer"] / 2) * (0.4 + 0.6 * heat),
             "labor": 100 * (1 - s["labor_passes"] / 5)}
        o = {k: round(max(0, min(100, v)), 1) for k, v in o.items()}
        o["total"] = round(sum(w[k] * o[k] for k in w) / max(sum(w.values()), 1e-9), 1)
        return o

POWER_FILE = newest("POWER*.csv", "power*.csv")
SMAP_FILE = newest("*SMAP*.csv", "*smap*.csv", "*SPL4SMGP*.csv")

@st.cache_data(show_spinner=False)
def get_indicators(year, depth, soc, elev, psig, ssig):
    try:
        import indicators as im
        im.APPLY_ELEV_ADJUST = elev
        ind = im.compute_indicators(year=year, rooting_depth_cm=depth, soc_override=soc)
        (DATA / "indicators.json").write_text(json.dumps(ind, indent=2, default=str))
        return ind, "live"
    except Exception as e:
        if (DATA / "indicators.json").exists():
            ind = json.loads((DATA / "indicators.json").read_text())
            ind.setdefault("meta", {}).setdefault("gaps", []).append(f"Live recompute unavailable ({e}); using cached indicators.json.")
            return ind, "cached"
        fb = json.loads(json.dumps(FALLBACK))
        fb["meta"]["gaps"].insert(0, f"Live compute unavailable ({e}); showing the Nov-15 snapshot.")
        return fb, "snapshot"

def load_daily(year):
    p = DATA / f"daily_{year}.csv"
    if not p.exists(): return None
    d = pd.read_csv(p, parse_dates=["date"]).set_index("date").sort_index()
    return d

def load_yearly():
    p = DATA / "yearly_summary.csv"
    return pd.read_csv(p) if p.exists() else None

# ---------------------------------------------------------------- sidebar
for k, v in DEFAULT_W.items():
    st.session_state.setdefault(k, v)

with st.sidebar:
    st.markdown('<div class="rs-kicker">ROWSHIFT · GROWER CONSOLE</div>', unsafe_allow_html=True)
    st.markdown("### 🍇 Priorities")
    st.caption("Same NASA evidence, different priorities → different answer. The grower decides.")
    pcols = st.columns(3)
    def set_persona(name):
        for k, v in PERSONAS[name].items(): st.session_state[k] = v
    for col, name in zip(pcols, PERSONAS):
        col.button(name.split(" ")[1], key=f"p_{name}", on_click=set_persona, args=(name,), **wide_kwargs(st.button))
    for key, label, _, icon in CRITERIA:
        st.slider(f"{icon} {label}", 0, 5, key=WKEY[key],
                  help="0 = ignore this priority · 5 = decisive")
    st.markdown("---")
    st.markdown("### 🗓️ Site & season")
    yearly0 = load_yearly()
    years = sorted(yearly0["year"].astype(int).tolist()) if yearly0 is not None else list(range(1990, 2027))
    cached_meta = {}
    if (DATA / "indicators.json").exists():
        try: cached_meta = json.loads((DATA / "indicators.json").read_text()).get("meta", {})
        except Exception: pass
    default_year = cached_meta.get("year", years[-1])
    if default_year not in years: years.append(default_year); years.sort()
    year = st.selectbox("Season", years, index=years.index(default_year))
    depth = st.select_slider("Rooting depth (cm)", options=[30, 60, 100], value=30,
                             help="Vines on karst exploit deep fissures; SoilGrids only sees the grid's layers.")
    soc_on = st.toggle("Lab SOC override", value=False, help="SoilGrids says 68 g/kg — suspiciously rich for karst. Override with a lab value.")
    soc_val = st.number_input("Measured SOC (g/kg)", 1.0, 120.0, 15.0, 0.5, disabled=not soc_on)
    elev = st.toggle("Lapse-rate elevation correction", value=True,
                     help="POWER grid mean 933 m vs vineyard ~50 m → +5.7 °C. First-order downscaling; raw values kept.")
    if st.button("🔄 Refresh data (pick up new SMAP / POWER files)", **wide_kwargs(st.button)):
        st.cache_data.clear(); st.rerun()
    with st.expander("📁 Data status"):
        checks = [("POWER daily", POWER_FILE), ("SMAP L4", SMAP_FILE),
                  ("indicators.json", DATA / "indicators.json" if (DATA / "indicators.json").exists() else None),
                  ("soil_constants.json", DATA / "soil_constants.json" if (DATA / "soil_constants.json").exists() else None),
                  ("strategies.csv", DATA / "strategies.csv"),
                  ("yearly_summary.csv", DATA / "yearly_summary.csv" if (DATA / "yearly_summary.csv").exists() else None),
                  (f"daily_{year}.csv", DATA / f"daily_{year}.csv" if (DATA / f"daily_{year}.csv").exists() else None),
                  ("blocks.geojson", DATA / "blocks.geojson" if (DATA / "blocks.geojson").exists() else None),
                  ("sources.csv", DATA / "sources.csv" if (DATA / "sources.csv").exists() else None)]
        for name, p in checks:
            mark = "✓" if p else "—"
            cls = "ok" if p else "warn"
            st.markdown(f'<span class="pill {cls}">{mark} {esc(name)}</span>', unsafe_allow_html=True)
        st.caption(f"Scoring: {SCORE_SRC}")
    st.caption("Rotate the alley, not the vine. Evidence, trade-offs and gaps — never a verdict.")

weights = {k: st.session_state[WKEY[k]] for k, *_ in CRITERIA}
ind, MODE = get_indicators(year, depth, soc_val if soc_on else None, elev, sig(POWER_FILE), sig(SMAP_FILE))
meta = ind.get("meta", {})
daily = load_daily(year)
yearly = load_yearly()

# ---------------------------------------------------------------- hero + tiles
smap_live = ind.get("smap_date") is not None
pills = [
    f'<span class="pill ok">POWER ✓ {esc(meta.get("power_file", "")[:34])}…</span>',
    f'<span class="pill {"ok" if smap_live else "warn"}">SMAP {"✓ " + esc(ind["smap_date"]) if smap_live else "⚠ neutral 50 assumed"}</span>',
    f'<span class="pill info">SoilGrids ✓ AWC {ind["awc_mm"]} mm</span>',
    f'<span class="pill {"ok" if elev else "warn"}">Elevation corr. {"on (+5.7 °C)" if elev else "off (raw grid)"}</span>',
    f'<span class="pill">Season {esc(year)}</span>',
    f'<span class="pill {"ok" if MODE == "live" else "warn"}">indicators: {MODE}</span>',
]
st.markdown(f"""
<div class="rs-hero">
  <div class="rs-kicker">NASA SPACE APPS 2026 · FIELD SHIFT · PODGORICA</div>
  <div class="rs-title">Row<span>Shift</span></div>
  <div class="rs-sub">Rotate the alley, not the vine — a heat &amp; water trade-off lens for Ćemovsko polje,
  Europe's largest contiguous vineyard. Three inter-row rotations, scored live against NASA evidence and your priorities.</div>
  <div class="rs-pills">{''.join(pills)}</div>
</div>""", unsafe_allow_html=True)

tiles = [
    tile("🌡️", "Hot days · ripening", ind["hot_days_ripening"], " d", f"Jul–Aug ≥35 °C · flowering: {ind.get('hot_days_flowering', '—')} d", C["danger"]),
    tile("🌙", "Warm nights", ind.get("warm_nights_ripening", "—"), " d", "Jul–Aug Tmin ≥20 °C · color/aroma risk", C["clover"]),
    tile("🏜️", "Longest dry spell", ind["dry_spell_days"], " d", "Apr–Sep, rain <1 mm/day", C["heat"]),
    tile("⛈️", "Winter storm days", ind["winter_storm_days"], " d", f"Nov {year-1}–Feb {year} ≥20 mm · erosion driver", C["water"]),
    tile("🛰️", "SMAP moisture", f'{ind["smap_pct"]:.0f}', " pctl", "live root-zone" if smap_live else "assumed · awaiting AppEEARS", C["water"] if smap_live else C["heat"]),
    tile("🪣", "Available water", ind["awc_mm"], " mm", f"top {depth} cm · stone-corrected · karst caveat", C["leaf"]),
]
cols = st.columns(6)
for col, t in zip(cols, tiles):
    col.markdown(t, unsafe_allow_html=True)

# ---------------------------------------------------------------- scoring
results = {sid: score_fn(sid, ind, weights) for sid in STRATS.index}
order = sorted(results, key=lambda s: results[s]["total"], reverse=True)
prev = st.session_state.get("prev_totals", {})
leader = order[0]
lmeta = STRAT.get(leader, {"color": C["gold"], "icon": "•"})
if prev and st.session_state.get("prev_leader") not in (None, leader) and hasattr(st, "toast"):
    st.toast(f"Leader changed → {STRATS.loc[leader, 'label']}", icon="🔁")
st.session_state["prev_totals"] = {s: results[s]["total"] for s in results}
st.session_state["prev_leader"] = leader

if sum(weights.values()) == 0:
    st.markdown('<div class="rs-note">All priorities are zero — move a slider or pick a persona to rank the rotations.</div>', unsafe_allow_html=True)
else:
    st.markdown(f'<div class="leader" style="--sc:{lmeta["color"]}">👑 Best fit for your priorities: '
                f'<b>{esc(STRATS.loc[leader, "label"])}</b> · {results[leader]["total"]}/100 '
                f'<span class="lm">trade-offs, not a verdict — verify locally with an agronomist</span></div>',
                unsafe_allow_html=True)

tab_compare, tab_evidence, tab_map, tab_gaps = st.tabs(
    ["⚖️ Compare rotations", "📅 Heat & water evidence", "🗺️ Block map", "🔎 Evidence, gaps & sources"])

# ---------------------------------------------------------------- tab 1: compare
with tab_compare:
    section("Three inter-row rotations · ranked for your weights")
    cols = st.columns(3)
    for rank, (col, sid) in enumerate(zip(cols, order), start=1):
        r = results[sid]; s = STRATS.loc[sid]; m = STRAT.get(sid, {"color": C["muted"], "icon": "•"})
        delta = r["total"] - prev.get(sid, r["total"])
        dcls = "up" if delta > 0.05 else ("down" if delta < -0.05 else "")
        dtxt = f'{"▲" if delta > 0 else "▼"} {delta:+.1f}' if dcls else "· baseline"
        bars = "".join(
            f'<div class="bar-row"><span class="bar-l">{esc(label)}</span>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{max(0, min(100, r[key]))}%;background:{cc}"></div></div>'
            f'<span class="bar-v">{r[key]:.0f}</span></div>'
            for key, label, cc, _ in CRITERIA)
        rank_txt = "#1 · BEST FIT" if rank == 1 else f"#{rank}"
        col.markdown(f"""
<div class="scard" style="--sc:{m['color']}">
  <div class="sc-top"><span class="sc-rank {'r1' if rank == 1 else ''}">{rank_txt}</span><span class="sc-delta {dcls}">{dtxt}</span></div>
  <div class="sc-name">{m['icon']} {esc(s['label'])}</div>
  <div class="sc-score">{r['total']}<span> /100</span></div>
  {bars}
  <div class="sc-txt b">✔ {esc(s.get('main_benefit', ''))}</div>
  <div class="sc-txt r">⚠ {esc(s.get('main_risk', ''))}</div>
  <div class="sc-txt a">Assumes: {esc(s.get('key_assumption', ''))}</div>
</div>""", unsafe_allow_html=True)

    section("Trade-off fingerprint")
    try:
        import plotly.graph_objects as go
        fig = go.Figure()
        theta = [label for _, label, _, _ in CRITERIA]
        for sid in STRATS.index:
            m = STRAT.get(sid, {"color": C["muted"]})
            vals = [results[sid][k] for k, *_ in CRITERIA]
            fig.add_trace(go.Scatterpolar(r=vals + vals[:1], theta=theta + theta[:1], fill="toself",
                                          name=str(STRATS.loc[sid, "label"]), line=dict(color=m["color"], width=2),
                                          fillcolor=m["color"] + "22"))
        fig.update_layout(height=430, polar=dict(bgcolor="rgba(0,0,0,0)",
                          radialaxis=dict(range=[0, 100], gridcolor=C["line"], tickfont=dict(color=C["muted"], size=10), linecolor=C["line"]),
                          angularaxis=dict(gridcolor=C["line"], linecolor=C["line"], tickfont=dict(size=11))))
        show_fig(fig)
    except Exception as e:
        st.markdown(f'<div class="rs-note">Radar chart unavailable ({esc(e)}). The score bars above carry the same information.</div>', unsafe_allow_html=True)
    st.markdown('<div class="rs-note">🔬 <b>Sensitivity:</b> toggle the elevation correction or the lab-SOC override in the sidebar and watch the ranking respond — '
                'the two assumptions the grid data is weakest on. Water-first keeps vines safe; soil-first accepts summer competition for erosion and organic-matter gains.</div>',
                unsafe_allow_html=True)

# ---------------------------------------------------------------- tab 2: heat & water
with tab_evidence:
    section(f"Daily maximum temperature · {year}")
    if daily is not None and "tmax_c" in daily:
        try:
            import plotly.graph_objects as go
            d = daily.copy()
            d["wd"] = d.index.dayofweek
            d["wk"] = (d.index.dayofyear - 1) // 7
            d["lbl"] = d.index.strftime("%a %d %b")
            z = d.pivot(index="wd", columns="wk", values="tmax_c").reindex(index=range(7), columns=range(53))
            ht = d.pivot(index="wd", columns="wk", values="lbl").reindex(index=range(7), columns=range(53)).fillna("")
            months = pd.date_range(f"{year}-01-01", f"{year}-12-01", freq="MS")
            tickvals = [(m.dayofyear - 1) // 7 for m in months]
            scale = [[0, "#3b2f63"], [0.25, C["water"]], [0.45, C["leaf"]], [0.65, C["gold"]],
                     [0.8, C["heat"]], [0.9, C["danger"]], [1, "#a2264b"]]
            fig = go.Figure(go.Heatmap(z=z.values, x=list(range(53)), y=list(range(7)), customdata=ht.values,
                                       hovertemplate="%{customdata}<br>Tmax %{z:.1f} °C<extra></extra>",
                                       colorscale=scale, zmin=0, zmax=42, xgap=1, ygap=2,
                                       colorbar=dict(title="°C", tickfont=dict(color=C["muted"]), outlinewidth=0)))
            for m0, m1, name, cc in [(5, 7, "flowering", C["leaf"]), (7, 9, "ripening", C["heat"])]:
                w0 = (pd.Timestamp(year, m0, 1).dayofyear - 1) // 7
                w1 = (pd.Timestamp(year, m1, 1).dayofyear - 1) // 7
                fig.add_vrect(x0=w0 - 0.5, x1=w1 - 0.5, fillcolor=cc, opacity=0.07, line_width=0)
                fig.add_annotation(x=(w0 + w1) / 2, y=6.9, text=name, showarrow=False,
                                   font=dict(size=10, color=cc), yanchor="bottom")
            fig.update_layout(height=320, xaxis=dict(tickvals=tickvals, ticktext=[m.strftime("%b") for m in months],
                              tickfont=dict(color=C["muted"]), showgrid=False, zeroline=False),
                              yaxis=dict(tickvals=list(range(7)), ticktext=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
                              tickfont=dict(color=C["muted"]), showgrid=False, autorange="reversed"))
            show_fig(fig)
        except Exception as e:
            st.markdown(f'<div class="rs-note">Calendar unavailable ({esc(e)}).</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="rs-note"><b>No daily file for {year}.</b> Run <code>uv run python src/indicators.py --year {year}</code> to generate <code>data/daily_{year}.csv</code>.</div>', unsafe_allow_html=True)

    section("The shift, 1990 → today")
    if yearly is not None and len(yearly) > 2:
        try:
            import plotly.graph_objects as go
            y = yearly.sort_values("year")
            fig = go.Figure()
            fig.add_trace(go.Bar(x=y["year"], y=y["hot_days_ripening"], name="Hot days · ripening",
                                 marker_color=C["heat"], marker_line_width=0, opacity=0.85))
            fig.add_trace(go.Scatter(x=y["year"], y=y["hot_days_flowering"], name="Hot days · flowering",
                                     mode="lines+markers", line=dict(color=C["clover"], width=2), marker=dict(size=4)))
            if len(y) >= 3:
                k, b = np.polyfit(y["year"], y["hot_days_ripening"], 1)
                fig.add_trace(go.Scatter(x=y["year"], y=k * y["year"] + b, name=f"trend {k:+.2f} d/yr",
                                         mode="lines", line=dict(color=C["ink"], width=1.5, dash="dot")))
            fig.add_trace(go.Scatter(x=y["year"], y=y["precip_total_mm"], name="Annual rain (mm)", yaxis="y2",
                                     mode="lines", line=dict(color=C["water"], width=1.5, dash="dash")))
            fig.update_layout(height=360, barmode="overlay",
                              xaxis=dict(gridcolor=C["line"], tickfont=dict(color=C["muted"])),
                              yaxis=dict(title="days ≥35 °C", gridcolor=C["line"], tickfont=dict(color=C["muted"])),
                              yaxis2=dict(title="mm", overlaying="y", side="right", showgrid=False,
                                          tickfont=dict(color=C["water"])))
            show_fig(fig)
        except Exception as e:
            st.markdown(f'<div class="rs-note">Trend chart unavailable ({esc(e)}).</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="rs-note"><b>No yearly summary yet.</b> It is written by <code>src/indicators.py</code>.</div>', unsafe_allow_html=True)

    c1, c2 = st.columns([1, 1])
    with c1:
        section("Root-zone moisture · SMAP")
        if smap_live:
            try:
                import plotly.graph_objects as go
                fig = go.Figure(go.Indicator(mode="gauge+number", value=ind["smap_pct"],
                    number=dict(suffix=" pctl", font=dict(color=C["ink"], size=34)),
                    gauge=dict(axis=dict(range=[0, 100], tickfont=dict(color=C["muted"])),
                               bar=dict(color=C["water"], thickness=0.3), bgcolor="rgba(0,0,0,0)", borderwidth=0,
                               steps=[dict(range=[0, 25], color="rgba(228,87,46,.35)"),
                                      dict(range=[25, 50], color="rgba(242,165,65,.3)"),
                                      dict(range=[50, 100], color="rgba(90,167,214,.25)")],
                               threshold=dict(line=dict(color=C["ink"], width=3), value=ind["smap_pct"]))))
                fig.update_layout(height=250)
                show_fig(fig)
                st.caption(f"Observed {ind['smap_date']} · percentile vs same day-of-year ±15 d, 2015+ · 9 km pixel, not block-scale.")
            except Exception:
                st.metric("SMAP percentile", ind["smap_pct"])
        else:
            st.markdown('<div class="rs-note">🛰️ <b>SMAP pending.</b> Drop the AppEEARS SPL4SMGP point-sample CSV into <code>data/</code> '
                        '(e.g. <code>smap_l4.csv</code>) and press <b>Refresh data</b> — the percentile replaces the neutral 50 automatically. '
                        'Until then the water score runs on rainfall + soil bucket only, and this is declared as a gap.</div>', unsafe_allow_html=True)
    with c2:
        section("The soil bucket · SoilGrids")
        awc = float(ind["awc_mm"]); ref = 120.0; pct = max(2, min(100, awc / ref * 100))
        st.markdown(f"""
<div class="tile"><div class="tl">🪣 Plant-available water · top {depth} cm</div>
<div class="tv" style="color:{C['leaf']}">{awc:.1f}<small>mm</small></div>
<div class="bar-track" style="margin:.4rem 0"><div class="bar-fill" style="width:{pct}%;background:linear-gradient(90deg,{C['water']},{C['leaf']})"></div></div>
<div class="td">vs ~120 mm reference bucket · coarse-fragment corrected · SOC {ind['soc_g_kg']:.0f} g/kg {'(lab override)' if soc_on else '(grid — karst caveat)'}<br>
A small bucket is why permanent grass is risky here: it drinks from the same reserve as the vines.</div></div>""", unsafe_allow_html=True)

# ---------------------------------------------------------------- tab 3: map
with tab_map:
    section("Ćemovsko polje · the rotated field is the alley between vine rows")
    block_ll, power_ll = [42.37, 19.29], None
    mfile = meta.get("power_file", "")
    mm = re.search(r"(\d{3})d(\d{2})([NS])_(\d{3})d(\d{2})([EW])", mfile)
    if mm:
        power_ll = [int(mm[1]) + int(mm[2]) / 100, int(mm[4]) + int(mm[5]) / 100]
        if mm[3] == "S": power_ll[0] *= -1
        if mm[5] == "W": power_ll[1] *= -1
    try:
        import folium
        from streamlit_folium import st_folium
        fmap = folium.Map(location=block_ll, zoom_start=13, tiles=None)
        folium.TileLayer(tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                         attr="Esri World Imagery", name="Satellite").add_to(fmap)
        gj_path = DATA / "blocks.geojson"
        if gj_path.exists():
            gj = json.loads(gj_path.read_text())
            folium.GeoJson(gj, name="Vineyard blocks",
                           style_function=lambda f: {"color": C["clover"], "weight": 2, "fillColor": C["clover"], "fillOpacity": 0.18}).add_to(fmap)
        else:
            folium.Polygon([[42.367, 19.286], [42.367, 19.296], [42.374, 19.296], [42.374, 19.286]],
                           color=C["clover"], weight=2, fill=True, fill_opacity=0.18,
                           tooltip="Illustrative block — draw the real one at geojson.io → data/blocks.geojson").add_to(fmap)
        folium.CircleMarker(block_ll, radius=7, color=C["clover"], fill=True, fill_opacity=0.9,
                            tooltip="Block / soil centroid (42.37, 19.29)").add_to(fmap)
        if power_ll:
            folium.CircleMarker(power_ll, radius=7, color=C["water"], fill=True, fill_opacity=0.9,
                                tooltip=f"POWER grid point ({power_ll[0]:.2f}, {power_ll[1]:.2f}) — same MERRA-2 cell").add_to(fmap)
            folium.PolyLine([block_ll, power_ll], color=C["heat"], weight=2, dash_array="6 6",
                            tooltip="~5 km centroid offset — declared in gaps; values unchanged (same cell)").add_to(fmap)
        bounds = [block_ll] + ([power_ll] if power_ll else [])
        fmap.fit_bounds([[min(b[0] for b in bounds) - 0.015, min(b[1] for b in bounds) - 0.02],
                         [max(b[0] for b in bounds) + 0.015, max(b[1] for b in bounds) + 0.02]])
        st_folium(fmap, height=440, returned_objects=[], key="rs_map", **wide_kwargs(st_folium))
    except Exception as e:
        pts = pd.DataFrame({"lat": [block_ll[0]] + ([power_ll[0]] if power_ll else []),
                            "lon": [block_ll[1]] + ([power_ll[1]] if power_ll else [])})
        st.map(pts, zoom=12)
        st.caption(f"Satellite map unavailable ({e}) — showing centroids. Install folium + streamlit-folium for imagery.")
    st.markdown('<div class="rs-note">🍇 The vines stay for 30+ years; the <b>alley</b> is the field that rotates — bare soil → permanent grass → winter legume/summer mulch. '
                'Satellite pixels are coarser than a block: SMAP 9 km, POWER ~50 km, SoilGrids 250 m. Every number here is evidence for a conversation with the grower, not a field verdict.</div>',
                unsafe_allow_html=True)

# ---------------------------------------------------------------- tab 4: evidence & gaps
with tab_gaps:
    section("Assumptions & information gaps · the honesty layer")
    gaps = list(meta.get("gaps", []))
    if MODE != "live":
        gaps.insert(0, f"Indicator mode: {MODE}. Live compute runs when POWER data is importable; refresh after adding files.")
    if not smap_live:
        gaps.append("Decision impact of the SMAP gap: water-competition penalty uses rainfall + soil bucket only; a dry anomaly would strengthen the case against permanent grass.")
    for g in gaps:
        warn = any(k in g.lower() for k in ("not present", "differs", "under-resolves", "placeholder", "unavailable", "assumed", "override", "failed", "pending", "snapshot", "cached"))
        st.markdown(f'<div class="gap {"warn" if warn else "info"}">{"⚠️" if warn else "ℹ️"} {esc(g)}</div>', unsafe_allow_html=True)

    section("Rotation traits · the agronomy constants")
    trait_cols = [c for c in ["label", "summer_water_use", "winter_cover", "n_fix_low", "n_fix_high",
                              "erosion_c", "heat_buffer", "labor_passes", "termination_doy"] if c in STRATS.columns]
    st.markdown(table_html(STRATS[trait_cols].reset_index(drop=True)), unsafe_allow_html=True)
    st.caption("Ordinal scales 0–3 unless noted · erosion_c = USLE-style cover factor (lower = better) · n_fix in kg N/ha of covered alley · DOY 135 ≈ 15 May termination.")

    c1, c2 = st.columns(2)
    with c1:
        section("Soil constants")
        sc_path = DATA / "soil_constants.json"
        if sc_path.exists():
            sc = json.loads(sc_path.read_text())
            kv = [("AWC 0–30 cm", f"{sc.get('awc_0_30_mm', '—')} mm"), ("AWC 0–60 cm", f"{sc.get('awc_0_60_mm', '—')} mm"),
                  ("AWC 0–100 cm", f"{sc.get('awc_0_100_mm', '—')} mm"), ("SOC topsoil", f"{sc.get('soc_top_g_kg', '—')} g/kg"),
                  ("Texture 0–5", sc.get("texture_0_5cm", "—")), ("Stones 0–5", f"{sc.get('cfvo_0_5_pct', '—')} %")]
            st.markdown('<div class="kv">' + "".join(tile("🪨", k, v) for k, v in kv) + "</div>", unsafe_allow_html=True)
        else:
            st.markdown('<div class="rs-note">Run <code>src/fetch_soilgrids.py</code> to derive soil constants.</div>', unsafe_allow_html=True)
    with c2:
        section("Confidence register")
        src_path = DATA / "sources.csv"
        if src_path.exists():
            st.markdown(table_html(pd.read_csv(src_path)), unsafe_allow_html=True)
        else:
            st.markdown('<div class="rs-note">Add <code>data/sources.csv</code> (constant · source · confidence · note).</div>', unsafe_allow_html=True)

    section("Copy-ready for the submission form")
    nasa_text = (
        "NASA data used: (1) NASA POWER daily agroclimatology (MERRA-2 T2M_MAX/T2M_MIN/T2M; "
        "PRECTOTCORR precipitation, GPM IMERG-corrected in the satellite era) — heat calendar, dry spells, "
        "winter storm days, 1990–2026 trend, with a disclosed lapse-rate elevation adjustment. "
        "(2) SMAP L4 root-zone soil moisture via AppEEARS — day-of-year percentile anomaly "
        f"({'observed ' + str(ind['smap_date']) if smap_live else 'pending; neutral 50 assumed and declared as a gap'}). "
        "(3) ISRIC SoilGrids v2 (non-NASA soil layer) for available-water capacity and organic carbon, "
        "coarse-fragment corrected, with karst caveats. ECOSTRESS LST planned as an illustrative hot-block snapshot."
    )
    st.code(nasa_text, language="text")
    st.caption("References: FAO-56 (Allen et al. 1998) · Delpuech 2018 (cover-crop water competition × soil depth) · Novara 2021 (cover-crop water conservation) · "
               "USLE C-factor tables · MONTEVITIS / Fernandes et al. 2024 (Montenegrin viticulture under climate change). "
               "AI-assisted code disclosed per the Space Apps SI policy; no NASA branding in generated assets.")

st.markdown('<div class="rs-foot">RowShift · built solo at the Podgorica local event · NASA Space Apps Challenge 2026 · '
            'Data: NASA POWER · GPM IMERG · SMAP L4 · ISRIC SoilGrids · FAO-56 &amp; cover-crop literature · '
            'This tool frames trade-offs for a grower–agronomist conversation; it does not issue management verdicts.</div>',
            unsafe_allow_html=True)