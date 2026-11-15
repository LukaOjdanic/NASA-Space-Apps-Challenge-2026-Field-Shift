"""indicators.py -- cached NASA/soil data -> the six numbers score.py needs.

Reads:  data/POWER*.csv           (required; auto-detects header row + units)
        data/*SMAP*.csv           (optional AppEEARS SPL4SMGP point sample)
        data/soil_constants.json  (optional; falls back to soilgrids_parsed.csv)
Writes: data/indicators.json      (score keys + extras + meta.gaps)
        data/yearly_summary.csv   (trend chart)
        data/daily_<year>.csv     (heat-calendar heatmap)

Run:  python indicators.py [--year 2026] [--rooting-depth 30] [--soc-override 15]
"""
import argparse, io, json, re
from pathlib import Path
import numpy as np
import pandas as pd

DATA = Path("data")
HEAT_C, NIGHT_C, STORM_MM, DRY_MM = 35.0, 20.0, 20.0, 1.0
THICK_MM = {"0-5cm": 50, "5-15cm": 100, "15-30cm": 150, "30-60cm": 300, "60-100cm": 400}
SITE_ELEV_M = 50.0       # Cemovsko polje vineyard floor
LAPSE_C_PER_M = 0.0065   # standard environmental lapse rate
APPLY_ELEV_ADJUST = True


def longest_true_run(mask):
    best = cur = 0
    for v in mask:
        cur = cur + 1 if v else 0
        best = max(best, cur)
    return int(best)


def _pick_power_file(path=None):
    if path:
        return Path(path)
    roots = [Path("data"), Path(__file__).resolve().parent.parent / "data"]
    files = [p for r in roots for pat in ("POWER*.csv", "power*.csv") for p in r.glob(pat)]
    if not files:
        raise FileNotFoundError("No data/POWER*.csv found -- run fetch_nasa_power.py")
    return max(files, key=lambda p: p.stat().st_mtime)


def _find_header(lines):
    """Prefer the line right after -END HEADER-; else scan for a real column row."""
    for i, l in enumerate(lines):
        if l.strip().upper().startswith("-END HEADER"):
            for j in range(i + 1, len(lines)):
                if lines[j].strip():
                    return j
    for i, l in enumerate(lines):
        t = [x.strip().upper() for x in l.split(",")]
        if len(t) >= 3 and t[0] in ("YEAR", "YYYYMMDD", "DATE", "DATETIME", "TIME") \
           and any(x.startswith(("T2M", "PRECTOT")) for x in t):
            return i
    raise ValueError("Could not locate POWER header. First lines:\n" + "\n".join(lines[:20]))


def _build_date(df):
    """Handle every POWER date layout: YEAR/MO/DY, YYYYMMDD, DATE, ISO, YEAR+DOY."""
    c = {x.upper(): x for x in df.columns}
    def dt(*names): return pd.to_datetime(df[[c[n] for n in names]].rename(
        columns={c[n]: k for n, k in zip(names, ("year", "month", "day"))}), errors="coerce")
    if {"YEAR", "MO", "DY"} <= c.keys():        return dt("YEAR", "MO", "DY")
    if {"YEAR", "MONTH", "DAY"} <= c.keys():    return dt("YEAR", "MONTH", "DAY")
    if "YYYYMMDD" in c: return pd.to_datetime(df[c["YYYYMMDD"]].astype(str), format="%Y%m%d", errors="coerce")
    for k in ("DATE", "DATETIME", "TIME"):
        if k in c: return pd.to_datetime(df[c[k]], errors="coerce", utc=True).dt.tz_convert(None)
    if {"YEAR", "DOY"} <= c.keys():
        return (pd.to_datetime(df[c["YEAR"]].astype(str), format="%Y")
                + pd.to_timedelta(pd.to_numeric(df[c["DOY"]]) - 1, unit="D"))
    raise ValueError(f"No recognised date columns. Found: {list(df.columns)}")


