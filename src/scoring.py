import pandas as pd
S = pd.read_csv("data/strategies.csv").set_index("id")

def dryness(i):                      # 0.6 wet .. 1.4 hot/dry
    d = 1.0 + 0.2*min(i["dry_spell_days"]/40, 1)
    d += 0.2*(1 - i["smap_pct"]/100) - 0.2*min(i["awc_mm"]/120, 1)
    return max(0.6, min(1.4, d))

def score(sid, i, w):
    s = S.loc[sid]; d = dryness(i)
    storm = min(i["winter_storm_days"]/8, 1)
    heat  = min(i["hot_days_ripening"]/25, 1)
    lowC  = 1 - min(i["soc_g_kg"]/40, 1)
    o = {
      "vine_water": 100 - s["summer_water_use"]*25*d,
      "erosion":    100*(1 - s["erosion_c"]/0.35)*(0.4 + 0.6*storm),
      "fertility":  100*(0.5*s["om_input"]/3 + 0.5*min(s["n_fix_high"]/60,1))*(0.6+0.4*lowC),
      "heat":       100*(s["heat_buffer"]/2)*(0.4 + 0.6*heat),
      "labor":      100*(1 - s["labor_passes"]/5),
    }
    o = {k: round(max(0, min(100, v)), 1) for k, v in o.items()}
    o["total"] = round(sum(w[k]*o[k] for k in w)/max(sum(w.values()), 1e-9), 1)
    return o