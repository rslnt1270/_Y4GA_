"""
YAGA PROJECT - Extractor de viajes DiDi
Intercepta el API interno del portal de conductores de DiDi y extrae el historial.

⚠️  AVISO LEGAL
Este script es una herramienta de extracción de datos personales para uso
estrictamente individual. El autor no se hace responsable del mal uso,
la pérdida de acceso a la cuenta o cualquier violación a los términos de
servicio de DiDi. Úselo bajo su propio riesgo y discreción.

REQUISITOS:
  pip install playwright pandas
  playwright install chromium

USO:
  python didi_extraction.py
"""

import json
import time
import os
import re
from datetime import datetime, timezone

# ── Rutas ──────────────────────────────────────────────────────────────────────
SESSION_FILE = "uber_session/didi_session.json"
OUTPUT_JSON  = f"didi_viajes_{datetime.now().strftime('%Y_%m')}_detallado.json"
OUTPUT_CSV   = f"didi_viajes_{datetime.now().strftime('%Y_%m')}_bruto.csv"

# ── Endpoints conocidos del portal DiDi (se actualizan por interceptacion) ────
# DiDi usa /api/passenger o /api/driver para el historial
DIDI_TRIP_ENDPOINTS = [
    "getOrderHistoryList",
    "getTripHistory",
    "order/history",
    "driverOrderHistory",
    "earningHistory",
    "activityList",
    "getDriverOrderList",
]

viajes_acumulados = []


def interceptar_respuesta(response):
    """Captura respuestas del API de DiDi que contengan historial de viajes."""
    global viajes_acumulados

    url = response.url
    if response.status != 200:
        return

    # Filtrar por endpoints conocidos o por contenido de la URL
    url_lower = url.lower()
    es_endpoint_viajes = any(ep.lower() in url_lower for ep in DIDI_TRIP_ENDPOINTS)

    # También buscar por patrones generales de historial
    es_historial = any(kw in url_lower for kw in [
        "history", "order", "trip", "earning", "driver", "viaje"
    ])

    if not (es_endpoint_viajes or es_historial):
        return

    # Intentar parsear el JSON
    try:
        content_type = response.headers.get("content-type", "")
        if "json" not in content_type and "javascript" not in content_type:
            return

        datos = response.json()
    except Exception:
        return

    # Buscar viajes en la respuesta (DiDi puede anidar en data.list, data.trips, etc.)
    nuevos = _extraer_viajes_de_respuesta(datos)
    if nuevos:
        viajes_acumulados.extend(nuevos)
        print(f"  ✅ {len(nuevos)} viajes capturados desde: {url[:80]}...")
        print(f"     Total acumulado: {len(viajes_acumulados)}")


def _extraer_viajes_de_respuesta(datos: dict | list) -> list:
    """
    DiDi puede devolver viajes en distintas estructuras. Busca recursivamente
    listas que parezcan contener viajes.
    """
    candidatos = []

    def buscar(obj, profundidad=0):
        if profundidad > 5:
            return
        if isinstance(obj, list):
            if obj and isinstance(obj[0], dict) and _parece_viaje(obj[0]):
                candidatos.extend(obj)
            else:
                for item in obj[:3]:
                    buscar(item, profundidad + 1)
        elif isinstance(obj, dict):
            # Claves comunes donde DiDi guarda listas de viajes
            for clave in ["list", "trips", "orders", "data", "result",
                          "items", "records", "orderList", "tripList",
                          "historyList", "earningList"]:
                if clave in obj:
                    buscar(obj[clave], profundidad + 1)

    buscar(datos)
    return candidatos


def _parece_viaje(obj: dict) -> bool:
    """Heurística: ¿este dict luce como un viaje?"""
    claves = set(k.lower() for k in obj.keys())
    indicadores = {
        "price", "income", "fare", "monto", "amount",
        "distance", "duration", "time", "address",
        "origin", "dest", "start", "end", "lat", "lng",
        "order", "trip", "ride"
    }
    return len(claves & indicadores) >= 2


# ── Ejecutar bot ───────────────────────────────────────────────────────────────
def ejecutar_bot():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("❌ Playwright no instalado.")
        print("   Ejecuta: pip install playwright && playwright install chromium")
        return

    if not os.path.exists("uber_session"):
        os.makedirs("uber_session")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)

        # Cargar sesion previa si existe
        if os.path.exists(SESSION_FILE):
            print("🔐 Cargando sesión DiDi guardada…")
            context = browser.new_context(storage_state=SESSION_FILE)
        else:
            print("🆕 Primera vez — necesitarás iniciar sesión en DiDi.")
            context = browser.new_context()

        page = context.new_page()
        page.on("response", interceptar_respuesta)

        print("\n🌐 Abriendo portal de conductores DiDi…")
        try:
            page.goto("https://driver.didiglobal.com/mx/earnings/history",
                      wait_until="domcontentloaded", timeout=30000)
        except Exception:
            try:
                page.goto("https://driver.didiglobal.com",
                          wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                print(f"  ⚠️  Error al cargar el portal: {e}")

        print("\n💡 INSTRUCCIONES:")
        print("   1. Si la sesión expiró, inicia sesión en DiDi.")
        print("   2. Navega por tu historial de viajes (semana a semana).")
        print("   3. Deja que carguen los datos de cada semana.")
        print("   4. Cuando termines, presiona ENTER aquí.")
        print()
        print(f"   Los viajes capturados aparecerán arriba en tiempo real.")

        input("\n⏳ Presiona ENTER cuando hayas terminado de navegar…\n")

        # Guardar sesion
        context.storage_state(path=SESSION_FILE)
        print(f"✔️  Sesión guardada en {SESSION_FILE}")

        if viajes_acumulados:
            _guardar_resultados()
        else:
            print("\n⚠️  No se capturaron viajes.")
            print("   Asegúrate de navegar por la sección de historial/ganancias.")
            print("   Si DiDi cambió su estructura, contáctanos para actualizar el extractor.")

        browser.close()


def _guardar_resultados():
    # JSON crudo
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(viajes_acumulados, f, ensure_ascii=False, indent=2)
    print(f"\n✅ {len(viajes_acumulados)} viajes guardados en: {OUTPUT_JSON}")

    # Intentar normalizar a CSV para referencia
    try:
        import pandas as pd
        df = pd.DataFrame(viajes_acumulados)
        df.to_csv(OUTPUT_CSV, index=False)
        print(f"   CSV: {OUTPUT_CSV}")
    except Exception:
        pass

    print(f"\n📤 Para importar a YAGA:")
    print(f"   curl -X POST https://y4ga.app/api/v1/historico/import/json \\")
    print(f"        -H 'Authorization: Bearer TU_TOKEN' \\")
    print(f"        -F 'file=@{OUTPUT_JSON}' \\")
    print(f"        -F 'platform=didi'")


if __name__ == "__main__":
    ejecutar_bot()
