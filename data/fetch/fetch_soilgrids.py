"""Fetch SoilGrids at the block centroid -> derived soil constants for RowShift.
Run from repo root:  uv run python data/fetch/fetch_soilgrids.py [--lat 42.42 --lon 19.33]
Outputs: soilgrids_raw.json, soilgrids_parsed.csv, soilgrids_paw.csv, soil_constants.json
"""
import argparse, json
from pathlib import Path
import pandas as pd
import requests

URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"
PROPS = ["clay", "sand", "soc", "cfvo", "bdod", "wv0033", "wv1500"]
DEPTHS = ["0-5cm", "5-15cm", "15-30cm", "30-60cm", "60-100cm"]
FACTORS = {"clay": 10, "sand": 10, "soc": 10, "cfvo": 10, "bdod": 100,
           "wv0033": 1000, "wv1500": 1000}  # SoilGrids mapped units -> % / g/kg / fraction

def thickness_mm(label):                      # "15-30cm" -> 150
    lo, hi = label.replace("cm", "").split("-")
    return (int(hi) - int(lo)) * 10

def texture_class(clay, sand):                # simplified USDA triangle (approximate)
    if clay is None or sand is None: return "unknown"
    silt = 100 - clay - sand
    if clay >= 40 and silt >= 40: return "silty clay"
    if clay >= 40 and sand <= 45: return "clay"
    if clay >= 35 and sand > 45:  return "sandy clay"
    if clay >= 27 and silt >= 40: return "silty clay loam"
    if clay >= 27: return "clay loam" if sand <= 45 else "sandy clay loam"
    if clay >= 20 and sand > 45:  return "sandy clay loam"
    if silt >= 50: return "silt loam" if clay >= 12 else "silt"
    if clay >= 7 and sand <= 52:  return "loam"
    if sand > 85: return "sand"
    return "sandy loam"

ap = argparse.ArgumentParser()
ap.add_argument("--lat", type=float, default=42.42)   # SAME centroid as POWER
ap.add_argument("--lon", type=float, default=19.33)
a = ap.parse_args()
out = Path("data"); out.mkdir(exist_ok=True)

r = requests.get(URL, params={"lat": a.lat, "lon": a.lon, "property": PROPS,
                              "depth": DEPTHS, "value": "mean"}, timeout=60)
r.raise_for_status()
raw = r.json()
(out / "soilgrids_raw.json").write_text(json.dumps(raw, indent=2))

rows = []
for layer in raw["properties"]["layers"]:
    p = layer["name"]
    for d in layer["depths"]:
        m = d["values"]["mean"]
        rows.append({"property": p, "depth": d["label"], "raw_mean": m,
                     "value": None if m is None else m / FACTORS[p]})
df = pd.DataFrame(rows)
df.to_csv(out / "soilgrids_parsed.csv", index=False)

def get(p, depth):
    v = df[(df.property == p) & (df.depth == depth)]["value"]
    return None if v.empty else v.iloc[0]

paw_rows, awc = [], {"0-30cm": 0.0, "0-60cm": 0.0, "0-100cm": 0.0}
for depth in DEPTHS:
    fc, wp, cf = get("wv0033", depth), get("wv1500", depth), get("cfvo", depth)
    if fc is None or wp is None: continue
    t = thickness_mm(depth)
    mm = (fc - wp) * t
    eff = mm * (1 - (cf or 0) / 100)          # stones hold no plant-available water
    paw_rows.append({"depth": depth, "paw_fraction": round(fc - wp, 4),
                     "thickness_mm": t, "paw_mm": round(mm, 1),
                     "cfvo_pct": cf, "paw_eff_mm": round(eff, 1)})
    top = int(depth.replace("cm", "").split("-")[0])
    for key, limit in [("0-30cm", 30), ("0-60cm", 60), ("0-100cm", 100)]:
        if top < limit: awc[key] += eff
pd.DataFrame(paw_rows).to_csv(out / "soilgrids_paw.csv", index=False)

num = den = 0.0
for depth in ["0-5cm", "5-15cm", "15-30cm"]:
    s = get("soc", depth)
    if s is not None: num += s * thickness_mm(depth); den += thickness_mm(depth)

constants = {
    "lat": a.lat, "lon": a.lon,
    "awc_0_30_mm": round(awc["0-30cm"], 1),
    "awc_0_60_mm": round(awc["0-60cm"], 1),
    "awc_0_100_mm": round(awc["0-100cm"], 1),
    "soc_top_g_kg": get("soc", "0-5cm"),
    "soc_0_30_g_kg": round(num / den, 1) if den else None,
    "texture_0_5cm": texture_class(get("clay", "0-5cm"), get("sand", "0-5cm")),
    "texture_15_30cm": texture_class(get("clay", "15-30cm"), get("sand", "15-30cm")),
    "cfvo_0_5_pct": get("cfvo", "0-5cm"),
    "caveats": [
        "SoilGrids 250 m interpolated product; karst heterogeneity not resolved.",
        "Coarse-fragment correction applied; local stone cover may be much higher.",
        "AWC assumes uniform soil to depth; vines may exploit deep karst fissures.",
        "Verify against local soil survey / MONTEVITIS data before farm decisions.",
    ],
}
(out / "soil_constants.json").write_text(json.dumps(constants, indent=2))
print(pd.DataFrame(paw_rows).to_string(index=False))
print(json.dumps(constants, indent=2))