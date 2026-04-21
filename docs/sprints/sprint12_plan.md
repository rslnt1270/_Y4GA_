# © YAGA Project — Todos los derechos reservados
# Sprint 12 — NLP híbrido + UX Fase 02 + observabilidad

**Duración**: 2 semanas (2026-05-12 → 2026-05-25)
**Pre-requisitos**: Sprint 11 cerrado (frontend modular + ARCO sesiones)
**Rama base**: `main`

---

## Objetivos

1. **Inteligencia**: NLP entiende comandos complejos ("cargué 400 de la roja con comisión") vía fallback a LLM pequeño, manteniendo costo mensual < $2 USD.
2. **Visible al usuario**: UX Fase 02 (hero stat de ingresos, voz rediseñada, animación de transición al cerrar jornada).
3. **Observabilidad**: métricas de uso del NLP, latencia p99 por endpoint, errores de auth auditados.

## Tareas

### [P0 - Backend] NLP Router híbrido regex + LLM
- **Archivos nuevos**: `app/services/nlp_router.py`, `app/services/nlp_llm_fallback.py`.
- **Capa 1**: regex actual (13 intents, sub-200 ms, gratuito). Si `confidence > 0.8` → ejecutar.
- **Capa 2**: si `confidence < 0.8` o `UNKNOWN` → enviar a LLM pequeño (**Claude Haiku vía API Anthropic directa**, NO Bedrock por restricción "no agregar AWS extra").
- Budget: ≤ 5% de comandos deben llegar al LLM → instrumentar contador en Valkey; si excede umbral, log + fallback a "no entendí".
- Prompt del LLM: return JSON estricto con `{intent, entities}` de la lista cerrada actual.
- **Criterio**: +30% de tasa de éxito en comandos complejos; costo real < $2/mes medido durante 2 semanas; latencia p95 del router < 800 ms.
- **Fallback si Claude API cae**: retornar UNKNOWN normal, no bloquear.

### [P0 - UX] Stitch Fase 02 — hero stat + voz rediseñada
- Hero: card grande de ingresos del día con micro-animación al cambiar el número.
- Voz: botón de micrófono con estados visuales explícitos (escuchando / procesando / éxito / error).
- Transición al cerrar jornada: 3-pantallas tipo slide (resumen → comparativa → cierre).
- **Criterio**: grabaciones de prueba muestran mejora subjetiva; no se rompen flujos existentes.

### [P1 - Ops] Métricas + alertas
- **Stack**: `fastapi` middleware → `/metrics` prometheus-compatible → panel en Grafana Cloud free tier (hasta 10k series, gratuito).
- Métricas: requests/s por endpoint, latencia p50/p95/p99, ratio 4xx/5xx, uso del NLP LLM (capa 2 %).
- Alertas: `auth_reuse_detected > 5/hora` → Telegram bot.
- **Criterio**: dashboard Grafana accesible con datos reales; 1 alerta validada end-to-end.
- **Restricción**: Grafana Cloud free, no agregar CloudWatch detallado (costo).

### [P1 - Backend] Reducir access TTL login/register a 15 min
- Condición: frontend modular (Sprint 11) en el 100% de usuarios activos (verificar vía audit log).
- Cambio: `ACCESS_TOKEN_EXPIRE_MINUTES = 15` (un número).
- **Criterio**: tasa de 401 → refresh no explota; sin incremento de logins fallidos.

### [P2 - Data] Backup pg_dump cifrado a S3 + restore test
- **Archivos**: `scripts/backup_postgres.sh` (hardening), `scripts/test_restore.sh` (nuevo), cron `/etc/cron.d/yaga-backup` en EC2.
- Cifrado cliente con `openssl aes-256-cbc -pbkdf2` usando `BACKUP_ENCRYPT_KEY` (clave distinta a `DB_ENCRYPT_KEY`).
- S3 lifecycle: Standard 7d → Glacier IR 30d → Deep Archive 90d → expire 2y.
- Restore test semanal a contenedor efímero con `SELECT count(*)` de validación.
- **Criterio**: 3 backups consecutivos en S3 cifrados; restore < 15 min; `BACKUP_ENCRYPT_KEY` documentada en runbook (no en repo).

### [P2 - UX/A11y] Auditoría accesibilidad
- Axe-core en el build manual (script one-shot).
- Contraste textos muted (issue menor de Fase 01).
- Labels + aria en inputs.
- **Criterio**: Axe < 10 violations en index principal.

## Riesgos

1. **Costo LLM**: si usuarios descubren que fallback es más listo y hablan más natural, el 5% sube. Mitigación: rate limit por usuario (20 requests/hora al LLM).
2. **Anthropic API key**: se guardará en AWS Secrets Manager (sí, 1 AWS nuevo — pero gratuito hasta 3 secretos) o en `.env` con permisos estrictos. Decisión al inicio del sprint.
3. **Grafana Cloud**: si la free tier no alcanza, fallback a logging en stdout + CloudWatch Logs básico.

## Fuera de alcance (Sprint 13+)

- Migración a EKS.
- Sustituir PG en EC2 por RDS (análisis-only en Sprint 13, no implementación).
- App móvil nativa.
- SDK público para integrarse con flotas.
