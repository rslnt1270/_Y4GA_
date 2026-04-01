---
name: architect
description: "Visión arquitectónica, trade-offs, roadmap, y decisiones de diseño de YAGA. Se activa en planificación de sprints y revisiones de PRD."
---

# Arquitectura YAGA — Decisiones y Roadmap

## Decisiones vigentes
| Decisión | Rationale | Fecha |
|----------|-----------|-------|
| NLP determinista, no LLM | <200ms, cero costo, offline | Sprint 1 |
| AES-256 en app, no en SQL | Clave no aparece en query logs | Sprint 1 |
| JWT RS256 (no HS256) | Verificación sin secreto compartido | Sprint 1 |
| Docker Compose (no K8s aún) | Costo vs complejidad para 1 instancia | Sprint 2 |
| GPS como PII cifrada | LFPDPPP + Schrems II safe | Sprint 3 |
| Bedrock Haiku = fallback NLP | Solo cuando el clasificador falla, no reemplazo | Sprint 3 |
| Particionado mensual GPS | Evita table bloat en t3.small | Sprint 3 |
| Poleana como submodule | Repos independientes, deploy separado | Cleanup |

## Flujo principal
```
Voz → PWA → NLP clasificador → intent + entities
  → FastAPI endpoint → encrypt PII → PostgreSQL
  → Redis (session, rate limit)
  → Response → PWA render (cockpit)
```

## Flujo GPS
```
PWA GPS tracker (5s throttle) → buffer local (30s)
  → POST /api/v1/gps/batch (max 500 pts)
  → encrypt lat/lng → UNNEST bulk insert → gps_logs

Cierre jornada:
  → decrypt GPS → Haversine distancia
  → SELECT ingresos-gastos → ganancia_real
  → UPDATE viajes proporcional
```

## Métricas de salud
- NLP: <200ms p99, 0 LLM calls en modo normal
- GPS batch: <500ms para 500 puntos
- Auth: <100ms login, rate limit 5/min
- EC2: CPU <70%, memory <80%, disk <60%
- API: <1% 5xx rate

## Contexto académico
- Tesis "Educación y Algoritmos" — UNAM dual degree
- PAPIME PE110324, UNESCO AI Competency Framework 2024
- Capítulo 5 = YAGA como aplicación práctica
- Marco teórico: entropía como nodo ciudad↔algoritmo
