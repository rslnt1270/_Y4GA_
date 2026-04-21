# © YAGA Project — Todos los derechos reservados
"""
Endpoint NLP: procesa comandos de voz de conductores mexicanos.
Sprint 6: diccionario ampliado, logging de comandos no reconocidos.
"""
import asyncio

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from core.logging import get_logger
from dependencies import get_current_user
from services.audit_service import log_action
from services.jornada_service import (
    cerrar_jornada,
    get_or_create_jornada,
    registrar_viaje,
    registrar_gasto,
    get_resumen_jornada,
    get_comparativa,
)
from services.nlp.classifier import classify
from services.nlp.intent_catalog import DriverIntent

router = APIRouter()
logger = get_logger("yaga.nlp")

MONTO_MIN = 1
MONTO_MAX = 5000


def _monto_valido(monto) -> bool:
    try:
        m = float(monto)
    except (TypeError, ValueError):
        return False
    return MONTO_MIN <= m <= MONTO_MAX

# Intents que requieren guardar un gasto con categoría implícita
_GASTO_INTENTS = {
    DriverIntent.AGREGAR_GASOLINA,
    DriverIntent.AGREGAR_COMIDA,
    DriverIntent.AGREGAR_PEAJE,
    DriverIntent.AGREGAR_ESTACIONAMIENTO,
    DriverIntent.AGREGAR_GASTO_GENERAL,
    DriverIntent.REGISTRAR_GASTO,
}

# Intents que registran un viaje (con método de pago)
_VIAJE_INTENTS = {
    DriverIntent.AGREGAR_EFECTIVO,
    DriverIntent.AGREGAR_TARJETA,
    DriverIntent.REGISTRAR_VIAJE,
}

# Intents de ciclo de viaje (solo acknowledgment, sin DB write aún)
_CICLO_MSGS = {
    DriverIntent.EN_CAMINO_RECOGER: "🚗 En camino a recoger al pasajero.",
    DriverIntent.INICIAR_VIAJE:     "▶️ Viaje iniciado.",
    DriverIntent.TERMINAR_VIAJE:    "🏁 Viaje terminado. ¿Cuánto fue?",
}


class CommandRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)


