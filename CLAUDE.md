# YAGA Project — Instrucciones del Proyecto

> © YAGA Project — Todos los derechos reservados
> Todo archivo generado debe iniciar con comentario de licencia.

## Qué es YAGA

Plataforma Fintech para conductores de Uber/DiDi en México. Registro de viajes y gastos por comandos de voz. Dominio: y4ga.app

### Proyectos dentro del repositorio
1. **YAGA PWA** — Co-piloto financiero y asistente de jornadas para conductores
2. **Poleana** — Juego de mesa mexicano multijugador online (subdirectorio dentro del proyecto)

## Stack

- **Backend:** FastAPI Python 3.11 · PostgreSQL 16 (pgcrypto habilitado) · Redis 7
- **Frontend:** PWA React 18+ TypeScript · Vite · Tailwind CSS · offline-first
- **Infra actual:** Docker Compose en AWS EC2 t3.small (Amazon Linux 2023)
- **Poleana:** Cloudflare Pages/Workers (frontend) + mismo EC2 (backend Python)
- **NLP:** Clasificador determinista por keywords (7 intents, español MX, sub-200ms, sin LLM)

## Esquema de base de datos

Tablas principales: `usuarios`, `consentimientos`, `auditoria`, `jornadas`, `viajes`, `gastos`.
- `usuarios` almacena email/phone en texto plano (indexado) Y cifrado AES-256 en columnas `*_cifrado` (BYTEA)
- `consentimientos` tiene restricción UNIQUE(usuario_id, finalidad) con flag `es_obligatorio`
- `auditoria` registra toda acción crítica con IP, user_agent y detalles JSONB
- Todas las PKs son UUID excepto auditoria (BIGSERIAL) y consentimientos (SERIAL)
- Soft delete en usuarios via `deleted_at`

## Seguridad — Reglas no negociables

1. **Cifrado PII:** AES-256 en capa de aplicación con `cryptography` (módulo `app.core.crypto`). IV único por registro. PROHIBIDO usar `pgp_sym_encrypt` en SQL
2. **Clave maestra:** `DB_ENCRYPT_KEY` en AWS Secrets Manager (prod) o env var (local). Nunca en código ni en imágenes Docker
3. **JWT:** RS256 con RSA 2048-bit. Claves inyectadas como env vars desde Secrets Manager
4. **Refresh tokens:** Redis key `refresh:{user_id}`, TTL 7 días, rotación en cada uso, blacklist en logout
5. **Rate limiting:** slowapi + Redis, 5 intentos/min en `/auth/login` y `/auth/register`
6. **Frontend:** JWT en memoria (variable de estado), refresh en HttpOnly cookie. PROHIBIDO localStorage/sessionStorage para tokens
7. **Auditoría:** Todo login, logout, cambio de consentimiento y evento ARCO → tabla `auditoria`
8. **Secretos en K8s (roadmap):** External Secrets Operator, nunca archivos montados

## Compliance LFPDPPP

### Finalidades
- **operacion** (obligatoria, no revocable): cuentas, pagos, KYC, fiscal
- **marketing** (secundaria, opt-out): promociones y comunicaciones
- **investigacion** (secundaria, opt-out): análisis agregado, mejora de servicio

### Derechos ARCO
- `GET /arco/acceso` → JSON con datos personales + transaccionales
- `PUT /arco/rectificacion` → actualiza email/phone, re-cifra con AES-256, valida unicidad
- `POST /arco/cancelacion` → soft delete, anonimiza PII con placeholders, retiene transaccionales 7 años sin relación al usuario, revoca refresh tokens
- `POST /arco/oposicion` → revoca finalidad secundaria sin afectar servicio principal
- Cada acción ARCO se registra en `auditoria` con accion = `arco_*` y detalles JSON

## Endpoints principales

- `/auth/*` → registro, login, refresh, logout
- `/consentimientos/*` → CRUD de finalidades (obligatorias no modificables)
- `/arco/*` → derechos ARCO completos
- `/api/v1/*` → negocio (nlp, vehículo, histórico, comparativa)

## Sprint actual

| Sprint | Módulo | Estado |
|--------|--------|--------|
| 1 | Voice-based financial tracker | ✅ |
| 2 | PWA cabin dashboard (cockpit) | 🔄 En progreso |
| 3 | Vehicle maintenance module | ✅ |

El dashboard cockpit está diseñado para lectura periférica por conductores en movimiento: alto contraste, fuentes grandes, gestos simples.

## Poleana

- Motor Python con `PoleanaRuleSet` inyectable (TOURNAMENT_RULES / STREET_RULES)
- **Prioridad crítica:** migrar lógica de juego al servidor — la arquitectura actual es client-authoritative vía WebSocket (vulnerabilidad de manipulación de estado)
- El servidor debe ser la única fuente de verdad; el cliente solo envía intenciones

## Verificación

```bash
# Backend
cd backend && pytest --tb=short -q
cd backend && ruff check .

# Frontend
cd frontend && npm run typecheck
cd frontend && npm run test
cd frontend && npm run lint

# Infra
docker compose config --quiet
```

## Convenciones

- **Commits:** Conventional Commits en español (feat:, fix:, docs:, refactor:)
- **Ramas:** feature/, fix/, chore/ desde develop
- **Python:** tipado estricto, docstrings en español, ruff como linter
- **TypeScript:** strict mode, interfaces sobre types
- **Archivos nuevos:** header de licencia `# © YAGA Project` o `// © YAGA Project`

## Agentes disponibles

Este proyecto tiene subagentes especializados en `.claude/agents/`:
- `@agent-backend-security` — endpoints, modelos, auth, cifrado, ARCO
- `@agent-frontend` — componentes React, PWA, dashboard cockpit, consentimientos UI
- `@agent-devops-sre` — Docker, AWS, CI/CD, monitoreo, healthchecks
- `@agent-data-engineer` — ETL, anonimización, retención fiscal, dataset
- `@agent-security-engineer` — auditoría OWASP, WAF, hardening, revisión de PRs

## Comandos disponibles

- `/security-audit` — auditoría de seguridad completa
- `/sprint-status` — estado del sprint y cambios recientes
- `/arco-check` — verificación de compliance LFPDPPP
- `/poleana-audit` — estado de migración server-authoritative
