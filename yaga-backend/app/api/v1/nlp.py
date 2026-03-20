"""
YAGA PROJECT - Endpoints para Conductores con persistencia
Copyright (c) 2026 YAGA Project
"""
from fastapi import APIRouter
from pydantic import BaseModel, Field
from services.nlp.classifier import classify
from services.nlp.intent_catalog import DriverIntent
from services.jornada_service import (
    get_or_create_jornada,
    registrar_viaje,
    registrar_gasto,
    get_resumen_jornada,
)

router = APIRouter()


class CommandRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    conductor_id: str = "default"


@router.post("/command")
async def process_command(body: CommandRequest):
    result = classify(body.text)
    intent = result.intent

    # Intents que no necesitan BD
    if intent == DriverIntent.UNKNOWN:
        return {
            "intent": intent.value,
            "message": "❓ No entendí. Intenta: 'viaje uber efectivo 90' o 'gasolina 300'",
            "data": None,
        }

    if intent == DriverIntent.CONSULTAR_RESUMEN or intent == DriverIntent.CERRAR_JORNADA:
        resumen = await get_resumen_jornada(body.conductor_id)
        return {
            "intent": intent.value,
            "message": "📊 Resumen de tu jornada",
            "data": resumen,
        }

    # Para todo lo demás necesitamos jornada activa
    jornada_id = await get_or_create_jornada(body.conductor_id)

    if intent == DriverIntent.REGISTRAR_VIAJE:
        if not result.entities.monto:
            return {
                "intent": intent.value,
                "message": "❓ ¿Cuánto fue el viaje? Ejemplo: 'viaje uber efectivo 90'",
                "data": None,
            }
        saved = await registrar_viaje(jornada_id, result.entities)
        return {
            "intent": intent.value,
            "message": f"✅ Viaje guardado: ${saved['monto']} en {saved['plataforma']} ({saved['metodo_pago']})",
            "data": saved,
        }

    if intent == DriverIntent.REGISTRAR_GASTO:
        if not result.entities.monto:
            return {
                "intent": intent.value,
                "message": "❓ ¿Cuánto fue el gasto? Ejemplo: 'gasolina 300'",
                "data": None,
            }
        saved = await registrar_gasto(jornada_id, result.entities)
        return {
            "intent": intent.value,
            "message": f"✅ Gasto guardado: ${saved['monto']} en {saved['categoria']}",
            "data": saved,
        }

    if intent == DriverIntent.INICIAR_JORNADA:
        return {
            "intent": intent.value,
            "message": f"✅ Jornada activa. ID: {jornada_id}",
            "data": {"jornada_id": jornada_id},
        }

    return {"intent": intent.value, "message": "Procesando...", "data": None}


@router.get("/resumen")
async def resumen_jornada(conductor_id: str = "default"):
    resumen = await get_resumen_jornada(conductor_id)
    return resumen
