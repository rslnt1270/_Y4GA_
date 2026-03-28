from fastapi import APIRouter, HTTPException
import re

router = APIRouter()

# Diccionario de intenciones (Lexicon Mexicano)
KEYWORDS = {
    "viaje": ["viaje", "carrera", "servicio", "uber", "didi", "rappi", "indriver"],
    "gasto": ["gasto", "gasolina", "gas", "comida", "taller", "cargué", "pagué"],
    "cierre": ["cerrar", "terminar", "fin", "concluir", "parar", "terminé", "cierre"]
}

@router.post("/procesar")
async def procesar_comando(payload: dict):
    texto_original = payload.get("text", "")
    if not texto_original:
        return {"intent": "unknown", "message": "No recibí audio o texto."}
        
    texto = texto_original.lower()
    
    # 1. Detectar: CIERRE DE JORNADA
    if any(word in texto for word in KEYWORDS["cierre"]) and "jornada" in texto:
        return {
            "intent": "cerrar_jornada",
            "action": "POST",
            "url": "/api/v1/jornada/cerrar",
            "message": "Entendido. Generando tu resumen de hoy..."
        }

    # 2. Detectar: REGISTRO DE VIAJE
    if any(word in texto for word in KEYWORDS["viaje"]):
        monto = re.findall(r'\d+', texto)
        monto_final = float(monto[0]) if monto else 0
        return {
            "intent": "registrar_viaje",
            "data": {"monto": monto_final, "plataforma": "uber"}
        }

    # 3. Detectar: REGISTRO DE GASTO
    if any(word in texto for word in KEYWORDS["gasto"]):
        monto = re.findall(r'\d+', texto)
        monto_final = float(monto[0]) if monto else 0
        return {
            "intent": "registrar_gasto",
            "data": {"monto": monto_final}
        }

    return {"intent": "unknown", "message": "¿Puedes repetir? No detecté una orden clara."}
