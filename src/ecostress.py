"""src/ecostress.py -- clean the AppEEARS ECO_L2_LSTE point sample.
Run:  uv run python src/ecostress.py
In:   data/*LSTE*.csv | *ECOSTRESS*.csv | *ecostress*.csv   (raw AppEEARS export)
Out:  data/ecostress_lst.csv      clear-sky, good-quality observations, deg C, local time
      data/ecostress_summary.json counts + caveats for the evidence footer
"""
import json
from pathlib import Path
import pandas as pd

DATA = Path("data")
TZ = "Europe/Podgorica"

files = [p for pat in ("*LSTE*.csv", "*ECOSTRESS*.csv", "*ecostress*.csv")
         for p in DATA.glob(pat)]
if not files:
    raise FileNotFoundError("Put the AppEEARS ECOSTRESS CSV in data/ (name must contain LSTE or ECOSTRESS).")
src = max(files, key=lambda p: p.stat().st_mtime)
df = pd.read_csv(src)
df.columns = [c.strip() for c in df.columns]
low = {c.lower(): c for c in df.columns}

def find(*tokens, end=None):
    for lc, orig in low.items():
        if all(t in lc for t in tokens) and (end is None or lc.endswith(end)):
            return orig
    return None

c_date = find("date")
c_lst  = find("lste", end="_lst")
c_cld  = find("cloud_mask", "description")
c_mand = find("mandatory", "description")
c_qual = find("data_quality_flag", end="_flag")
c_geo  = find("geolocation")
c_zen  = find("solar zenith")
if c_lst is None or c_date is None:
    raise ValueError(f"Could not find LST/Date columns. Found: {list(df.columns)}")

lst_k = pd.to_numeric(df[c_lst], errors="coerce")
keep = lst_k.gt(200)                                   # 0.0 = fill / pixel not produced
reasons = {"fill_or_not_produced": int((~lst_k.gt(200)).sum())}
if c_cld is not None:
    clear = df[c_cld].astype(str).str.strip().str.lower().eq("clear")
    reasons["cloudy"] = int((~clear & lst_k.gt(200)).sum()); keep &= clear
if c_mand is not None:
    keep &= df[c_mand].astype(str).str.startswith("Pixel produced")
if c_qual is not None:
    keep &= df[c_qual].astype(str).str.strip().eq("0b00")

t_utc = pd.to_datetime(df[c_date], utc=True, errors="coerce")
t_loc = t_utc.dt.tz_convert(TZ)
out = pd.DataFrame({
    "date_utc": t_utc.dt.strftime("%Y-%m-%d %H:%M"),
    "date_local": t_loc.dt.strftime("%Y-%m-%d %H:%M"),
    "lst_c": (lst_k - 273.15).round(2),
    "month": t_loc.dt.month,
    "hour_local": t_loc.dt.hour,
    "geo_qa": df[c_geo] if c_geo else "",
    "solar_zenith": pd.to_numeric(df[c_zen], errors="coerce") if c_zen else None,
})[keep].dropna(subset=["lst_c"]).sort_values("date_local")
out.to_csv(DATA / "ecostress_lst.csv", index=False)

summer = out[out.month.isin([6, 7, 8])]
summary = {
    "source_file": src.name, "product": "ECO_L2_LSTE (v002)",
    "point": [float(df.Latitude.iloc[0]), float(df.Longitude.iloc[0])],
    "n_scenes": int(len(df)), "n_usable": int(len(out)),
    "n_usable_summer": int(len(summer)),
    "rejected": reasons,
    "max_lst_c": float(out.lst_c.max()) if len(out) else None,
    "max_summer_lst_c": float(summer.lst_c.max()) if len(summer) else None,
    "caveats": [
        "LST is land-SURFACE temperature, not air temperature; bare sunlit soil can exceed air Tmax by 10-20 C.",
        "Sampled 6.5 km from the block centroid -- regional illustration, NOT a block measurement.",
        "ISS overpasses are irregular and at varying local times; scenes are not directly comparable.",
        "Cloudy, 'pixel not produced' and non-nominal-quality scenes removed; counts above.",
    ],
}
(DATA / "ecostress_summary.json").write_text(json.dumps(summary, indent=2))
print(out.tail(10).to_string(index=False))
print(json.dumps(summary, indent=2))