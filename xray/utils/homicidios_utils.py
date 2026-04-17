# © YAGA Project — Todos los derechos reservados
"""
Funciones de análisis de homicidios dolosos por entidad (1990-2023).
Equivalente al notebook carreras.ipynb pero para el dataset de homicidios.
"""

import os
import requests
import pandas as pd
from geopy.distance import geodesic

# Fuente datamx.io — CKAN
DATASET_SLUG = "homicidios-dolosos-registrados-en-mexico-por-entidad-1990-2023"
CKAN_API = "https://datamx.io/api/3/action/package_show"
CSV_CACHE = os.path.join(os.path.dirname(__file__), "..", "data", "homicidios.csv")
TIMEOUT = 30

# Coordenadas de capitales de estados (para calcular estado más cercano al usuario)
CAPITALES = {
    "Aguascalientes":      (21.8818, -102.2916),
    "Baja California":     (32.5027, -117.0037),
    "Baja California Sur": (24.1426, -110.3128),
    "Campeche":            (19.8301,  -90.5349),
    "Chiapas":             (16.7370,  -93.1153),
    "Chihuahua":           (28.6353, -106.0889),
    "Ciudad de México":    (19.4326,  -99.1332),
    "Coahuila":            (25.4232, -100.9963),
    "Colima":              (19.2452, -103.7241),
    "Durango":             (24.0277, -104.6532),
    "Guanajuato":          (21.0190, -101.2574),
    "Guerrero":            (17.5506,  -99.5021),
    "Hidalgo":             (20.0911,  -98.7624),
    "Jalisco":             (20.6597, -103.3496),
    "México":              (19.2826,  -99.6557),
    "Michoacán":           (19.6815, -101.2036),
    "Morelos":             (18.9242,  -99.2216),
    "Nayarit":             (21.5085, -104.8952),
    "Nuevo León":          (25.6714, -100.3090),
    "Oaxaca":              (17.0732,  -96.7266),
    "Puebla":              (19.0414,  -98.2063),
    "Querétaro":           (20.5888, -100.3899),
    "Quintana Roo":        (21.1743,  -86.8466),
    "San Luis Potosí":     (22.1565, -100.9855),
    "Sinaloa":             (24.8091, -107.3940),
    "Sonora":              (29.0892, -110.9608),
    "Tabasco":             (17.9869,  -92.9303),
    "Tamaulipas":          (23.7369,  -99.1411),
    "Tlaxcala":            (19.3181,  -98.2375),
    "Veracruz":            (19.1738,  -96.1342),
    "Yucatán":             (20.9674,  -89.6237),
    "Zacatecas":           (22.7709, -102.5832),
}


# ── 1. Ubicación del usuario por IP ──────────────────────────────────────────
def obtener_ubicacion(ip: str = "") -> tuple[float, float]:
    """Devuelve (lat, lon) detectada por IP. Compatible con notebook carreras.ipynb."""
    try:
        url = f"http://ip-api.com/json/{ip}" if ip else "http://ip-api.com/json/"
        data = requests.get(url, timeout=5).json()
        return (data["lat"], data["lon"])
    except Exception:
        return (19.4326, -99.1332)  # fallback: Ciudad de México


# ── 2. Cargar o descargar el CSV de homicidios ────────────────────────────────
def cargar_datos() -> pd.DataFrame:
    """Carga desde cache local; si no existe, descarga de datamx.io."""
    os.makedirs(os.path.dirname(CSV_CACHE), exist_ok=True)

    if not os.path.exists(CSV_CACHE):
        _descargar_csv()

    df = pd.read_csv(CSV_CACHE, encoding="utf-8-sig")
    return _normalizar(df)


def _descargar_csv() -> None:
    resp = requests.get(CKAN_API, params={"id": DATASET_SLUG}, timeout=TIMEOUT)
    resp.raise_for_status()
    recursos = resp.json()["result"]["resources"]

    for r in recursos:
        fmt = r.get("format", "").lower()
        if fmt in ("csv", "xlsx", "xls"):
            data = requests.get(r["url"], timeout=TIMEOUT)
            data.raise_for_status()
            with open(CSV_CACHE, "wb") as f:
                f.write(data.content)
            return

    raise RuntimeError("No se encontró recurso CSV/Excel en el dataset.")


