# © YAGA Project — Todos los derechos reservados
"""
Clasificador determinista de comandos de voz para conductores mexicanos.
Sub-200ms, sin LLM, basado en keyword matching con scores de confianza.
Sprint 6: soporte para required_none, requires_amount, score exacto vs parcial.
"""
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

from services.nlp.intent_catalog import DriverIntent, INTENT_PATTERNS

_AMOUNT_RE = re.compile(r'\b(\d+(?:\.\d+)?)\b')


def normalize(text: str) -> str:
    """Minúsculas + eliminar acentos/diacríticos."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


@dataclass
class ExtractedEntities:
    monto: Optional[float] = None
    propina: Optional[float] = None
    plataforma: Optional[str] = None
    metodo_pago: Optional[str] = None
    categoria_gasto: Optional[str] = None
    tipo_pago: Optional[str] = None


@dataclass
class ClassificationResult:
    intent: DriverIntent
    confidence: float
    matched_keywords: list[str]
    entities: ExtractedEntities = field(default_factory=ExtractedEntities)
    missing: Optional[str] = None


def extract_amount(text: str) -> Optional[float]:
    """Extrae el primer número del texto."""
    m = _AMOUNT_RE.search(text)
    return float(m.group(1)) if m else None


def extract_entities(text: str, intent: DriverIntent) -> ExtractedEntities:
    """Extrae entidades según la intención detectada."""
    entities = ExtractedEntities()
    normalized = normalize(text)

    # Montos
    amounts = [float(n) for n in _AMOUNT_RE.findall(text)]

    if "propina" in normalized and amounts:
        if len(amounts) >= 2:
            entities.monto = amounts[0]
            entities.propina = amounts[1]
        else:
            entities.monto = amounts[0]
            entities.propina = 0.0
    elif amounts:
        entities.monto = amounts[0]

    # Plataforma
    platforms = {"uber": "uber", "didi": "didi", "cabify": "cabify", "indriver": "indriver"}
    entities.plataforma = next((p for k, p in platforms.items() if k in normalized), "uber")

    # Método de pago según intención
    if intent == DriverIntent.AGREGAR_EFECTIVO:
        entities.metodo_pago = "efectivo"
        entities.tipo_pago = "efectivo"
    elif intent == DriverIntent.AGREGAR_TARJETA:
        entities.metodo_pago = "tarjeta"
        entities.tipo_pago = "tarjeta"
    elif any(kw in normalized for kw in ("efectivo", "cash", "billete", "feria", "lana")):
        entities.metodo_pago = "efectivo"
        entities.tipo_pago = "efectivo"
    else:
        entities.metodo_pago = "app"
        entities.tipo_pago = "app"

    # Categoría de gasto según intención
    _gasto_map = {
        DriverIntent.AGREGAR_GASOLINA:        "gasolina",
        DriverIntent.AGREGAR_COMIDA:          "comida",
        DriverIntent.AGREGAR_PEAJE:           "peaje",
        DriverIntent.AGREGAR_ESTACIONAMIENTO: "estacionamiento",
        DriverIntent.AGREGAR_GASTO_GENERAL:   "general",
        DriverIntent.REGISTRAR_GASTO:         "general",
    }
    if intent in _gasto_map:
        entities.categoria_gasto = _gasto_map[intent]

    return entities


def classify(text: str) -> ClassificationResult:
    """
    Clasifica un comando de voz en un DriverIntent.

    Reglas:
    1. Normalizar texto (minúsculas + sin acentos).
    2. Para cada patrón, descartar si algún required_none aparece.
    3. Score exacto = 1.0 por frase exacta, parcial = proporción de keywords.
    4. Si requires_amount y no hay número → COMANDO_INCOMPLETO.
    5. Si mejor score < 0.5 → UNKNOWN.
    """
    normalized = normalize(text)
    scores: dict[DriverIntent, tuple[float, list[str]]] = {}

    for pattern in INTENT_PATTERNS:
        # Filtrar por required_none
        if any(excl in normalized for excl in pattern.required_none):
            continue

        matched: list[str] = []
        exact_hit = False

        for kw in pattern.keywords:
            if kw in normalized:
                matched.append(kw)
                # Frase larga exacta = bonus de exactitud
                if len(kw.split()) >= 2:
                    exact_hit = True

        if not matched:
            continue

        # Calcular score
        # Frase multi-palabra exacta → alta confianza
        # Keyword de palabra sola → mínimo 0.6 si el keyword es específico (≥4 chars)
        if exact_hit:
            base_score = 1.0
        else:
            ratio = len(matched) / len(pattern.keywords)
            char_bonus = sum(len(kw) for kw in matched) / 200.0
            raw = ratio + char_bonus
            # Evitar que patrones con muchos keywords penalicen keywords específicos
            specific_single = any(len(kw) >= 4 and " " not in kw for kw in matched)
            base_score = max(raw, 0.6) if specific_single else min(raw, 0.7)

        scores[pattern.intent] = (round(base_score, 4), matched)

    if not scores:
        return ClassificationResult(
            intent=DriverIntent.UNKNOWN,
            confidence=0.0,
            matched_keywords=[],
        )

    best_intent = max(scores, key=lambda i: scores[i][0])
    best_score, best_kws = scores[best_intent]

    if best_score < 0.5:
        return ClassificationResult(
            intent=DriverIntent.UNKNOWN,
            confidence=best_score,
            matched_keywords=best_kws,
        )

    # Verificar requires_amount
    for pattern in INTENT_PATTERNS:
        if pattern.intent == best_intent and pattern.requires_amount:
            if extract_amount(text) is None:
                return ClassificationResult(
                    intent=DriverIntent.COMANDO_INCOMPLETO,
                    confidence=best_score,
                    matched_keywords=best_kws,
                    missing="monto",
                )
            break

    entities = extract_entities(text, best_intent)

    return ClassificationResult(
        intent=best_intent,
        confidence=best_score,
        matched_keywords=best_kws,
        entities=entities,
    )
