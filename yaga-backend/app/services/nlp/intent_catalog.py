"""
YAGA PROJECT - Intenciones para Conductores de Plataformas
Copyright (c) 2026 YAGA Project
"""
from enum import Enum
from dataclasses import dataclass
from typing import FrozenSet


class DriverIntent(str, Enum):
    # Jornada
    INICIAR_JORNADA     = "iniciar_jornada"
    CERRAR_JORNADA      = "cerrar_jornada"
    # Ingresos
    REGISTRAR_VIAJE     = "registrar_viaje"
    # Gastos
    REGISTRAR_GASTO     = "registrar_gasto"
    # Consultas
    CONSULTAR_RESUMEN   = "consultar_resumen"
    CONSULTAR_TOTAL     = "consultar_total"
    # Desconocido
    UNKNOWN             = "unknown"


@dataclass(frozen=True)
class IntentPattern:
    intent: DriverIntent
    keywords: FrozenSet[str]


INTENT_PATTERNS = [
    IntentPattern(
        intent=DriverIntent.INICIAR_JORNADA,
        keywords=frozenset({
            "iniciar jornada", "empezar jornada", "inicio jornada",
            "comienzo jornada", "empiezo", "arranco", "inicio turno",
            "comenzar", "empezar turno",
        }),
    ),
    IntentPattern(
        intent=DriverIntent.CERRAR_JORNADA,
        keywords=frozenset({
            "cerrar jornada", "terminar jornada", "fin jornada",
            "termino jornada", "ya termine", "ya acabé", "ya acabe",
            "resumen del dia", "resumen del día", "cuanto hice hoy",
            "cuánto hice hoy",
        }),
    ),
    IntentPattern(
        intent=DriverIntent.REGISTRAR_VIAJE,
        keywords=frozenset({
            "viaje", "carrera", "servicio", "efectivo", "tarjeta",
            "uber", "didi", "cabify", "indriver", "rappi", "ubereats",
            "agrega", "registra", "anota", "fue de", "cobré", "cobre",
            "propina",
        }),
    ),
    IntentPattern(
        intent=DriverIntent.REGISTRAR_GASTO,
        keywords=frozenset({
            "gasto", "gasté", "gaste", "pague", "pagué",
            "gasolina", "gas", "comida", "comi", "comí", "comer",
            "mantenimiento", "taller", "aceite", "llanta", "frenos",
            "lavado", "lavar", "estacionamiento", "parqueo",
            "cargué", "cargue", "llené", "llene",
        }),
    ),
    IntentPattern(
        intent=DriverIntent.CONSULTAR_RESUMEN,
        keywords=frozenset({
            "resumen", "como voy", "cómo voy", "cuanto llevo",
            "cuánto llevo", "mis ganancias", "balance", "reporte",
            "strava", "informe", "estadisticas", "estadísticas",
        }),
    ),
    IntentPattern(
        intent=DriverIntent.CONSULTAR_TOTAL,
        keywords=frozenset({
            "cuanto gane", "cuánto gané", "total del dia", "total del día",
            "cuanto hice", "cuánto hice", "mis viajes", "cuantos viajes",
            "cuántos viajes", "cuanto gasté", "cuánto gasté",
        }),
    ),
]
