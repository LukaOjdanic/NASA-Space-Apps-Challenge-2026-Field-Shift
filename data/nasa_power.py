import requests, pandas as pd, io
params = "T2M_MAX,T2M_MIN,T2M,PRECTOTCORR,RH2M,ALLSKY_SFC_SW_DWN"
frames = []
for y0 in range(1990, 2026, 5):          # chunked = robust to any request-size limit
    url = (f"https://power.larc.nasa.gov/api/temporal/daily/point?parameters={params}"
           f"&community=AG&latitude=42.42&longitude=19.33"
           f"&start={y0}0101&end={min(y0+4,2025)}1231&format=CSV")
    r = requests.get(url, timeout=120); r.raise_for_status()
    frames.append(pd.read_csv(io.StringIO(r.text), skiprows=15))  # check header lines!
pd.concat(frames).to_csv("data/power_daily.csv", index=False)