# NASA-Space-Apps-Challenge-2026-Field-Shift
The project for the 2026 NASA Space Apps Challenge Hackathon. The project that I chose is Field Shift.

# 🍇 RowShift

**Rotate the alley, not the vine.**
A decision-support tool for vineyard inter-row management under a shifting climate — built for Ćemovsko polje, Podgorica, Montenegro.

NASA Space Apps Challenge 2026 · Challenge: **Field Shift: Adapting Farms with NASA Data** · Podgorica local event · Solo build

---

## The idea in one paragraph

Grapevines are a 30+ year perennial — they cannot be rotated. But the **alley between the rows** is ground a grower manages season after season, and that is a field that *does* rotate. RowShift compares **three inter-row strategies, including the existing practice**, scores them against NASA-derived heat and water evidence weighted by the grower's own priorities, and shows the trade-offs, the evidence, the gaps and the risks behind every score. It never issues a verdict.

| Strategy | Description |
|---|---|
| `bare` | Bare cultivated alley — **current practice** at Ćemovsko polje |
| `grass` | Permanent resident grass cover |
| `legume` | Winter legume cover → terminated ~15 May (DOY 135) → summer mulch |

The agronomic tension is real and documented: cover crops protect soil from erosion and add nitrogen and organic matter, but on shallow skeletal karst soils they compete with the vines for water in exactly the driest months. The winter-legume cycle is the compromise hypothesis the tool tests.

Link to the project presentation slide deck: https://canva.link/smlpee5icdx6pqv

---

## Status snapshot

| Component | State |
|---|---|
| NASA POWER ingestion (1990–2026 daily) | ✅ working |
| SoilGrids ingestion + derived soil constants | ✅ working |
| Indicator engine (heat, dry spells, storms, AWC) | ✅ working |
| Scoring engine + grower priority weights | ✅ working |
| Streamlit app (4 tabs, live re-ranking) | ✅ working |
| Elevation bias correction (disclosed, toggleable) | ✅ working |
| **SMAP L4 root-zone moisture** | ✅ working |
| **ECOSTRESS LST snapshot** | ✅ working |

---

## Quickstart

```bash
# Required
python 3.14
uv (https://docs.astral.sh/uv/)

# 1. install
uv add streamlit plotly pandas numpy requests folium streamlit-folium

# 2. fetch + derive (already cached in data/, re-run only to refresh)
uv run python src/fetch_nasa_power.py
uv run python src/fetch_soilgrids.py

# 3. compute indicators
uv run python src/indicators.py                  # latest complete season
uv run python src/indicators.py --year 2025      # a specific season
uv run python src/indicators.py --soc-override 15 --rooting-depth 60

# 4. sanity-check the scoring without the UI
uv run python src/demo_score.py

# 5. run the app  (from the repo root)
uv run streamlit run app.py
```

The app reads **only local files in `data/`** — no live API calls.

---

## Data sources

| Source | What it provides | Resolution | Status |
|---|---|---|---|
| **NASA POWER** (MERRA-2, AG community) | Daily `T2M_MAX`, `T2M_MIN`, `T2M`, `RH2M`, `ALLSKY_SFC_SW_DWN` → heat calendar, warm nights, dry spells, 1990–2026 trend | ~0.5° × 0.625°, daily | ✅ used |
| **GPM IMERG** (via POWER `PRECTOTCORR`) | Bias-corrected precipitation → dry-spell length, winter storm days | ~0.1°, daily | ✅ used |
| **ISRIC SoilGrids v2** *(non-NASA)* | `wv0033`, `wv1500`, `cfvo`, `soc`, `clay`, `sand`, `bdod` → available water capacity, organic carbon, texture | 250 m, 6 depths | ✅ used |
| **FAO-56 + cover-crop literature** | Crop coefficients, N-fixation ranges, USLE-style cover factors, labor assumptions | — | ✅ used (hand-authored constants) |
| **SMAP L4** (`SPL4SMGP`, AppEEARS) | Root-zone soil moisture → day-of-year percentile anomaly vs 2015+ | 9 km, 3-hourly | ⏳ ordered, processing |
| **ECOSTRESS** (`ECO_L2_LSTE`, AppEEARS) | Land-surface temperature → illustrative hot-block snapshot | ~70 m, irregular ISS overpasses | ⏳ ordered, processing |

**Deliberately skipped:** SSURGO/WSS, CropScape CDL, OpenET, PRISM, NAIP, NASS — all US-only and unavailable for Montenegro. SRTM slope was skipped because Ćemovsko polje is a flat plain (erosion there is driven by bareness + torrential rain, not gradient). In case the project scope is expanded to a field that is not a flat plain the SRTM slope needs to be included.

