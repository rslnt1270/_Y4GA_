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

    # 1. Extraer todos los números del texto
    amounts = [float(n) for n in re.findall(r'\d+(?:\.\d+)?', text)]

    # 2. Lógica Especial de Propinas
    if "propina" in normalized and amounts:
        # Si hay propina, el primer número es el monto del viaje, el segundo la propina
        # Ej: "viaje 100 propina 20" -> monto 100, propina 20
        # Ej: "20 propina" -> monto 20, propina 0 (el total ya incluye la propina)
        if len(amounts) >= 2:
            entities.monto = amounts[0]
            entities.propina = amounts[1]
        else:
            # Solo propina sin monto de viaje (ej: "20 propina") -> monto=tip, propina=0
            entities.monto = amounts[0]
            entities.propina = 0
    elif amounts:
        # Viaje normal
        entities.monto = amounts[0]

    # 3. Plataforma (Uber por defecto)
    platforms = {'uber': 'uber', 'didi': 'didi', 'cabify': 'cabify', 'indriver': 'indriver'}
    entities.plataforma = next((p for k, p in platforms.items() if k in normalized), 'uber')

    # 4. Método de pago
    if any(kw in normalized for kw in ['efectivo', 'cash']):
        entities.metodo_pago = 'efectivo'
    else:
        entities.metodo_pago = 'app'

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
