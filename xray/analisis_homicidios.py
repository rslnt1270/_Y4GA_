#!/usr/bin/env python3
# © YAGA Project — Todos los derechos reservados
"""
Script standalone: análisis de Homicidios Dolosos México 1990-2023.
Equivalente al notebook carreras.ipynb pero para el dataset de homicidios.

Uso:
    python analisis_homicidios.py
    python analisis_homicidios.py --descarga   # forza re-descarga del CSV
"""

import sys
import os

# Agregar el directorio del app al path para importar utils
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import requests
from utils.homicidios_utils import (
    cargar_datos,
    obtener_ubicacion,
    estado_mas_cercano,
    total_por_estado,
    historico_nacional,
    tabla_completa_estados_anios,
    resumen_general,
)

pd.set_option("display.max_rows", 40)
pd.set_option("display.width", 120)
pd.set_option("display.float_format", "{:,.0f}".format)


def separador(titulo: str) -> None:
    ancho = 70
    print("\n" + "═" * ancho)
    print(f"  {titulo}")
    print("═" * ancho)


def main():
    forzar = "--descarga" in sys.argv

    # ── Cargar datos ──────────────────────────────────────────────────────────
    print("Cargando dataset de Homicidios Dolosos México 1990-2023...")
    try:
        df = cargar_datos(forzar_descarga=forzar)
    except RuntimeError as e:
        print(f"\nERROR: {e}")
        sys.exit(1)

    print(f"  → {len(df):,} registros cargados")
    print(f"  → Columnas: {list(df.columns)}")
    print(f"  → Años: {sorted(df['Año'].dropna().unique().astype(int).tolist())}")

    # ── Resumen general ───────────────────────────────────────────────────────
    res = resumen_general(df)
    separador("RESUMEN GENERAL")
    print(f"  Total homicidios 1990-2023 : {res['total_periodo']:>10,}")
    print(f"  Año más violento           : {res['anio_max']}  ({res['total_anio_max']:,} casos)")
    print(f"  Año menos violento         : {res['anio_min']}  ({res['total_anio_min']:,} casos)")
    print(f"  Estado más afectado        : {res['estado_mas_alto']}  ({res['total_estado_max']:,} casos)")

    # ── Histórico nacional por año ────────────────────────────────────────────
    separador("HISTÓRICO NACIONAL — Total por año")
    hist = historico_nacional(df)
    print(hist.to_string(index=False))

    # ── Ranking estados ───────────────────────────────────────────────────────
    separador("TASA TOTAL DE HOMICIDIOS POR ESTADO (1990-2023)")
    estados = total_por_estado(df)
    print(estados[["Ranking", "Entidad", "Total_1990_2023", "Promedio_anual"]].to_string(index=False))

    # ── Tabla pivot: estado × años ────────────────────────────────────────────
    separador("HOMICIDIOS POR ESTADO — ÚLTIMOS 10 AÑOS")
    pivot = tabla_completa_estados_anios(df)
    anio_cols = sorted([c for c in pivot.columns
                        if c not in ("Entidad", "Total_acumulado") and c.isdigit()])
    cols_mostrar = ["Entidad"] + anio_cols[-10:] + ["Total_acumulado"]
    print(pivot[cols_mostrar].to_string(index=False))

    # ── Geolocalización (igual que notebook) ──────────────────────────────────
    separador("TU UBICACIÓN Y ESTADOS MÁS CERCANOS")
    print("  Detectando ubicación por IP...")
    mi_ubicacion = obtener_ubicacion()
    print(f"  Tu ubicación: {mi_ubicacion}")
    print()
    cercanos = estado_mas_cercano(mi_ubicacion, n=5)
    for e in cercanos:
        total_e = estados.loc[
            estados["Entidad"].str.contains(e["estado"].split()[0], case=False, na=False),
            "Total_1990_2023"
        ]
        total_str = f"{int(total_e.values[0]):,}" if not total_e.empty else "—"
        print(f"  {e['estado']:<25} {e['distancia_km']:>7} km   |   Total homicidios: {total_str}")

    print()


if __name__ == "__main__":
    main()
