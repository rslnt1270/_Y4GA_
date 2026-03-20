"""
YAGA PROJECT - Clasificador para Conductores
Copyright (c) 2026 YAGA Project
"""
import unicodedata
import re
from dataclasses import dataclass, field
from typing import Optional
from services.nlp.intent_catalog import DriverIntent, INTENT_PATTERNS


def normalize(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


@dataclass
class ExtractedEntities:
    monto: Optional[float] = None
    propina: Optional[float] = None
    plataforma: Optional[str] = None
    metodo_pago: Optional[str] = None
    categoria_gasto: Optional[str] = None


@dataclass
class ClassificationResult:
    intent: DriverIntent
    confidence: float
    matched_keywords: list[str]
    entities: ExtractedEntities = field(default_factory=ExtractedEntities)


def extract_entities(text: str) -> ExtractedEntities:
    entities = ExtractedEntities()
    normalized = normalize(text)

    # Extraer monto principal
    amounts = re.findall(r'\b(\d+(?:\.\d{2})?)\b', text)
    if amounts:
        entities.monto = float(amounts[0])
    if len(amounts) >= 2:
        entities.propina = float(amounts[1])

    # Detectar plataforma
    platforms = {
        'uber': 'uber', 'didi': 'didi', 'cabify': 'cabify',
        'indriver': 'indriver', 'rappi': 'rappi', 'ubereats': 'ubereats',
    }
    for kw, platform in platforms.items():
        if kw in normalized:
            entities.plataforma = platform
            break
    if not entities.plataforma:
        entities.plataforma = 'uber'  # Default

    # Detectar método de pago
    if any(kw in normalized for kw in ['efectivo', 'cash', 'billetes']):
        entities.metodo_pago = 'efectivo'
    elif any(kw in normalized for kw in ['tarjeta', 'card', 'credito', 'debito']):
        entities.metodo_pago = 'tarjeta'
    else:
        entities.metodo_pago = 'app'

    # Detectar categoría de gasto
    gasto_map = {
        'gasolina': ['gasolina', 'gas', 'cargue', 'cargué', 'llene', 'llené'],
        'comida':   ['comida', 'comi', 'comí', 'comer', 'taco', 'almuerzo'],
        'mantenimiento': ['mantenimiento', 'taller', 'aceite', 'llanta', 'frenos'],
        'lavado':   ['lavado', 'lavar', 'lavé'],
        'estacionamiento': ['estacionamiento', 'parqueo', 'parking'],
    }
    for categoria, keywords in gasto_map.items():
        if any(kw in normalized for kw in keywords):
            entities.categoria_gasto = categoria
            break
    if not entities.categoria_gasto:
        entities.categoria_gasto = 'otro'

    return entities


def classify(text: str) -> ClassificationResult:
    normalized = normalize(text)
    scores: dict = {}

    for pattern in INTENT_PATTERNS:
        matched = [kw for kw in pattern.keywords if kw in normalized]
        if not matched:
            continue
        score = len(matched) / len(pattern.keywords)
        bonus = sum(len(kw) for kw in matched) / 200.0
        scores[pattern.intent] = (min(score + bonus, 0.99), matched)

    if not scores:
        return ClassificationResult(
            intent=DriverIntent.UNKNOWN,
            confidence=0.0,
            matched_keywords=[],
        )

    best = max(scores, key=lambda i: scores[i][0])
    best_score, best_kws = scores[best]
    entities = extract_entities(text)

    return ClassificationResult(
        intent=best,
        confidence=round(best_score, 4),
        matched_keywords=best_kws,
        entities=entities,
    )