def _normalizar(df: pd.DataFrame) -> pd.DataFrame:
    """Detecta formato wide/long y estandariza a wide con columna 'Entidad'."""
    # Normalizar nombre de columna de entidad
    for col in df.columns:
        col_lower = col.lower().strip()
        if "entidad" in col_lower or "estado" in col_lower:
            df = df.rename(columns={col: "Entidad"})
            break

    # Limpiar nombre de entidad
    if "Entidad" in df.columns:
        df["Entidad"] = df["Entidad"].astype(str).str.strip()

    # Detectar formato long: si hay columna "Año" y columna de valor
    cols_lower = {c.lower(): c for c in df.columns}
    if "año" in cols_lower or "anio" in cols_lower:
        anio_col = cols_lower.get("año") or cols_lower.get("anio")
        # Buscar columna de valor numérico
        valor_col = next(
            (c for c in df.columns if c not in ("Entidad", anio_col)
             and pd.api.types.is_numeric_dtype(df[c])),
            None
        )
        if valor_col:
            df = df.pivot_table(
                index="Entidad", columns=anio_col, values=valor_col, aggfunc="sum"
            ).reset_index()
            df.columns.name = None
            df.columns = [str(c) for c in df.columns]

    return df


# ── 3. Estado más cercano al usuario ─────────────────────────────────────────
def estado_mas_cercano(ubicacion_usuario: tuple[float, float], n: int = 3) -> list[dict]:
    """
    Equivalente a universidad_mas_cercana() del notebook.
    Devuelve los n estados más cercanos con distancia en km.
    """
    resultados = []
    for estado, coords in CAPITALES.items():
        distancia = geodesic(ubicacion_usuario, coords).km
        resultados.append({"estado": estado, "coords": coords, "distancia_km": round(distancia, 2)})

    return sorted(resultados, key=lambda x: x["distancia_km"])[:n]


# ── 4. Tendencia de homicidios para un estado ─────────────────────────────────
def tendencia_estado(df: pd.DataFrame, nombre_estado: str) -> list[dict]:
    """
    Devuelve lista [{año, homicidios}] para el estado dado.
    Normaliza nombres parciales (ej. 'Michoacán' matchea 'Michoacán de Ocampo').
    """
    if "Entidad" not in df.columns:
        return []

    mask = df["Entidad"].str.contains(nombre_estado, case=False, na=False)
    filas = df[mask]

    if filas.empty:
        # Intentar match más laxo
        for estado_clave in CAPITALES:
            if nombre_estado.lower() in estado_clave.lower() or estado_clave.lower() in nombre_estado.lower():
                mask = df["Entidad"].str.contains(estado_clave.split()[0], case=False, na=False)
                filas = df[mask]
                break

    if filas.empty:
        return []

    fila = filas.iloc[0]
    anios = [c for c in df.columns if c != "Entidad" and str(c).isdigit()]
    return [{"año": int(a), "homicidios": int(fila[a]) if pd.notna(fila[a]) else 0} for a in sorted(anios)]


# ── 5. Resumen estadístico del dataframe completo ────────────────────────────
def resumen_dataframe(df: pd.DataFrame) -> dict:
    anios = [c for c in df.columns if c != "Entidad" and str(c).isdigit()]
    if not anios or "Entidad" not in df.columns:
        return {}

    totales_por_anio = df[anios].sum()
    anio_max = str(totales_por_anio.idxmax())
    anio_min = str(totales_por_anio.idxmin())

    return {
        "total_registros": len(df),
        "anios_disponibles": [int(a) for a in sorted(anios)],
        "anio_mayor_homicidios": anio_max,
        "total_mayor": int(totales_por_anio[anio_max]),
        "anio_menor_homicidios": anio_min,
        "total_menor": int(totales_por_anio[anio_min]),
        "totales_por_anio": {int(a): int(totales_por_anio[a]) for a in anios},
    }
