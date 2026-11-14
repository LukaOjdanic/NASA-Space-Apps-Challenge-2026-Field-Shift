import json
import requests
from pathlib import Path
import pandas as pd

URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"

PARAMS = {
    "lon": 19.28,
    "lat": 42.38,
    "property": ["clay", "sand", "soc", "cfvo", "bdod", "wv0033", "wv1500"],
    "depth": ["0-5cm", "5-15cm", "15-30cm"],
    "value": "mean",
}

OUT = Path("data/soilgrids_raw.json")
OUT.parent.mkdir(parents=True, exist_ok=True)

# --- fetch ---
resp = requests.get(URL, params=PARAMS, timeout=60)
resp.raise_for_status()
OUT.write_text(json.dumps(resp.json(), indent=2))
print(f"Saved {OUT} ({OUT.stat().st_size} bytes)")

# --- parse ---
raw = json.loads(OUT.read_text())

FACTORS = {
    "clay": 10, "sand": 10, "soc": 10,
    "cfvo": 10, "bdod": 100,
    "wv0033": 1000, "wv1500": 1000,   # raw / 1000 -> volumetric fraction
}

rows = []
for layer in raw["properties"]["layers"]:
    prop = layer["name"]
    for d in layer["depths"]:
        rows.append({
            "property": prop,
            "depth": d["label"],
            "raw_mean": d["values"]["mean"],
            "value": d["values"]["mean"] / FACTORS.get(prop, 1) if d["values"]["mean"] is not None else None,
        })

df = pd.DataFrame(rows)
df.to_csv("data/soilgrids_parsed.csv", index=False)

# Plant-available water fraction per depth (wv0033 - wv1500)
paw = (df[df.property == "wv0033"].set_index("depth")["value"]
       - df[df.property == "wv1500"].set_index("depth")["value"]).rename("paw_fraction")
paw.to_csv("data/soilgrids_paw.csv")

print(paw)

# --- Karst sensitivity: SoilGrids 250 m cell mixes land covers on Ćemovsko polje.
# Local literature (MONTEVITIS / Plantaže) describes skeletal, shallow, low-OM soil.
# Offer a "karst-corrected" scenario the farmer can dial in.
GRID_PAW = paw.copy()                                   # from SoilGrids
KARST_PAW = (GRID_PAW * 0.5).clip(lower=0.02, upper=0.08)  # halve + cap

sensitivity = pd.DataFrame({
    "depth": GRID_PAW.index,
    "paw_grid": GRID_PAW.values,
    "paw_karst_low": KARST_PAW.values,
})
sensitivity.to_csv("data/soilgrids_paw_sensitivity.csv", index=False)
print(sensitivity)