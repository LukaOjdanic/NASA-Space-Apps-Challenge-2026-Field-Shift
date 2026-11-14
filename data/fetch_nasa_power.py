import requests

URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMS = {
    "start": "19900101",
    "end": "20261113",
    "latitude": 42.381,
    "longitude": 19.282,
    "community": "ag",
    "parameters": "T2M_MAX,T2M_MIN,T2M,PRECTOTCORR,RH2M,ALLSKY_SFC_SW_DWN",
    "format": "csv",
    "units": "imperial",
    "header": "true",
}
FILENAME = "data/POWER_Point_Daily_19900101_20261113_042d38N_019d28E_LST.csv"

r = requests.get(URL, params=PARAMS, headers={"accept": "application/json"}, timeout=180)
r.raise_for_status()
with open(FILENAME, "w") as f:
    f.write(r.text)
print(f"Saved {FILENAME} ({len(r.text)} bytes)")