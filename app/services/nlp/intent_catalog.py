# © YAGA Project — Todos los derechos reservados
"""
Catálogo de intenciones NLP para conductores mexicanos de plataformas.
Clasificador determinista — sin LLM, sub-200ms.
Sprint 6: diccionario ampliado con required_none y requires_amount.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import FrozenSet


class DriverIntent(str, Enum):
    # Jornada
    INICIAR_JORNADA         = "iniciar_jornada"
    CERRAR_JORNADA          = "cerrar_jornada"
    TERMINAR_JORNADA        = "terminar_jornada"
    # Ciclo de viaje
    EN_CAMINO_RECOGER       = "en_camino_recoger"
    INICIAR_VIAJE           = "iniciar_viaje"
    TERMINAR_VIAJE          = "terminar_viaje"
    # Ingresos (legacy — mantener compatibilidad)
    REGISTRAR_VIAJE         = "registrar_viaje"
    # Ingresos por método de pago
    AGREGAR_EFECTIVO        = "agregar_efectivo"
    AGREGAR_TARJETA         = "agregar_tarjeta"
    # Gastos por categoría
    AGREGAR_GASOLINA        = "agregar_gasolina"
    AGREGAR_COMIDA          = "agregar_comida"
    AGREGAR_PEAJE           = "agregar_peaje"
    AGREGAR_ESTACIONAMIENTO = "agregar_estacionamiento"
    AGREGAR_GASTO_GENERAL   = "agregar_gasto_general"
    # Gastos (legacy)
    REGISTRAR_GASTO         = "registrar_gasto"
    # Consultas
    CONSULTAR_RESUMEN       = "consultar_resumen"
    CONSULTAR_TOTAL         = "consultar_total"
    # Errores
    COMANDO_INCOMPLETO      = "comando_incompleto"
    UNKNOWN                 = "unknown"


@dataclass(frozen=True)
class IntentPattern:
    intent: DriverIntent
    keywords: FrozenSet[str]
    required_none: FrozenSet[str] = field(default_factory=frozenset)
    requires_amount: bool = False


INTENT_PATTERNS: list[IntentPattern] = [
    # ── Jornada ──────────────────────────────────────────────────────────────
    IntentPattern(
        intent=DriverIntent.INICIAR_JORNADA,
        keywords=frozenset({
            "iniciar jornada", "empezar jornada", "comenzar jornada",
            "iniciar turno", "arrancar turno", "empezar el dia",
            "arrancar la chamba", "empezar a ruletear", "a trabajar",
            "inicio de jornada", "empezamos", "arrancamos el turno",
            "inicio jornada", "comienzo jornada", "inicio turno",
            "comenzar", "empezar turno",
        }),
        required_none=frozenset({"terminar", "finalizar", "acabar"}),
    ),
    IntentPattern(
        intent=DriverIntent.CERRAR_JORNADA,
        keywords=frozenset({
            "cerrar jornada", "terminar jornada", "fin jornada",
            "termino jornada", "ya termine", "ya acabe",
            "cuanto hice hoy", "cuanto hice",
        }),
    ),
    IntentPattern(
        intent=DriverIntent.TERMINAR_JORNADA,
        keywords=frozenset({
            "finalizar jornada", "acabar jornada", "fin de jornada",
            "terminar turno", "ya fue por hoy", "hasta aqui",
            "cerramos", "terminar el dia", "ya me voy a casa",
            "fin del turno", "terminamos por hoy",
        }),
        required_none=frozenset({"viaje"}),
    ),
    # ── Ciclo de viaje ────────────────────────────────────────────────────────
    IntentPattern(
        intent=DriverIntent.EN_CAMINO_RECOGER,
        keywords=frozenset({
            "en camino a recoger", "voy por el pasajero", "voy por el usuario",
            "rumbo a la recogida", "ya voy para alla", "me dirijo",
            "voy en camino", "voy a recoger", "saliendo a recoger",
            "camino al pin", "voy por el cliente",
        }),
        required_none=frozenset({"terminar", "llegue"}),
    ),
    IntentPattern(
        intent=DriverIntent.INICIAR_VIAJE,
        keywords=frozenset({
            "iniciar viaje", "inicia viaje", "empezar viaje",
            "arranca el viaje", "ya lo recogi", "recogi al pasajero",
            "subio el pasajero", "ya vamos", "comenzar recorrido",
            "inicio de viaje", "arrancamos",
        }),
        required_none=frozenset({"terminar", "finalizar"}),
    ),
    IntentPattern(
        intent=DriverIntent.TERMINAR_VIAJE,
        keywords=frozenset({
            "terminar viaje", "termina viaje", "finalizar viaje",
            "fin de viaje", "llegamos", "ya llegamos",
            "llegue al destino", "deje al pasajero",
            "bajo el pasajero", "viaje terminado", "destino alcanzado",
            "fin del recorrido", "lo deje", "llego",
        }),
        required_none=frozenset({"jornada"}),
    ),
    # ── Ingresos: viaje legacy (compatibilidad) ───────────────────────────────
    IntentPattern(
        intent=DriverIntent.REGISTRAR_VIAJE,
        keywords=frozenset({
            "viaje", "carrera", "servicio", "uber", "didi",
            "cabify", "indriver", "rappi", "ubereats",
            "agrega", "registra", "anota", "fue de", "cobre", "propina",
        }),
        requires_amount=True,
    ),
    # ── Ingresos: por método de pago ──────────────────────────────────────────
    IntentPattern(
        intent=DriverIntent.AGREGAR_EFECTIVO,
        keywords=frozenset({
            "en efectivo", "en cash", "en billete", "en billetes",
            "me pago en efectivo", "fue en efectivo", "pago en cash",
            "con billete", "pago con efectivo", "en feria",
            "con feria", "con lana",
        }),
        requires_amount=True,
    ),
    IntentPattern(
        intent=DriverIntent.AGREGAR_TARJETA,
        keywords=frozenset({
            "en tarjeta", "con tarjeta", "fue con tarjeta",
            "pago con tarjeta", "pago digital", "con el plastico",
            "debito", "credito",
        }),
        requires_amount=True,
    ),
    # ── Gastos ────────────────────────────────────────────────────────────────
    IntentPattern(
        intent=DriverIntent.AGREGAR_GASOLINA,
        keywords=frozenset({
            "gasolina", "gas", "diesel", "combustible",
            "cargar gasolina", "echar gas", "llene el tanque",
            "puse gasolina", "tanquee", "cargue gasolina",
            "magna", "premium",
        }),
        requires_amount=True,
    ),
    IntentPattern(
        intent=DriverIntent.AGREGAR_COMIDA,
        keywords=frozenset({
            "comida", "comer", "almuerzo", "desayuno", "cena",
            "lonche", "torta", "tacos", "gaste en comida",
            "me comi", "lunch", "antojitos", "botana",
        }),
        requires_amount=True,
    ),
    IntentPattern(
        intent=DriverIntent.AGREGAR_PEAJE,
        keywords=frozenset({
            "peaje", "caseta", "cuota", "autopista",
            "cobro de caseta", "pase caseta", "pague caseta",
            "la caseta",
        }),
        requires_amount=True,
    ),
    IntentPattern(
        intent=DriverIntent.AGREGAR_ESTACIONAMIENTO,
        keywords=frozenset({
            "estacionamiento", "parking", "parquimetro",
            "estacione", "cobro de parking",
        }),
        requires_amount=True,
    ),
    IntentPattern(
        intent=DriverIntent.AGREGAR_GASTO_GENERAL,
        keywords=frozenset({
            "gasto", "gaste", "pague", "egreso",
            "salida de dinero", "otro gasto",
        }),
        requires_amount=True,
    ),
    # ── Gastos legacy (compatibilidad) ────────────────────────────────────────
    IntentPattern(
        intent=DriverIntent.REGISTRAR_GASTO,
        keywords=frozenset({
            "mantenimiento", "taller", "aceite", "llanta", "frenos",
            "lavado", "lavar", "parqueo", "cargue", "llene",
        }),
        requires_amount=True,
    ),
    # ── Consultas ─────────────────────────────────────────────────────────────
    IntentPattern(
        intent=DriverIntent.CONSULTAR_RESUMEN,
        keywords=frozenset({
            "resumen", "como voy", "cuanto llevo", "mis ganancias",
            "balance", "reporte", "informe", "estadisticas",
            "resumen del dia", "cómo voy", "cuanto gane",
            "total del dia", "balance",
        }),
    ),
    IntentPattern(
        intent=DriverIntent.CONSULTAR_TOTAL,
        keywords=frozenset({
            "cuanto hice", "mis viajes", "cuantos viajes",
            "cuanto gaste",
        }),
    ),
]
