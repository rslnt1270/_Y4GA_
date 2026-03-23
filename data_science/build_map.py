"""
YAGA PROJECT - Mapa Historico de Puntos de Partida
Geocodifica codigos postales unicos y genera mapa interactivo HTML.
"""

import csv
import re
import json
import time
import os
import folium
import pandas as pd
from folium.plugins import MarkerCluster, HeatMap
from geopy.geocoders import Nominatim

# ── Rutas ─────────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
CSV_PATH   = os.path.join(BASE_DIR, "YAGA_DataSet_Clean.csv")
CACHE_PATH = os.path.join(BASE_DIR, "geocode_cache.json")
MAP_OUT    = os.path.join(BASE_DIR, "YAGA_Mapa_Historico.html")

# ── 1. Cargar dataset ─────────────────────────────────────────────────────────
print("Cargando dataset...")
df = pd.read_csv(CSV_PATH)
df = df[df["origen"].notna() & (df["origen"].str.strip() != "")]
df = df[df["estado"] == "COMPLETED"].copy()
print(f"  Viajes COMPLETED con origen: {len(df)}")

# ── 2. Extraer CP de la direccion de origen ───────────────────────────────────
def extraer_cp(direccion):
    m = re.search(r'\b(\d{5})\b', str(direccion))
    return m.group(1) if m else None

df["cp"] = df["origen"].apply(extraer_cp)
df_con_cp = df[df["cp"].notna()].copy()
cps_unicos = df_con_cp["cp"].unique().tolist()
print(f"  CPs unicos a geocodificar: {len(cps_unicos)}")

# ── 3. Geocodificar CPs (con cache) ───────────────────────────────────────────
cache = {}
if os.path.exists(CACHE_PATH):
    with open(CACHE_PATH) as f:
        cache = json.load(f)
    print(f"  Cache cargado: {len(cache)} CPs ya geocodificados")

geolocator = Nominatim(user_agent="yaga_map_v1", timeout=10)
nuevos = 0

for i, cp in enumerate(cps_unicos):
    if cp in cache:
        continue
    try:
        loc = geolocator.geocode(f"{cp}, Mexico", country_codes="MX")
        if loc:
            cache[cp] = {"lat": loc.latitude, "lng": loc.longitude, "address": loc.address}
        else:
            cache[cp] = None
        nuevos += 1
        time.sleep(1.1)  # Nominatim ToS: 1 req/sec

        if nuevos % 20 == 0:
            with open(CACHE_PATH, "w") as f:
                json.dump(cache, f)
            print(f"  Geocodificados: {i+1}/{len(cps_unicos)} ({nuevos} nuevos)")

    except Exception as e:
        print(f"  Error CP {cp}: {e}")
        cache[cp] = None
        time.sleep(2)

# Guardar cache final
with open(CACHE_PATH, "w") as f:
    json.dump(cache, f, ensure_ascii=False, indent=2)
print(f"  Cache guardado ({len(cache)} CPs). Nuevos geocodificados: {nuevos}")

# ── 4. Unir coordenadas al dataframe ─────────────────────────────────────────
def get_lat(cp):
    if cp and cp in cache and cache[cp]:
        return cache[cp]["lat"]
    return None

def get_lng(cp):
    if cp and cp in cache and cache[cp]:
        return cache[cp]["lng"]
    return None

df_con_cp["lat"] = df_con_cp["cp"].apply(get_lat)
df_con_cp["lng"] = df_con_cp["cp"].apply(get_lng)
df_map = df_con_cp[df_con_cp["lat"].notna() & df_con_cp["lng"].notna()].copy()
print(f"\nViajes mapeables: {len(df_map)} / {len(df)}")

# ── 5. Calcular color por monto ───────────────────────────────────────────────
def color_por_monto(monto):
    if monto >= 200:   return "darkgreen"
    elif monto >= 130: return "green"
    elif monto >= 90:  return "orange"
    else:              return "red"

df_map["color"] = df_map["monto_bruto"].apply(color_por_monto)

# ── 6. Construir el mapa ──────────────────────────────────────────────────────
print("Construyendo mapa...")

# Centro en CDMX / Valle de Mexico
mapa = folium.Map(
    location=[19.43, -99.13],
    zoom_start=11,
    tiles="CartoDB positron",
    prefer_canvas=True
)

# ── Capa 1: Clusters de marcadores ────────────────────────────────────────────
cluster = MarkerCluster(
    name="Puntos de partida",
    options={"maxClusterRadius": 40, "disableClusteringAtZoom": 14}
).add_to(mapa)

