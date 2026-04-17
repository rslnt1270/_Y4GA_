# © YAGA Project — Todos los derechos reservados
from django.shortcuts import render
from django.http import JsonResponse, HttpRequest

from .utils.homicidios_utils import (
    cargar_datos,
    obtener_ubicacion,
    estado_mas_cercano,
    total_por_estado,
    historico_nacional,
    tabla_completa_estados_anios,
    resumen_general,
)


def index(request: HttpRequest):
    error = None
    resumen = {}
    tabla_estados_html = ""
    tabla_historico_html = ""
    tabla_pivot_html = ""
    ubicacion = None
    estados_cercanos = []

    try:
        df = cargar_datos()
        resumen = resumen_general(df)

        # ── Tabla 1: total por estado ──────────────────────────────────────
        df_estados = total_por_estado(df)
        tabla_estados_html = df_estados[
            ["Ranking", "Entidad", "Total_1990_2023", "Promedio_anual"]
        ].to_html(
            index=False, classes="tabla-datos", border=0, na_rep="—",
        )

        # ── Tabla 2: histórico nacional por año ───────────────────────────
        df_hist = historico_nacional(df)
        tabla_historico_html = df_hist.to_html(
            index=False, classes="tabla-datos", border=0, na_rep="—",
        )

        # ── Tabla 3: pivot estados × años ─────────────────────────────────
        df_pivot = tabla_completa_estados_anios(df)
        # Solo últimos 10 años + Total para no saturar la pantalla
        anio_cols = sorted([c for c in df_pivot.columns
                            if c not in ("Entidad", "Total_acumulado") and c.isdigit()])
        cols_mostrar = ["Entidad"] + anio_cols[-10:] + ["Total_acumulado"]
        tabla_pivot_html = df_pivot[cols_mostrar].to_html(
            index=False, classes="tabla-datos tabla-scroll", border=0, na_rep="—",
        )

        # ── Geolocalización (igual que notebook carreras) ──────────────────
        ip_cliente = (
            request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
            or request.META.get("REMOTE_ADDR", "")
        )
        ubicacion = obtener_ubicacion(ip_cliente)
        estados_cercanos = estado_mas_cercano(ubicacion, n=5)

        # Pasar datos del histórico para la gráfica CSS
        hist_data = df_hist[["Año", "Total_nacional"]].to_dict("records")
        max_val = max(r["Total_nacional"] for r in hist_data) if hist_data else 1

    except Exception as exc:
        error = str(exc)
        hist_data = []
        max_val = 1

    return render(request, "xray/homicidios.html", {
        "error": error,
        "resumen": resumen,
        "tabla_estados_html":   tabla_estados_html,
        "tabla_historico_html": tabla_historico_html,
        "tabla_pivot_html":     tabla_pivot_html,
        "ubicacion": ubicacion,
        "estados_cercanos": estados_cercanos,
        "hist_data": hist_data if "hist_data" in dir() else [],
        "max_val":   max_val   if "max_val"   in dir() else 1,
    })


def api_datos(request: HttpRequest):
    """API JSON: devuelve histórico nacional en JSON para gráficas externas."""
    try:
        df = cargar_datos()
        hist = historico_nacional(df).to_dict("records")
        estados = total_por_estado(df).to_dict("records")
        return JsonResponse({"historico": hist, "por_estado": estados})
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)