---

## Repository layout

```
.
├── app.py                      # Streamlit UI — reads only data/
├── src/
│   ├── fetch_nasa_power.py     # POWER daily point pull → data/POWER_*.csv
│   ├── fetch_soilgrids.py      # SoilGrids → parsed CSV + soil_constants.json
│   ├── indicators.py           # cached data → data/indicators.json (+ chart CSVs)
│   ├── score.py                # transparent multi-criteria scoring
│   └── demo_score.py           # headless ranking check across 3 personas
└── data/
    ├── POWER_Point_Daily_*.csv # raw POWER (YEAR,DOY layout, SI units)
    ├── soilgrids_raw.json      # raw API response (evidence)
    ├── soilgrids_parsed.csv    # scaled property × depth table
    ├── soilgrids_paw.csv       # plant-available water fraction per depth
    ├── soil_constants.json     # AWC 0–30/60/100 cm, SOC, texture, caveats
    ├── strategies.csv          # 3 rotations: traits + benefit/risk/assumption text
    ├── sources.csv             # constant → source → confidence register
    ├── indicators.json         # the six scoring inputs + meta.gaps
    ├── yearly_summary.csv      # per-year counts for the trend chart
    ├── daily_<year>.csv        # target-season series for the heat calendar
    ├── blocks.geojson          # optional: real block polygons (geojson.io)
    └── smap_l4.csv             # ⏳ drop the AppEEARS export here
```

---

## How it works

```
cached NASA + soil data
        ↓  src/indicators.py
six indicators  ──┐
                  ├──  src/score.py  ×  grower priority weights  →  ranked strategies
strategies.csv  ──┘                                                  + evidence footer
```

### Indicators (2026 season, current run)

| Indicator | Value | Definition |
|---|---|---|
| `hot_days_ripening` | **42 d** | Jul–Aug days with Tmax ≥ 35 °C |
| `hot_days_flowering` | **6 d** | May–Jun days with Tmax ≥ 35 °C |
| `warm_nights_ripening` | **49 d** | Jul–Aug nights with Tmin ≥ 20 °C (Vranac colour/aroma risk) |
| `dry_spell_days` | **45 d** | Longest Apr–Sep run with rain < 1 mm/day |
| `winter_storm_days` | **21 d** | Nov 2025–Feb 2026 days with rain ≥ 20 mm |
| `smap_pct` | **50** *(assumed)* | Root-zone moisture percentile vs same DOY ±15 d, 2015+ |
| `awc_mm` | **50.5 mm** | Plant-available water, top 30 cm, coarse-fragment corrected |
| `soc_g_kg` | **68 g/kg** | SoilGrids topsoil organic carbon (see caveats) |

### Scoring

Five criteria, each 0–100, combined as a weighted mean of the grower's sliders (0–5):

- **Vine water** — penalised by summer water use × a dryness factor built from dry-spell length, SMAP percentile and AWC
- **Erosion control** — USLE-style cover factor, amplified by winter storm frequency
- **Fertility** — organic-matter input + N fixation, amplified when baseline SOC is low
- **Heat buffering** — expected alley surface moderation, amplified by hot-day count
- **Labor & cost** — annual passes

Every formula is visible in `src/score.py` and every assumption is surfaced in the app's Evidence tab. **Transparency is the product.**

### Personas (the demo moment)

| Persona | Weights (water / erosion / fertility / heat / labor) | Effect |
|---|---|---|
| 💧 Water-first | 5 / 1 / 1 / 0 / 1 | Permanent grass falls to last — it drinks from the vines' reserve |
| 🌱 Soil-first | 1 / 5 / 4 / 2 / 0 | Permanent grass jumps to first — erosion and organic matter dominate |
| ⚖️ Balanced | 3 / 3 / 2 / 1 / 1 | Winter legume leads — protection without summer competition |

Same satellite evidence, different priorities, different answer. The grower decides.

---

## Configuration knobs (sidebar)

- **Season** — any year in the POWER record
- **Rooting depth** — 30 / 60 / 100 cm (vines on karst exploit deep fissures)
- **Lab SOC override** — replace the grid's suspicious 68 g/kg with a measured value
- **Lapse-rate elevation correction** — on/off, raw values preserved
- **Refresh data** — clears the cache and picks up newly arrived files

---

## Known limitations & assumptions

These are surfaced in-app under **Evidence, gaps & sources**, not buried:

