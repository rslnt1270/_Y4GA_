import json
import pandas as pd
from playwright.sync_api import sync_playwright
import os

# =========================================================================
# ⚠️ AVISO LEGAL / DISCLAIMER PARA USUARIOS EXTERNOS
# =========================================================================
# Este script es una herramienta de extracción de datos personales para uso 
# estrictamente individual. El autor no se hace responsable del mal uso, 
# la pérdida de acceso a la cuenta o cualquier violación a los términos de 
# servicio de Uber. Úselo bajo su propio riesgo y discreción.
# =========================================================================

viajes_acumulados = []
# Carpeta donde se guardarán tus credenciales (Cookies)
SESSION_FILE = "uber_session/gs_session.json"

def interceptar_trafico(response):
    global viajes_acumulados
    if "getWebActivityFeed" in response.url and response.status == 200:
        try:
            datos_json = response.json()
            nuevos_viajes = datos_json.get('data', {}).get('activities', [])
            if nuevos_viajes:
                viajes_acumulados.extend(nuevos_viajes)
                print(f"✅ ¡Pescados {len(nuevos_viajes)} viajes! (Total: {len(viajes_acumulados)})")
        except:
            pass

def ejecutar_bot():
    if not os.path.exists("uber_session"):
        os.makedirs("uber_session")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        
        # Intentamos cargar la sesión previa si existe
        if os.path.exists(SESSION_FILE):
            print("🔐 Cargando sesión existente... (No deberías necesitar login)")
            context = browser.new_context(storage_state=SESSION_FILE)
        else:
            print("🆕 No se encontró sesión previa. Deberás loguearte esta vez.")
            context = browser.new_context()

        page = context.new_page()
        page.on("response", interceptar_trafico)

        print("🌐 Entrando a Uber Actividades...")
        page.goto("https://drivers.uber.com/earnings/activities")

        print("\n💡 INSTRUCCIONES:")
        print("1. Si la sesión expiró, inicia sesión una última vez.")
        print("2. Navega por tus semanas para capturar los datos.")
        print("3. Al terminar, presiona ENTER en esta terminal.")

        input("\n⏳ PRESIONA 'ENTER' PARA GUARDAR DATOS Y ACTUALIZAR SESIÓN...")

        # 💾 GUARDAR SESIÓN: Esto evita el login la próxima vez
        context.storage_state(path=SESSION_FILE)
        print(f"✔️ Sesión guardada en {SESSION_FILE}")

        if viajes_acumulados:
            df = pd.DataFrame(viajes_acumulados)
            df.to_csv("viajes_uber_bruto.csv", index=False)
            with open("viajes_uber_detallados.json", "w", encoding="utf-8") as f:
                json.dump(viajes_acumulados, f, ensure_ascii=False, indent=4)
            print(f"🏆 Proceso finalizado. {len(df)} viajes guardados.")
        
        browser.close()

if __name__ == "__main__":
    ejecutar_bot()