def load_power(path=None):
    path = _pick_power_file(path)
    lines = path.read_text().splitlines()
    df = pd.read_csv(io.StringIO("\n".join(lines[_find_header(lines):])))
    df.columns = [c.strip() for c in df.columns]
    df["date"] = _build_date(df)
    df = df.dropna(subset=["date"]).set_index("date").sort_index()
    df = df.drop(columns=[c for c in df.columns
                          if c.upper() in ("YEAR", "MO", "DY", "MONTH", "DAY",
                                           "YYYYMMDD", "DATE", "DATETIME", "DOY")])
    for c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.replace([-999, -999.0], np.nan)
    if not any(c.upper().startswith("PRECTOT") for c in df.columns):
        raise ValueError(f"No precipitation column. Found: {list(df.columns)}")
    if "PRECTOTCORR" not in df.columns:
        p = next(c for c in df.columns if c.upper().startswith("PRECTOT"))
        df = df.rename(columns={p: "PRECTOTCORR"})

    notes = [f"Loaded {path.name}"]
    if df["T2M_MAX"].max() > 60:
        for c in ("T2M_MAX", "T2M_MIN", "T2M"):
            if c in df: df[c] = (df[c] - 32) * 5 / 9
        notes.append("POWER temperatures were imperial (F); converted to C.")
    annual = df["PRECTOTCORR"].groupby(df.index.year).sum()
    if annual.median() < 200:
        df["PRECTOTCORR"] *= 25.4
        notes.append("POWER precipitation looked like inches/day; converted to mm/day.")
    m = re.search(r"region\s*=\s*([\d.]+)\s*meters", "\n".join(lines[:30]), re.I)
    if m and APPLY_ELEV_ADJUST:
        grid_elev = float(m[1])
        off = (grid_elev - SITE_ELEV_M) * LAPSE_C_PER_M
        for c in ("T2M_MAX", "T2M_MIN", "T2M"):
            if c in df:
                df[c + "_raw"] = df[c]      # keep originals for the evidence footer
                df[c] = df[c] + off
        notes.append(
            f"Elevation adjustment: POWER grid mean {grid_elev:.0f} m vs vineyard ~{SITE_ELEV_M:.0f} m; "
            f"+{off:.1f} C applied to temperatures (lapse rate 6.5 C/km). Raw values kept as *_raw. "
            "First-order downscaling — validate against a local station before farm decisions.")
    return df, path.name, notes, float(annual.median())


def smap_percentile(path, ref_date, window=15):
    """Root-zone moisture percentile vs same day-of-year (+/- window) across all years."""
    if path is None:
        files = list(DATA.glob("*SMAP*.csv")) + list(DATA.glob("*smap*.csv"))
        path = max(files, key=lambda p: p.stat().st_mtime) if files else None
    if path is None:
        return 50.0, None, ["SMAP file not present; neutral percentile (50) assumed."]
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    tcol = next((c for c in df.columns if "time" in c or "date" in c), None)
    vcol = next((c for c in df.columns if "rootzone" in c), None) \
        or next((c for c in df.columns if "sm_surface" in c), None)
    if tcol is None or vcol is None:
        return 50.0, None, ["SMAP CSV: could not find time/rootzone columns; neutral 50 used."]
    s = pd.Series(pd.to_numeric(df[vcol], errors="coerce").values,
                  index=pd.to_datetime(df[tcol], errors="coerce", utc=True).dt.tz_convert(None))
    s = s[(s > 0) & (s <= 1)].dropna().sort_index().resample("D").mean().dropna()
    if s.empty:
        return 50.0, None, ["SMAP CSV had no valid rootzone values; neutral 50 used."]
    pos = s.index.get_indexer([ref_date], method="nearest")[0]
    cur_date = s.index[pos]
    if abs((cur_date - ref_date).days) > 10:
        cur_date, cur = s.index[-1], s.iloc[-1]   # fall back to latest observation
    else:
        cur = s.iloc[pos]
    doy = s.index.dayofyear
    dist = np.abs(doy - cur_date.dayofyear)
    dist = np.minimum(dist, 366 - dist)
    hist = s[dist <= window]
    pct = float((hist <= cur).mean() * 100)
    note = [f"SMAP percentile vs {len(hist)} daily values within +/-{window} days of DOY "
            f"{cur_date.dayofyear} (2015+); 9 km pixel, not block-scale."]
    return round(pct, 1), str(cur_date.date()), note