@router.post("/command")
async def process_command(
    request: Request,
    body: CommandRequest,
    current_user: dict = Depends(get_current_user),
):
    conductor_id = str(current_user["id"])
    texto_limpio = body.text.lower()

    # ── Interceptor de cierre (compatibilidad con comando explícito) ──────────
    if "cerrar" in texto_limpio and "jornada" in texto_limpio:
        stats = await get_comparativa(conductor_id)
        estado = stats.get("comparativa", {}).get("estado", "Evaluando...")
        await cerrar_jornada(conductor_id)
        return {
            "intent": "cerrar_jornada",
            "message": f"🏁 Jornada Cerrada. {estado}",
            "data": {"cerrada": True, "resumen": stats},
        }

    # ── Clasificar ────────────────────────────────────────────────────────────
    result = classify(body.text)
    intent = result.intent

    # ── Comando incompleto ────────────────────────────────────────────────────
    if intent == DriverIntent.COMANDO_INCOMPLETO:
        return {
            "intent": intent.value,
            "message": f"❓ Falta el {result.missing}. Ejemplo: 'gasolina 300' o 'en efectivo 150'",
            "data": None,
        }

    # ── Comando no reconocido ─────────────────────────────────────────────────
    if intent == DriverIntent.UNKNOWN:
        return {
            "intent": "comando_no_reconocido",
            "message": "❓ No entendí. Intenta: 'viaje uber efectivo 90', 'gasolina 300', 'cuánto llevo'",
            "data": None,
        }

    # ── Consultas ─────────────────────────────────────────────────────────────
    if intent in (DriverIntent.CONSULTAR_RESUMEN, DriverIntent.CONSULTAR_TOTAL):
        resumen = await get_resumen_jornada(conductor_id)
        return {
            "intent": intent.value,
            "message": "📊 Resumen de tu jornada",
            "data": resumen,
        }

    # ── Jornada ───────────────────────────────────────────────────────────────
    if intent == DriverIntent.INICIAR_JORNADA:
        jornada_id = await get_or_create_jornada(conductor_id)
        return {
            "intent": intent.value,
            "message": "✅ Jornada iniciada. ¡A ruletear!",
            "data": {"jornada_id": jornada_id},
        }

    if intent in (DriverIntent.TERMINAR_JORNADA, DriverIntent.CERRAR_JORNADA):
        stats = await get_comparativa(conductor_id)
        estado = stats.get("comparativa", {}).get("estado", "Evaluando...")
        await cerrar_jornada(conductor_id)
        return {
            "intent": intent.value,
            "message": f"🏁 Jornada Cerrada. {estado}",
            "data": {"cerrada": True, "resumen": stats},
        }

    # ── Ciclo de viaje (acknowledgment sin DB write) ──────────────────────────
    if intent in _CICLO_MSGS:
        return {
            "intent": intent.value,
            "message": _CICLO_MSGS[intent],
            "data": None,
        }

    # ── Operaciones que requieren jornada activa ──────────────────────────────
    jornada_id = await get_or_create_jornada(conductor_id)

    if intent in _VIAJE_INTENTS:
        if result.entities.monto is None and not result.entities.propina:
            return {
                "intent": intent.value,
                "message": "❓ ¿Cuánto fue el viaje? Ejemplo: 'viaje uber efectivo 90'",
                "data": None,
            }
        if result.entities.monto is not None and not _monto_valido(result.entities.monto):
            asyncio.create_task(log_action(
                usuario_id=conductor_id,
                accion="nlp_monto_rechazado",
                ip=None,
                user_agent=None,
                detalles={
                    "intent": intent.value,
                    "monto": result.entities.monto,
                    "texto": body.text[:200],
                },
            ))
            return {
                "intent": intent.value,
                "message": f"❌ Monto fuera de rango (permitido: ${MONTO_MIN}–${MONTO_MAX} MXN)",
                "data": None,
            }
        saved = await registrar_viaje(jornada_id, result.entities)
        return {
            "intent": intent.value,
            "message": f"✅ Viaje guardado: ${saved['monto']} en {saved['plataforma']} ({saved['metodo_pago']})",
            "data": saved,
        }

    if intent in _GASTO_INTENTS:
        if not result.entities.monto:
            return {
                "intent": intent.value,
                "message": "❓ ¿Cuánto fue el gasto? Ejemplo: 'gasolina 300'",
                "data": None,
            }
        if not _monto_valido(result.entities.monto):
            asyncio.create_task(log_action(
                usuario_id=conductor_id,
                accion="nlp_monto_rechazado",
                ip=None,
                user_agent=None,
                detalles={
                    "intent": intent.value,
                    "monto": result.entities.monto,
                    "texto": body.text[:200],
                },
            ))
            return {
                "intent": intent.value,
                "message": f"❌ Monto fuera de rango (permitido: ${MONTO_MIN}–${MONTO_MAX} MXN)",
                "data": None,
            }
        saved = await registrar_gasto(jornada_id, result.entities)
        return {
            "intent": intent.value,
            "message": f"✅ Gasto guardado: ${saved['monto']} en {saved['categoria']}",
            "data": saved,
        }

    # Fallback (intención reconocida pero sin handler)
    logger.warning(f"Intent sin handler: {intent.value}")
    return {
        "intent": intent.value,
        "message": "⚠️ Comando reconocido pero no implementado aún.",
        "data": None,
    }


@router.get("/resumen")
async def get_resumen(current_user: dict = Depends(get_current_user)):
    return await get_resumen_jornada(str(current_user["id"]))


@router.get("/comparativa")
async def comparativa_endpoint(current_user: dict = Depends(get_current_user)):
    return await get_comparativa(str(current_user["id"]))
