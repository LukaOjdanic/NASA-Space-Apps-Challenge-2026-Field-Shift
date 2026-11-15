# fetch_nasa_power.py
import requests

URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMS = {
    "start": "19900101",
    "end": "20261113",
    "latitude": 42.38,          # Ćemovsko polje block centroid (unified)
    "longitude": 19.28,
    "community": "ag",
    "parameters": "T2M_MAX,T2M_MIN,T2M,PRECTOTCORR,RH2M,ALLSKY_SFC_SW_DWN",
    "format": "csv",
    # units param omitted -> SI default (degC, mm/day) matches 35 C / 20 mm thresholds
    "header": "true",
}
FILENAME = "data/POWER_Point_Daily_19900101_20261113_042d38N_019d28E_LST.csv"

r = requests.get(URL, params=PARAMS, headers={"accept": "application/json"}, timeout=180)
r.raise_for_status()
open(FILENAME, "w").write(r.text)
print(f"Saved {FILENAME} ({len(r.text)} bytes)")

# Quick unit sanity check on the header block
head = r.text.splitlines()[:20]
units_line = next((l for l in head if "T2M_MAX" in l and "C" in l.upper() or "mm" in l.lower()), "")
print("Unit line from header:", units_line)