1. **SMAP is pending.** The water score currently runs on rainfall + soil bucket only, with a neutral percentile of 50. A dry anomaly would strengthen the case against permanent grass.
2. **Elevation bias.** The POWER grid cell averages **933 m**; the vineyard sits at ~50 m. A first-order lapse-rate correction of **+5.7 °C** (6.5 °C/km) is applied and toggleable; unadjusted values are kept as `*_raw`. Needs validation against a local station.
3. **Centroid offset.** POWER was pulled at 42.38 N, 19.28 E; soil/block centroid is 42.42 N, 19.33 E. Both fall inside the **same MERRA-2 cell**, so values are unchanged — but the footer should be unified.
4. **SoilGrids cannot resolve karst.** The 250 m interpolated product reports loam/clay-loam, only 10–12 % coarse fragments and 68 g/kg SOC — Ćemovsko polje is famously skeletal, gravelly and shallow. Treat as low confidence; the lab-override slider exists for this reason.
5. **Scale mismatch.** SMAP 9 km, POWER ~50 km, SoilGrids 250 m vs a 1–5 ha block. Indicators are contextual evidence, never block measurements.
6. **No yield prediction.** By design. Exposure and trade-offs are defensible in a weekend; yield would be false precision.
7. **Agronomy constants are literature ranges**, not local measurements — N fixation 20–60 kg N/ha of covered alley is flagged low-confidence in `sources.csv`.

### Maintainer gotchas

- The POWER CSV uses a **`YEAR,DOY`** header (not `YEAR,MO,DY`) and returns **SI units** despite the `units: imperial` parameter in the fetch script. `indicators.py` handles both layouts and auto-detects units.
- POWER metadata headers must be skipped — anchor on `-END HEADER-`.
- Missing values are `-999`.
- Winter storms are counted **Nov of the previous year → Feb of the target year**.
- Do **not** hide `[data-testid="stToolbar"]` in CSS — Streamlit renders the "reopen sidebar" button inside it. Hide `stToolbarActions` / `stAppDeployButton` / `stStatusWidget` instead.

---

## Roadmap

- [ ] **Integrate SMAP L4** once AppEEARS finishes (drop-in, see below)
- [ ] **Integrate ECOSTRESS LST** as an illustrative hot-block panel
- [ ] Re-pull POWER at the unified block centroid
- [ ] Sentinel-2 NDVI to observe actual inter-row cover status
- [ ] Local soil sampling to replace grid-derived constants
- [ ] Validate the lapse-rate adjustment against a Podgorica station
- [ ] Draw real block polygons into `data/blocks.geojson`
- [ ] Optional: FAO-56 daily bucket water balance (Kc tables were scoped out for the 24 h build)

---

## References

- Allen, R.G. et al. (1998). *FAO Irrigation and Drainage Paper 56 — Crop Evapotranspiration.*
- Delpuech, X. et al. (2018). *Adapting cover crop soil coverage to soil depth to limit competition for water in vineyards.*
- Novara, A. et al. (2021). *Cover crop management and water conservation in vineyard and olive orchards.*
- Lopes, C.M. et al. (2016). *Cover crops competition for water in vineyards.*
- Poggio, L. et al. (2021). *SoilGrids 2.0: producing soil information for the globe.*
- Fernandes, A. et al. (2024). *Challenges to Viticulture in Montenegro under Climate Change.* ISPRS IJGI 13(8):270 — MONTEVITIS.
- MONTEVITIS (2023–2025), University of Donja Gorica — climate change mitigation and adaptation in Montenegrin viticulture.
- USLE cover-management (C) factor tables.
- NASA POWER · GPM IMERG · SMAP L4 · ECOSTRESS · ISRIC SoilGrids.

---

## AI / "Super Intelligence" disclosure

Per the 2026 NASA Space Apps SI policy: AI tools were used to accelerate implementation — parser debugging, indicator/scoring code, UI scaffolding and documentation. The solution concept, source selection, program architecture decisions, challenge framing, site selection and agronomic assumptions are the author's. No NASA logos, flags or mission identifiers appear in any generated asset.

---

## Credits

