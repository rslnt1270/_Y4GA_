# © YAGA Project — Todos los derechos reservados
"""
Descarga el dataset de Homicidios Dolosos en México (1990–2023) desde datamx.io.
Fuente: https://datamx.io/dataset/homicidios-dolosos-registrados-en-mexico-por-entidad-1990-2023

Dependencias: pip install requests pandas openpyxl
"""

import os
import sys
import requests
import pandas as pd

DATASET_SLUG = "homicidios-dolosos-registrados-en-mexico-por-entidad-1990-2023"
CKAN_API = "https://datamx.io/api/3/action/package_show"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "datasets")
TIMEOUT = 60  # segundos


def obtener_recursos(slug: str) -> list[dict]:
    """Consulta la API CKAN de datamx.io y devuelve los recursos del dataset."""
    resp = requests.get(CKAN_API, params={"id": slug}, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(f"API error: {data.get('error', {})}")
    return data["result"]["resources"]


def descargar_recurso(url: str, nombre: str, destino_dir: str) -> str:
    """Descarga un archivo con barra de progreso y lo guarda en destino_dir."""
    os.makedirs(destino_dir, exist_ok=True)
    ruta = os.path.join(destino_dir, nombre)

    print(f"  Descargando: {nombre}")
    with requests.get(url, stream=True, timeout=TIMEOUT) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        descargado = 0
        with open(ruta, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
                descargado += len(chunk)
                if total:
                    pct = descargado / total * 100
                    print(f"\r  {pct:.1f}%", end="", flush=True)
    print()
    return ruta


def cargar_dataframe(ruta: str) -> pd.DataFrame:
    """Carga el archivo descargado en un DataFrame según su extensión."""
    ext = os.path.splitext(ruta)[1].lower()
    if ext == ".csv":
        return pd.read_csv(ruta, encoding="utf-8-sig")
    if ext in (".xlsx", ".xls"):
        return pd.read_excel(ruta)
    if ext == ".json":
        return pd.read_json(ruta)
    raise ValueError(f"Formato no soportado: {ext}")


def main() -> None:
    print("=== Descarga: Homicidios Dolosos México 1990–2023 ===\n")

    print("Consultando recursos en datamx.io...")
    try:
        recursos = obtener_recursos(DATASET_SLUG)
    except Exception as exc:
        print(f"ERROR al consultar la API: {exc}")
        sys.exit(1)

    print(f"Recursos encontrados: {len(recursos)}\n")
    for i, r in enumerate(recursos):
        print(f"  [{i}] {r.get('name', 'sin nombre')} — {r.get('format', '?')} — {r['url']}")
    print()

    # Descargar todos los recursos tabulares (CSV / Excel)
    formatos_tabular = {"csv", "xlsx", "xls", "json"}
    descargados: list[tuple[str, str]] = []

    for recurso in recursos:
        fmt = recurso.get("format", "").lower()
        url = recurso.get("url", "")
        nombre = recurso.get("name") or os.path.basename(url) or f"recurso.{fmt}"

        # Normalizar extensión en el nombre
        if fmt and not nombre.lower().endswith(f".{fmt}"):
            nombre = f"{nombre}.{fmt}"

        if fmt in formatos_tabular:
            try:
                ruta = descargar_recurso(url, nombre, OUTPUT_DIR)
                descargados.append((ruta, fmt))
            except Exception as exc:
                print(f"  ADVERTENCIA: no se pudo descargar {nombre}: {exc}")

    if not descargados:
        print("No se encontraron recursos tabulares para descargar.")
        sys.exit(1)

    # Cargar y mostrar resumen del primer DataFrame
    ruta_principal, _ = descargados[0]
    print(f"\nCargando DataFrame desde: {os.path.basename(ruta_principal)}")
    df = cargar_dataframe(ruta_principal)

    print(f"\nForma: {df.shape[0]:,} filas × {df.shape[1]} columnas")
    print(f"Columnas: {list(df.columns)}")
    print(f"\nPrimeras 5 filas:\n{df.head()}")
    print(f"\nTipos de datos:\n{df.dtypes}")
    print(f"\nEstadísticas descriptivas:\n{df.describe(include='all').to_string()}")

    print(f"\nArchivos guardados en: {OUTPUT_DIR}/")
    for ruta, _ in descargados:
        print(f"  {os.path.basename(ruta)}")


if __name__ == "__main__":
    main()
