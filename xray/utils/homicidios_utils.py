# © YAGA Project — Todos los derechos reservados
"""
Análisis de Homicidios Dolosos por Entidad 1990-2023 (SESNSP / datamx.io).

Formato esperado del CSV (formato largo SESNSP):
  Año | Entidad | Enero | Febrero | ... | Diciembre | Total
  1997 | Aguascalientes | 3 | 1 | ... | 28
"""

import os
import io
import requests
import pandas as pd
from geopy.distance import geodesic

# ── Fuentes de descarga (datamx.io bloquea user-agents no-browser) ────────────
CKAN_API   = "https://datamx.io/api/3/action/package_show"
DATASET_ID = "homicidios-dolosos-registrados-en-mexico-por-entidad-1990-2023"
HEADERS_BROWSER = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-MX,es;q=0.9",
}

DATA_DIR   = os.path.join(os.path.dirname(__file__), "..", "data")
CSV_CACHE  = os.path.join(DATA_DIR, "homicidios.csv")
TIMEOUT    = 40

MESES = ["Enero","Febrero","Marzo","Abril","Mayo","Junio",
         "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]

# Coordenadas capitales — para detectar estado más cercano al usuario
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


# ─────────────────────────────────────────────────────────────────────────────
# 1. Descarga y carga del CSV
# ─────────────────────────────────────────────────────────────────────────────

def cargar_datos(forzar_descarga: bool = False) -> pd.DataFrame:
    """Carga CSV desde cache local; descarga si no existe o se fuerza."""
    os.makedirs(DATA_DIR, exist_ok=True)
    if forzar_descarga or not os.path.exists(CSV_CACHE):
        _descargar_csv()
    df = pd.read_csv(CSV_CACHE, encoding="utf-8-sig")
    return _normalizar(df)


def _descargar_csv() -> None:
    """Intenta datamx.io CKAN API con headers de navegador; guarda en CSV_CACHE."""
    session = requests.Session()
    session.headers.update(HEADERS_BROWSER)

    # Paso 1: obtener URL del recurso via CKAN API
    try:
        resp = session.get(CKAN_API, params={"id": DATASET_ID}, timeout=TIMEOUT)
        resp.raise_for_status()
        recursos = resp.json()["result"]["resources"]
    except Exception as e:
        raise RuntimeError(
            f"No se pudo acceder a datamx.io ({e}).\n"
            "Descarga manualmente el CSV desde:\n"
            f"  https://datamx.io/dataset/{DATASET_ID}\n"
            f"y guárdalo en:  {CSV_CACHE}"
        )

    descargado = False
    for recurso in recursos:
        fmt = recurso.get("format", "").lower()
        url = recurso.get("url", "")
        if fmt not in ("csv", "xlsx", "xls") or not url:
            continue
        try:
            r = session.get(url, timeout=TIMEOUT)
            r.raise_for_status()
            # Convertir xlsx a csv si aplica
            if fmt in ("xlsx", "xls"):
                xls = pd.read_excel(io.BytesIO(r.content))
                xls.to_csv(CSV_CACHE, index=False, encoding="utf-8-sig")
            else:
                with open(CSV_CACHE, "wb") as f:
                    f.write(r.content)
            descargado = True
            break
        except Exception:
            continue

    if not descargado:
        raise RuntimeError(
            "No se pudo descargar ningún recurso del dataset.\n"
            "Descarga manualmente el CSV y guárdalo en:\n"
            f"  {CSV_CACHE}"
        )


def _normalizar(df: pd.DataFrame) -> pd.DataFrame:
    """
    Estandariza el DataFrame al formato largo SESNSP:
      Año | Entidad | Enero…Diciembre | Total
    Detecta y renombra columnas clave.
    """
    # Renombrar columna de entidad
    for col in df.columns:
        if "entidad" in col.lower() or "estado" in col.lower():
            df = df.rename(columns={col: "Entidad"})
            break

    # Renombrar columna de año
    for col in df.columns:
        if col.lower() in ("año", "anio", "year", "a\xf1o"):
            df = df.rename(columns={col: "Año"})
            break

    # Renombrar columna Total si existe con variante
    for col in df.columns:
        if col.lower() in ("total", "total anual", "total_anual"):
            df = df.rename(columns={col: "Total"})
            break

    # Limpiar strings
    if "Entidad" in df.columns:
        df["Entidad"] = df["Entidad"].astype(str).str.strip()

    # Si no hay columna Total, calcularla sumando meses presentes
    if "Total" not in df.columns:
        meses_presentes = [m for m in MESES if m in df.columns]
        if meses_presentes:
            df["Total"] = df[meses_presentes].sum(axis=1)

    # Convertir Año y Total a numérico
    for col in ("Año", "Total"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Filtrar filas sin entidad real (totales nacionales en filas)
    if "Entidad" in df.columns:
        df = df[~df["Entidad"].str.lower().str.contains(
            r"total|nacional|república|nan", na=True
        )]

    return df.dropna(subset=["Entidad"])


# ─────────────────────────────────────────────────────────────────────────────
# 2. Análisis principal
# ─────────────────────────────────────────────────────────────────────────────

def total_por_estado(df: pd.DataFrame) -> pd.DataFrame:
    """
    Tabla: Estado | Total_homicidios (suma 1990-2023) | Promedio_anual
    Ordenada de mayor a menor.
    """
    resumen = (
        df.groupby("Entidad")["Total"]
        .sum()
        .reset_index()
        .rename(columns={"Total": "Total_1990_2023"})
    )
    n_anios = df["Año"].nunique() if "Año" in df.columns else 1
    resumen["Promedio_anual"] = (resumen["Total_1990_2023"] / n_anios).round(1)
    resumen["Ranking"] = resumen["Total_1990_2023"].rank(ascending=False).astype(int)
    return resumen.sort_values("Total_1990_2023", ascending=False).reset_index(drop=True)


def historico_nacional(df: pd.DataFrame) -> pd.DataFrame:
    """
    Tabla: Año | Total_nacional | Variacion_%
    Serie de tiempo nacional (suma de todos los estados por año).
    """
    if "Año" not in df.columns:
        return pd.DataFrame()

    hist = (
        df.groupby("Año")["Total"]
        .sum()
        .reset_index()
        .rename(columns={"Total": "Total_nacional"})
        .sort_values("Año")
    )
    hist["Variacion_pct"] = hist["Total_nacional"].pct_change().mul(100).round(1)
    return hist.reset_index(drop=True)


def tabla_completa_estados_anios(df: pd.DataFrame) -> pd.DataFrame:
    """
    Pivot: filas=Entidad, columnas=Año, valores=Total.
    Agrega columna 'Total_acumulado'.
    """
    if "Año" not in df.columns:
        return pd.DataFrame()

    pivot = df.pivot_table(
        index="Entidad", columns="Año", values="Total", aggfunc="sum"
    ).reset_index()
    pivot.columns.name = None
    pivot.columns = ["Entidad"] + [str(int(c)) for c in pivot.columns[1:]]

    anio_cols = [c for c in pivot.columns if c != "Entidad"]
    pivot["Total_acumulado"] = pivot[anio_cols].sum(axis=1).astype(int)
    return pivot.sort_values("Total_acumulado", ascending=False).reset_index(drop=True)


def resumen_general(df: pd.DataFrame) -> dict:
    """Métricas de resumen para las tarjetas del dashboard."""
    if df.empty:
        return {}

    hist = historico_nacional(df)
    por_estado = total_por_estado(df)

    anio_max = int(hist.loc[hist["Total_nacional"].idxmax(), "Año"])
    anio_min = int(hist.loc[hist["Total_nacional"].idxmin(), "Año"])
    estado_max = por_estado.iloc[0]["Entidad"]
    total_periodo = int(por_estado["Total_1990_2023"].sum())

    return {
        "total_periodo":    total_periodo,
        "n_estados":        len(por_estado),
        "anio_max":         anio_max,
        "total_anio_max":   int(hist.loc[hist["Año"] == anio_max, "Total_nacional"].values[0]),
        "anio_min":         anio_min,
        "total_anio_min":   int(hist.loc[hist["Año"] == anio_min, "Total_nacional"].values[0]),
        "estado_mas_alto":  estado_max,
        "total_estado_max": int(por_estado.iloc[0]["Total_1990_2023"]),
        "anios":            sorted(df["Año"].dropna().unique().astype(int).tolist()),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. Geolocalización (igual que notebook carreras)
# ─────────────────────────────────────────────────────────────────────────────

def obtener_ubicacion(ip: str = "") -> tuple[float, float]:
    try:
        url = f"http://ip-api.com/json/{ip}" if ip else "http://ip-api.com/json/"
        data = requests.get(url, timeout=5).json()
        return (float(data["lat"]), float(data["lon"]))
    except Exception:
        return (19.4326, -99.1332)


def estado_mas_cercano(ubicacion: tuple[float, float], n: int = 3) -> list[dict]:
    res = [
        {"estado": e, "distancia_km": round(geodesic(ubicacion, c).km, 1)}
        for e, c in CAPITALES.items()
    ]
    return sorted(res, key=lambda x: x["distancia_km"])[:n]