def load_soil(rooting_depth_cm=30, soc_override=None):
    gaps, awc, soc = [], None, None
    cj = DATA / "soil_constants.json"
    if cj.exists():
        c = json.loads(cj.read_text())
        key = {30: "awc_0_30_mm", 60: "awc_0_60_mm", 100: "awc_0_100_mm"}.get(rooting_depth_cm)
        awc = c.get(key) or c.get("awc_0_30_mm")
        soc = c.get("soc_top_g_kg")
        if key and c.get(key) is None:
            gaps.append(f"AWC at {rooting_depth_cm} cm unavailable; used 0-30 cm total.")
    elif (DATA / "soilgrids_parsed.csv").exists():
        piv = pd.read_csv(DATA / "soilgrids_parsed.csv").pivot_table(
            index="depth", columns="property", values="value")
        awc = 0.0
        for d, row in piv.iterrows():
            top = int(d.replace("cm", "").split("-")[0])
            if top < rooting_depth_cm and {"wv0033", "wv1500", "cfvo"} <= set(row.index):
                awc += (row["wv0033"] - row["wv1500"]) * THICK_MM[d] * (1 - row["cfvo"] / 100)
        soc = float(piv.loc["0-5cm", "soc"])
        gaps.append("Soil constants derived from 3-depth parsed CSV; re-run fetch_soilgrids.py for 100 cm.")
    if awc is None:
        awc, soc = 50.0, 20.0
        gaps.append("No soil data found; placeholder AWC=50 mm, SOC=20 g/kg.")
    if soc_override is not None:
        gaps.append(f"SOC overridden by farmer/lab value: {soc_override} g/kg (grid said {soc}).")
        soc = soc_override
    gaps.append("SoilGrids 250 m grid under-resolves karst; local soils likely shallower/stonier.")
    return round(float(awc), 1), float(soc), gaps


