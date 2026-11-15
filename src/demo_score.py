import pandas as pd
from scoring import score

INDICATORS = {              # plausible hot/dry year at Cemovsko polje
    "hot_days_ripening": 24,   # Jul-Aug days Tmax >= 35 C   (POWER)
    "dry_spell_days": 45,      # longest Apr-Sep run < 1 mm  (POWER)
    "winter_storm_days": 9,    # Nov-Feb days >= 20 mm rain  (POWER/IMERG)
    "smap_pct": 15,            # root-zone moisture percentile vs 2015+ (SMAP)
    "awc_mm": 50.0,            # 0-30 cm, stone-corrected    (SoilGrids)
    "soc_g_kg": 15.0,          # topsoil SOC (SoilGrids)
}

# 3 Farmer personas all with different preferences
PERSONAS = {
    "Water-first grower": {"vine_water": 5, "erosion": 1, "fertility": 1, "heat": 0, "labor": 1},
    "Soil-first grower":  {"vine_water": 1, "erosion": 5, "fertility": 4, "heat": 2, "labor": 0},
    "Balanced":           {"vine_water": 3, "erosion": 3, "fertility": 2, "heat": 1, "labor": 1},
}

rows = [{"persona": name, "strategy": sid, **score(sid, INDICATORS, w)}
        for name, w in PERSONAS.items() for sid in ["bare", "grass", "legume"]]
df = pd.DataFrame(rows)
print(df.to_string(index=False), "\n")
for name in PERSONAS:
    sub = df[df.persona == name].sort_values("total", ascending=False)
    print(f"{name:20s} " + " > ".join(f"{r.strategy} ({r.total})" for r in sub.itertuples()))