Built solo at the Podgorica local event, NASA Space Apps Challenge 2026.
Local context: Ćemovsko polje (~2,300 ha, Europe's largest contiguous vineyard, ~60 % Vranac) and the MONTEVITIS research programme at UDG.

License: MIT

---

## 📍 Where I am right now

**The pipeline is complete and the app runs end-to-end on real data.** Fetch → indicators → scoring → UI all work; the three strategies rank and re-rank live as the grower's priorities change, and every assumption is disclosed in the Evidence tab. The AppEEARS data is incorporated.

Everything else on the roadmap is post-hackathon polish.

# Challenge Description:
## Background

Farmers face increasingly complex decisions as temperatures shift, rainfall becomes less predictable, and soil health declines across many regions. Water shortages, erosion, nutrient depletion, and extreme weather events add further uncertainty. Selecting new crops to add to a rotation can be difficult, because a crop that improves soil health in one place may consume too much water, introduce disease, conflict with local markets, or fall outside expected growing seasons somewhere else.

This challenge is inspired in part by multigenerational farming experience — many families have lived through seasons where better tools for tracking changing conditions could have helped identify healthier, more resilient rotation choices. Today, NASA’s long‑term environmental datasets offer new ways to understand local growing conditions, and SI techniques open opportunities to translate that data into practical, farmer‑friendly insights.

## Objectives

You may consider combining NASA Earth observations with local agricultural information to create an app, model, interactive map, or other decision‑support tool. The goal is to help farmers explore crop‑rotation options that may improve soil health and strengthen resilience to changing weather and water conditions.

You may explore NASA datasets such as SMAP, ECOSTRESS, GPM, Landsat, MODIS, NASA POWER, GRACE and GRACE‑FO, and SRTM or other NASA elevation products. Using these datasets, you may analyze patterns in temperature, heat stress, rainfall, soil moisture, evaporation, frost risk, extreme precipitation, vegetation stress, and long‑term water trends. You may also consider local soil information, crop characteristics, and farmer priorities—such as water use, forage value, nitrogen‑fixing potential, erosion reduction, organic matter improvement, or market suitability.

Your tool may highlight times when fields are typically bare, seasons when current crops appear more vulnerable, or opportunities for rotations that could interrupt pest cycles, reduce water demand, improve infiltration, or add supplemental income. You may compare at least three rotation strategies, including the existing rotation. For each strategy, you may explain why it was suggested, what evidence supports it, what benefits it may offer, where information gaps exist, and any risks that would need local review by farmers or agricultural experts.

The intended outcome is a supportive tool — one that helps identify patterns and possibilities, but does not replace farmer judgment or local agricultural expertise.

## Potential Considerations

You may (but are not required to) consider the following:

Understanding Conditions & Data

    Explore how changes in temperature, soil moisture, rainfall, evaporation, and vegetation stress relate to crop vulnerability and soil health.
    Consider explaining scientific terms such as evapotranspiration, soil moisture anomalies, vegetation indices (e.g., NDVI), frost risk, and water‑balance indicators.
    Clarify how satellite observations differ from ground‑based measurements, and how combining both may improve accuracy.

SI, Modeling, and Data Fusion

    You may compare different SI or statistical approaches for identifying patterns in historical climate and soil conditions.
    Consider how SI could highlight seasonal transitions, bare‑field periods, or times when current crops show increased stress.
    Explain how the model interprets uncertainty and where local expertise would be needed to validate results.
    You may consider harmonizing datasets with different spatial and temporal resolutions by downsampling, aggregating, or resampling them to a common analysis grid. Harmonizing resolution can help the SI combine SMAP soil moisture, ECOSTRESS land‑surface temperature, GPM precipitation, Landsat/MODIS vegetation indices, GEDI biomass, and soil datasets into coherent features that support clear, explainable rotation‑strategy comparisons.

Rotation Strategy Exploration

    Compare rotation scenarios by examining nutrient cycling, erosion risk, organic matter contributions, pest‑cycle disruption, water use, forage potential, or market considerations.
    You may consider mapping which rotation ideas best align with farmer priorities—such as conserving water, generating supplemental income, or improving soil structure.
    Include brief explanations of how nitrogen‑fixing crops, cover crops, deep‑rooting crops, or drought‑tolerant crops contribute to long‑term soil health.

Geospatial Mapping & Visualization

    Consider whether interactive maps could help users explore trends over time such as long‑term soil moisture, heat waves, or water‑storage declines.
    Explore ways to visualize field‑level vulnerabilities (e.g., zones of erosion risk, water stress hotspots, frost‑prone areas).
    You may include optional add‑ons such as timelines, overlays comparing datasets, or scenario sliders that adjust rainfall or temperature patterns.

Farmer‑Centered Design

    Consider how to make the tool easily interpretable for farmers who may have limited technical or geospatial experience.
    Think about ways to allow farmers to input their own priorities or constraints, such as water availability, equipment limitations, or market preferences.
    Share reminders that the tool is intended to support—not replace—local expertise, and highlight where human judgment is particularly important.
