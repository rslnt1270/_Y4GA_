# © YAGA Project — Todos los derechos reservados
"""
import_historico.py — Importa todos los JSONs de Uber al usuario y.ortega
Uso: python3 import_historico.py
"""
import json, re, glob, os, urllib.parse
from datetime import datetime, timezone
from typing import Optional

# ── Config ──────────────────────────────────────────────────────────────────
CONDUCTOR_ID = "61f22076-69b7-41d0-ab79-8769a19181ff"
JSON_DIR     = os.path.join(os.path.dirname(__file__), "data_science/Extraction_trafic_data_Uber")
DB_URL       = "postgresql://yaga_user:Yaga2026SecurePass@localhost:5432/yaga_db"

# ── Parsers (misma lógica que historico_service.py) ─────────────────────────

def _parse_monto(formatted: str) -> Optional[float]:
    if not formatted:
        return None
    cleaned = formatted.replace("MXN", "").replace("$", "").strip()
    if "," in cleaned and "." not in cleaned:
        cleaned = cleaned.replace(",", ".")
    elif "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None

def _parse_duracion(formatted: str) -> Optional[float]:
    if not formatted:
        return None
    total = 0.0
    h = re.search(r'(\d+)\s*h', formatted)
    m = re.search(r'(\d+)\s*min', formatted)
    s = re.search(r'(\d+)\s*seg', formatted)
    if h: total += int(h.group(1)) * 60
    if m: total += int(m.group(1))
    if s: total += int(s.group(1)) / 60
    return round(total, 2) if total > 0 else None

def _parse_distancia(formatted: str) -> Optional[float]:
    if not formatted:
        return None
    m = re.search(r'([\d.,]+)\s*km', formatted)
    if m:
        return float(m.group(1).replace(",", "."))
    return None

def _parse_coords(map_url: str):
    if not map_url:
        return None, None
    decoded = urllib.parse.unquote(map_url)
    lat_m = re.search(r'lat[=:](-?\d+\.\d+)', decoded)
    lng_m = re.search(r'lng[=:](-?\d+\.\d+)', decoded)
    if lat_m and lng_m:
        return float(lat_m.group(1)), float(lng_m.group(1))
    return None, None

def normalizar_viaje(raw: dict) -> Optional[dict]:
    if raw.get("type") != "TRIP" or raw.get("status") != "COMPLETED":
        return None
    meta = raw.get("tripMetaData") or {}
    lat, lng = _parse_coords(meta.get("mapUrl", ""))
    ts    = raw.get("recognizedAt")
    fecha = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None
    monto = _parse_monto(raw.get("formattedTotal", ""))
    if not monto:
        return None
    dist  = _parse_distancia(meta.get("formattedDistance", ""))
    dur   = _parse_duracion(meta.get("formattedDuration", ""))
    efic  = round(monto / dist, 2) if dist and dist > 0 else None
    return {
        "trip_id":      raw.get("uuid"),
        "conductor_id": CONDUCTOR_ID,
        "fecha_local":  fecha,
        "monto_bruto":  monto,
        "duracion_min": dur,
        "distancia_km": dist,
        "eficiencia_km": efic,
        "plataforma":   raw.get("activityTitle", "UberX"),
        "origen":       meta.get("pickupAddress"),
        "destino":      meta.get("dropOffAddress"),
        "lat":          lat,
        "lng":          lng,
    }

# ── Import ───────────────────────────────────────────────────────────────────

def main():
    try:
        import asyncpg
        import asyncio
    except ImportError:
        print("Installing asyncpg...")
        os.system("pip3 install asyncpg --quiet")
        import asyncpg
        import asyncio

    async def run():
        conn = await asyncpg.connect(DB_URL)
        files = sorted(glob.glob(os.path.join(JSON_DIR, "*_detallado.json")))
        all_viajes = []
        seen = set()
        for fpath in files:
            with open(fpath) as f:
                data = json.load(f)
            for raw in data:
                v = normalizar_viaje(raw)
                if v and v["trip_id"] and v["trip_id"] not in seen:
                    seen.add(v["trip_id"])
                    all_viajes.append(v)

        print(f"Total viajes únicos a importar: {len(all_viajes)}")
        insertados = duplicados = 0
        for v in all_viajes:
            result = await conn.execute(
                """
                INSERT INTO viajes_historicos
                    (trip_id, conductor_id, fecha_local, monto_bruto, duracion_min,
                     distancia_km, eficiencia_km, plataforma, origen, destino, lat, lng)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                ON CONFLICT (trip_id) DO UPDATE SET
                    conductor_id  = EXCLUDED.conductor_id,
                    lat = COALESCE(viajes_historicos.lat, EXCLUDED.lat),
                    lng = COALESCE(viajes_historicos.lng, EXCLUDED.lng)
                """,
                v["trip_id"], v["conductor_id"], v["fecha_local"], v["monto_bruto"],
                v["duracion_min"], v["distancia_km"], v["eficiencia_km"],
                v["plataforma"], v["origen"], v["destino"], v["lat"], v["lng"],
            )
            if "INSERT 0 1" in str(result):
                insertados += 1
            else:
                duplicados += 1

        stats = await conn.fetchrow(
            "SELECT COUNT(*) as total, COUNT(lat) as con_coords FROM viajes_historicos WHERE conductor_id=$1",
            CONDUCTOR_ID
        )
        print(f"Insertados: {insertados}  Duplicados: {duplicados}")
        print(f"Total en DB: {stats['total']}  Con coordenadas: {stats['con_coords']}")
        await conn.close()

    import asyncio
    asyncio.run(run())

if __name__ == "__main__":
    main()