def compute_indicators(year=None, rooting_depth_cm=30, soc_override=None,
                       power_path=None, smap_path=None):
    df, fname, notes, annual_mm = load_power(power_path)
    gaps = list(notes)

    if year is None:  # latest year with a complete Apr-Sep growing season
        for y in sorted(df.index.year.unique(), reverse=True):
            sub = df[(df.index.year == y) & (df.index.month >= 4) & (df.index.month <= 9)]
            if sub["T2M_MAX"].notna().sum() >= 180:
                year = int(y); break
    gaps.append(f"Target season: {year}. Thresholds: heat >= {HEAT_C} C, warm night >= {NIGHT_C} C, "
                f"storm >= {STORM_MM} mm/day, dry day < {DRY_MM} mm.")

    rip = df[(df.index.year == year) & df.index.month.isin([7, 8])]
    flo = df[(df.index.year == year) & df.index.month.isin([5, 6])]
    grow = df[(df.index.year == year) & (df.index.month >= 4) & (df.index.month <= 9)]
    winter = df[((df.index.year == year - 1) & (df.index.month >= 11)) | ((df.index.year == year) & (df.index.month <= 2))]
    gaps.append(f"Winter storms counted Nov {year-1} - Feb {year} (winter preceding the season).")

    pct, smap_date, smap_notes = smap_percentile(smap_path, pd.Timestamp(year=year, month=7, day=31))
    gaps += smap_notes
    awc, soc, soil_gaps = load_soil(rooting_depth_cm, soc_override)
    gaps += soil_gaps

    # centroid check: POWER filename encodes its grid point (e.g. 042d38N_019d28E)
    m = re.search(r"(\d{3})d(\d{2})([NS])_(\d{3})d(\d{2})([EW])", fname)
    if m and (DATA / "soil_constants.json").exists():
        lat = int(m[1]) + int(m[2]) / 100; lon = int(m[4]) + int(m[5]) / 100
        c = json.loads((DATA / "soil_constants.json").read_text())
        if abs(lat - c["lat"]) > 0.02 or abs(lon - c["lon"]) > 0.02:
            gaps.append(f"POWER point ({lat:.2f},{lon:.2f}) differs from soil/block centroid "
                        f"({c['lat']},{c['lon']}); re-pull POWER at the unified centroid.")

    ind = {
        "hot_days_ripening": int((rip["T2M_MAX"] >= HEAT_C).sum()),
        "hot_days_flowering": int((flo["T2M_MAX"] >= HEAT_C).sum()),
        "warm_nights_ripening": int((rip["T2M_MIN"] >= NIGHT_C).sum()),
        "dry_spell_days": longest_true_run((grow["PRECTOTCORR"] < DRY_MM).fillna(False)),
        "winter_storm_days": int((winter["PRECTOTCORR"] >= STORM_MM).sum()),
        "smap_pct": pct, "smap_date": smap_date,
        "awc_mm": awc, "soc_g_kg": soc,
        "meta": {"year": year, "power_file": fname, "median_annual_precip_mm": round(annual_mm, 0),
                 "rooting_depth_cm": rooting_depth_cm, "gaps": gaps,
                 "sources": ["NASA POWER daily (AG; PRECTOTCORR = GPM IMERG-corrected)",
                             "SMAP L4 root-zone soil moisture (if present)", "ISRIC SoilGrids v2"]},
    }

    # chart-ready side outputs
    rows = []
    for y, g in df.groupby(df.index.year):
        r = g[g.index.month.isin([7, 8])]; f = g[g.index.month.isin([5, 6])]
        gs = g[(g.index.month >= 4) & (g.index.month <= 9)]
        rows.append({"year": int(y),
                     "hot_days_ripening": int((r["T2M_MAX"] >= HEAT_C).sum()),
                     "hot_days_flowering": int((f["T2M_MAX"] >= HEAT_C).sum()),
                     "dry_spell_days": longest_true_run((gs["PRECTOTCORR"] < DRY_MM).fillna(False)),
                     "precip_total_mm": round(float(g["PRECTOTCORR"].sum()), 0)})
    pd.DataFrame(rows).to_csv(DATA / "yearly_summary.csv", index=False)
    daily = df[df.index.year == year][["T2M_MAX", "T2M_MIN", "PRECTOTCORR"]].copy()
    daily.columns = ["tmax_c", "tmin_c", "precip_mm"]
    daily.reset_index().to_csv(DATA / f"daily_{year}.csv", index=False)
    return ind


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=None)
    ap.add_argument("--rooting-depth", type=int, default=30, choices=[30, 60, 100])
    ap.add_argument("--soc-override", type=float, default=None)
    ap.add_argument("--power", default=None); ap.add_argument("--smap", default=None)
    a = ap.parse_args()
    ind = compute_indicators(a.year, a.rooting_depth, a.soc_override, a.power, a.smap)
    (DATA / "indicators.json").write_text(json.dumps(ind, indent=2, default=str))
    print(json.dumps({k: v for k, v in ind.items() if k != "meta"}, indent=2))
    print("\nGAPS / ASSUMPTIONS (evidence footer):")
    for g in ind["meta"]["gaps"]: print(" -", g)
    print(f"\nSanity check: median annual precip = {ind['meta']['median_annual_precip_mm']} mm "
          "(Podgorica expects roughly 1500-1700 mm). Saved data/indicators.json")