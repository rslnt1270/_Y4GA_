"""
YAGA PROJECT - Endpoints de Comandos de Voz
Copyright (c) 2026 YAGA Project
"""
from fastapi import APIRouter
from pydantic import BaseModel, Field
from services.nlp.classifier import classify
from services.nlp.intent_catalog import DriverIntent
from services.jornada_service import (
    cerrar_jornada,
    get_or_create_jornada,
    registrar_viaje,
    registrar_gasto,
    get_resumen_jornada,
    get_comparativa
)

router = APIRouter()

class CommandRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    conductor_id: str = "default"

@router.post("/command")
async def process_command(body: CommandRequest):
    texto_limpio = body.text.lower()

    # Interceptor de Cierre de Jornada
    if "cerrar" in texto_limpio and "jornada" in texto_limpio:
        stats = await get_comparativa(body.conductor_id)
        estado = stats.get("comparativa", {}).get("estado", "Evaluando...")
        await cerrar_jornada(body.conductor_id)
        return {
            "intent": "cerrar_jornada",
            "message": f"Jornada Cerrada. {estado}",
            "data": {"cerrada": True, "resumen": stats}
        }

    # Flujo Normal
    result = classify(body.text)
    intent = result.intent

    if intent == DriverIntent.UNKNOWN:
        return {
            "intent": intent.value,
            "message": "No entendi. Intenta: 'viaje uber efectivo 90' o 'gasolina 300'",
            "data": None,
        }

    if intent == DriverIntent.CONSULTAR_RESUMEN:
        resumen = await get_resumen_jornada(body.conductor_id)
        return {
            "intent": intent.value,
            "message": "Resumen de tu jornada",
            "data": resumen,
        }

    jornada_id = await get_or_create_jornada(body.conductor_id)

    if intent == DriverIntent.REGISTRAR_VIAJE:
        if result.entities.monto is None and not result.entities.propina:
            return {
                "intent": intent.value,
                "message": "Cuanto fue el viaje? Ejemplo: 'viaje uber efectivo 90'",
                "data": None,
            }
        saved = await registrar_viaje(jornada_id, result.entities)
        return {
            "intent": intent.value,
            "message": f"Viaje guardado: ${saved['monto']} en {saved['plataforma']} ({saved['metodo_pago']})",
            "data": saved,
        }

    if intent == DriverIntent.REGISTRAR_GASTO:
        if not result.entities.monto:
            return {
                "intent": intent.value,
                "message": "Cuanto fue el gasto? Ejemplo: 'gasolina 300'",
                "data": None,
            }
        saved = await registrar_gasto(jornada_id, result.entities)
        return {
            "intent": intent.value,
            "message": f"Gasto guardado: ${saved['monto']} en {saved['categoria']}",
            "data": saved,
        }

    if intent == DriverIntent.INICIAR_JORNADA:
        return {
            "intent": intent.value,
            "message": f"Jornada activa. ID: {jornada_id}",
            "data": {"jornada_id": jornada_id},
        }

    return {"intent": intent.value, "message": "Procesando...", "data": None}

@router.get("/resumen")
async def resumen_jornada(conductor_id: str = "default"):
    return await get_resumen_jornada(conductor_id)

@router.get("/comparativa")
async def comparativa_jornada(conductor_id: str = "default"):
    return await get_comparativa(conductor_id)
