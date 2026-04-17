# © YAGA Project — Todos los derechos reservados
"""
Vistas Django para análisis de homicidios dolosos por entidad (1990-2023).
Equivalente al notebook carreras.ipynb adaptado a Django + dataset de homicidios.
"""

from django.shortcuts import render
from django.http import JsonResponse, HttpRequest

from .utils.homicidios_utils import (
    cargar_datos,
    obtener_ubicacion,
    estado_mas_cercano,
    tendencia_estado,
    resumen_dataframe,
)


def index(request: HttpRequest):
    """Vista principal: carga datos, detecta ubicación y muestra análisis."""
    error = None
    df = None
    resumen = {}
    ubicacion = None
    estados_cercanos = []
    tendencia = []
    estado_seleccionado = ""

    try:
        df = cargar_datos()
        resumen = resumen_dataframe(df)
    except Exception as exc:
        error = f"No se pudieron cargar los datos: {exc}"

    if df is not None:
        # Obtener IP real del cliente (detrás de proxies)
        ip_cliente = (
            request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
            or request.META.get("REMOTE_ADDR", "")
        )
        # En local (127.0.0.1) ip-api devuelve ubicación del servidor, está bien para pruebas
        ubicacion = obtener_ubicacion(ip_cliente)

        estados_cercanos = estado_mas_cercano(ubicacion, n=3)

        # Estado más cercano como selección por defecto
        estado_seleccionado = request.GET.get("estado", "")
        if not estado_seleccionado and estados_cercanos:
            estado_seleccionado = estados_cercanos[0]["estado"]

        if estado_seleccionado:
            tendencia = tendencia_estado(df, estado_seleccionado)

    # Convertir DataFrame a HTML para mostrar en template
    tabla_html = ""
    if df is not None and "Entidad" in df.columns:
        anios = [c for c in df.columns if c != "Entidad" and str(c).isdigit()]
        # Mostrar últimos 10 años para que la tabla no sea enorme
        anios_mostrar = sorted(anios)[-10:]
        cols = ["Entidad"] + anios_mostrar
        tabla_html = df[cols].to_html(
            index=False,
            classes="tabla-homicidios",
            border=0,
            na_rep="—",
        )

    return render(request, "xray/homicidios.html", {
        "error": error,
        "ubicacion": ubicacion,
        "estados_cercanos": estados_cercanos,
        "estado_seleccionado": estado_seleccionado,
        "tendencia": tendencia,
        "resumen": resumen,
        "tabla_html": tabla_html,
        "todos_estados": list(estados_cercanos),
    })


def api_tendencia(request: HttpRequest):
    """JSON API: tendencia de homicidios para un estado dado."""
    estado = request.GET.get("estado", "")
    if not estado:
        return JsonResponse({"error": "Parámetro 'estado' requerido"}, status=400)

    try:
        df = cargar_datos()
        datos = tendencia_estado(df, estado)
        return JsonResponse({"estado": estado, "datos": datos})
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)