for _, row in df_map.iterrows():
    popup_html = f"""
    <div style="font-family:monospace; font-size:12px; min-width:220px">
        <b style="color:#1a1a2e">YAGA — Viaje</b><br>
        <hr style="margin:4px 0">
        <b>ID:</b> {str(row['trip_id'])[:8]}...<br>
        <b>Fecha:</b> {row['fecha_local']}<br>
        <b>Monto:</b> <span style="color:green"><b>${row['monto_bruto']:.2f} MXN</b></span><br>
        <b>Distancia:</b> {row['distancia_km']:.1f} km<br>
        <b>Duracion:</b> {row['duracion_min']:.0f} min<br>
        <b>CP:</b> {row['cp']}<br>
        <b>Origen:</b><br>
        <span style="color:#555">{row['origen'][:80]}{'...' if len(row['origen']) > 80 else ''}</span>
    </div>
    """
    folium.CircleMarker(
        location=[row["lat"], row["lng"]],
        radius=6,
        color=row["color"],
        fill=True,
        fill_color=row["color"],
        fill_opacity=0.75,
        popup=folium.Popup(popup_html, max_width=280),
        tooltip=f"${row['monto_bruto']:.0f} MXN — {row['fecha_local'][:10]}",
    ).add_to(cluster)

# ── Capa 2: Heatmap de densidad ───────────────────────────────────────────────
heat_data = df_map[["lat", "lng", "monto_bruto"]].values.tolist()
HeatMap(
    heat_data,
    name="Densidad de viajes",
    min_opacity=0.3,
    radius=18,
    blur=15,
    max_zoom=13,
    show=False
).add_to(mapa)

# ── Leyenda ───────────────────────────────────────────────────────────────────
legend_html = """
<div style="
    position: fixed; bottom: 40px; left: 40px; z-index: 1000;
    background: white; padding: 14px 18px; border-radius: 10px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.2); font-family: monospace; font-size: 12px;
">
    <b style="font-size:13px">YAGA — Monto por viaje</b><br><br>
    <span style="color:darkgreen">&#11044;</span> $200+ MXN<br>
    <span style="color:green">&#11044;</span> $130 – $199 MXN<br>
    <span style="color:orange">&#11044;</span> $90 – $129 MXN<br>
    <span style="color:red">&#11044;</span> &lt; $90 MXN<br>
    <hr style="margin:8px 0">
    <span style="color:#555">Promedio historico: <b>$72.94</b></span>
</div>
"""
mapa.get_root().html.add_child(folium.Element(legend_html))

# ── Stats en header ───────────────────────────────────────────────────────────
total_viajes   = len(df_map)
ingreso_total  = df_map["monto_bruto"].sum()
promedio       = df_map["monto_bruto"].mean()
distancia_tot  = df_map["distancia_km"].sum()
fecha_min      = df_map["fecha_local"].min()[:10]
fecha_max      = df_map["fecha_local"].max()[:10]

stats_html = f"""
<div style="
    position: fixed; top: 15px; left: 50%; transform: translateX(-50%);
    z-index: 1000; background: rgba(26,26,46,0.92); color: white;
    padding: 10px 24px; border-radius: 20px; font-family: monospace;
    font-size: 12px; display: flex; gap: 24px; white-space: nowrap;
    box-shadow: 0 2px 12px rgba(0,0,0,0.4);
">
    <span>&#128205; <b>{total_viajes:,}</b> viajes</span>
    <span>&#128178; <b>${ingreso_total:,.0f}</b> MXN total</span>
    <span>&#8709; <b>${promedio:.2f}</b> / viaje</span>
    <span>&#128663; <b>{distancia_tot:,.0f}</b> km recorridos</span>
    <span>&#128197; {fecha_min} → {fecha_max}</span>
</div>
"""
mapa.get_root().html.add_child(folium.Element(stats_html))

# ── Control de capas ──────────────────────────────────────────────────────────
folium.LayerControl(collapsed=False).add_to(mapa)

# ── Guardar ───────────────────────────────────────────────────────────────────
mapa.save(MAP_OUT)
print(f"\nMapa guardado en: {MAP_OUT}")
print(f"  Viajes mapeados:  {total_viajes:,}")
print(f"  Ingreso total:    ${ingreso_total:,.2f} MXN")
print(f"  Promedio/viaje:   ${promedio:.2f} MXN")
print(f"  Distancia total:  {distancia_tot:,.0f} km")
print(f"  Periodo:          {fecha_min} → {fecha_max}")
