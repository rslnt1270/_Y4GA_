YAGA Project — Instrucciones del Proyecto
© YAGA Project — Todos los derechos reservados Todo archivo generado debe iniciar con comentario de licencia.

Qué es YAGA
Plataforma Fintech para conductores de Uber/DiDi en México. Registro de viajes y gastos por comandos de voz. Dominio: y4ga.app

Proyectos dentro del repositorio
YAGA PWA — Co-piloto financiero y asistente de jornadas para conductores
Poleana — Juego de mesa mexicano multijugador online (subdirectorio dentro del proyecto)

Stack REAL (verificado abril 2026)
Backend: FastAPI Python 3.11 · PostgreSQL 16 (asyncpg directo) · Redis 7
Frontend: HTML monolítico (frontend/index.html ~2,650 líneas) · CSS/JS vanilla inline · Sin React ni TypeScript en producción
Infra actual: Docker Compose en AWS EC2 t3.small (Amazon Linux 2023) · ec2-3-19-35-76.us-east-2.compute.amazonaws.com
Poleana: Cloudflare Pages (frontend) + mismo EC2 (backend Python WebSocket)
NLP: Clasificador determinista por keywords (7 intents, español MX, sub-200ms, sin LLM)
Auth: JWT HS256 via python-jose · bcrypt rounds=12 · Token en memoria JS (variable _authToken)

Esquema de base de datos
Tablas activas: usuarios, consentimientos, auditoria, jornadas, viajes, gastos, viajes_historicos, jornada_gps_logs (particionada por mes)

usuarios almacena email/phone en texto plano (indexado) Y cifrado AES-256 en columnas *_cifrado (BYTEA)
viajes_historicos contiene 3,299 registros importados (Jun 2024–Feb 2026), conductor_id es TEXT no UUID
consentimientos tiene restricción UNIQUE(usuario_id, finalidad) con flag es_obligatorio
auditoria registra toda acción crítica con IP, user_agent y detalles JSONB (solo Sistema B la usa actualmente)
Todas las PKs son UUID excepto auditoria (BIGSERIAL) y consentimientos (SERIAL)
Soft delete en usuarios via deleted_at

Seguridad — Reglas no negociables
Cifrado PII: AES-256-GCM en capa de aplicación con cryptography (módulo app/core/crypto.py → encrypt_value/decrypt_value). IV único por registro. PROHIBIDO usar pgp_sym_encrypt en SQL
Clave maestra: DB_ENCRYPT_KEY en env var. Nunca en código ni en imágenes Docker
JWT: HS256 via auth_service.py (Sistema A activo). Sistema B (RS256/SQLAlchemy) está DESHABILITADO — ver TODO en main.py
JWT_SECRET: env var obligatoria ≥32 chars. Si falta → WARNING CRITICAL + secret efímero (tokens se invalidan al reiniciar)
Refresh tokens: NO implementados aún (roadmap). Reset de contraseña via Redis TTL 3600s (un solo uso)
Frontend: JWT en memoria (_authToken = null en page load). PROHIBIDO localStorage/sessionStorage para tokens
Auditoría: roadmap — tabla auditoria existe pero Sistema B deshabilitado. Reimplementar en Sistema A
Secretos en K8s (roadmap): External Secrets Operator, nunca archivos montados

Sistema de Auth — CRÍTICO
SOLO existe un sistema activo: Sistema A (HS256)
Archivo activo: app/api/v1/auth.py + app/services/auth_service.py + app/dependencies.py
PROHIBIDO activar Sistema B (app/routers/auth.py) hasta migrar a core.crypto + asyncpg

Compliance LFPDPPP
Finalidades
operacion (obligatoria, no revocable): cuentas, pagos, KYC, fiscal
marketing (secundaria, opt-out): promociones y comunicaciones
investigacion (secundaria, opt-out): análisis agregado, mejora de servicio

Derechos ARCO
GET /arco/acceso → JSON con datos personales + transaccionales
PUT /arco/rectificacion → actualiza email/phone, re-cifra con AES-256, valida unicidad
POST /arco/cancelacion → soft delete, anonimiza PII con placeholders, retiene transaccionales 7 años sin relación al usuario
POST /arco/oposicion → revoca finalidad secundaria sin afectar servicio principal
Cada acción ARCO debe registrarse en auditoria con accion = arco_* y detalles JSON (pendiente en Sistema A)

Endpoints principales (Sistema A activo)
/api/v1/auth/* → registro, login, me, forgot-password, reset-password
/api/v1/command → NLP: registrar viaje/gasto, consultar resumen, cerrar jornada
/api/v1/resumen → resumen de jornada actual
/api/v1/comparativa → comparativa vs histórico
/api/v1/historico → viajes_historicos del conductor
/api/v1/gps/* → GPS batch upload (cifrado AES-256)
/api/v1/vehiculo/* → mantenimiento vehicular
/api/v1/jornada/cerrar → cerrar jornada (autenticado, promedio histórico real)
/ws/poleana/* → WebSocket del juego de mesa

Deploy — Patrón de producción
El código Python está bakeado en la imagen Docker (no hay volumen de código).
Para actualizar sin rebuild:
  scp archivo.py ec2-user@EC2:~/yaga-project/app/...
  docker cp ~/yaga-project/app/... yaga_api:/app/...
  WatchFiles recarga automáticamente (uvicorn --reload)
Frontend estático: scp frontend/index.html EC2:~/yaga-project/frontend/index.html

Sprint actual
Sprint	Módulo	Estado
1	Voice-based financial tracker	✅
2	PWA cabin dashboard (cockpit)	✅ (HTML monolítico con JS vanilla)
3	GPS tracking cifrado + módulo vehicular	✅
4	Forgot password + fixes auth	✅
4	Vulnerabilidades 6.1-6.4 corregidas	✅

Vulnerabilidades pendientes (backlog seguridad)
6.5 Poleana client-authoritative: cliente envía estado completo — servidor debe ser única fuente de verdad
6.6 Rooms in-memory: _rooms dict se pierde en restart — migrar a Redis
6.7 Rate limiting: slowapi no implementado en main.py — agregar en Sprint 5
Sistema B legacy: archivos app/routers/ y app/core/auth.py deben eliminarse tras validar que nada los usa

Poleana
Motor Python con PoleanaRuleSet inyectable (TOURNAMENT_RULES / STREET_RULES)
Fixes aplicados abril 2026: turnos invertidos corregidos, tablero bloqueado corregido, offline mode implementado
Prioridad crítica: migrar lógica de juego al servidor — la arquitectura actual sigue siendo parcialmente client-authoritative
El servidor debe ser la única fuente de verdad; el cliente solo envía intenciones (ROLL, MOVE)

Verificación
# Backend (desde el container en EC2)
docker exec yaga_api python3 -m pytest /app/tests/ -q 2>/dev/null || echo "Sin tests configurados"
curl -s http://localhost:8000/health

# Frontend
# No hay npm — es HTML estático. Verificar manualmente en browser.

# Infra
docker compose config --quiet
docker ps --format 'table {{.Names}}\t{{.Status}}'

Convenciones
Commits: Conventional Commits en español (feat:, fix:, docs:, refactor:, security:)
Ramas: feature/, fix/, chore/, security/ desde main
Python: tipado estricto, docstrings en español, ruff como linter
Archivos nuevos: header de licencia # © YAGA Project o // © YAGA Project
NO agregar recursos AWS extra sin aprobación explícita (restricción de costo)

Agentes disponibles
Este proyecto tiene subagentes especializados en .claude/agents/:

@agent-backend-security — endpoints FastAPI, asyncpg, auth HS256, cifrado AES-256, ARCO, NLP
@agent-frontend — dashboard cockpit HTML/JS vanilla, forgot-password UI, offline-first, service worker
@agent-devops-sre — Docker EC2, SSH/SCP, docker cp, CI/CD, monitoreo
@agent-data-engineer — PostgreSQL, viajes_historicos, migraciones, anonimización, dataset
@agent-security-engineer — auditoría OWASP, vulnerabilidades, compliance LFPDPPP, checklist

Documentación actualizada
docs/ARQUITECTURA_ACTUAL.md — stack real, endpoints, vulnerabilidades verificadas
docs/WORKFLOW_VOZ.md — diagramas Mermaid del flujo voz→DB
docs/AGENT_SKILLS_UPGRADE.md — caso de estudio 401, protocolo de orquestación

Comandos disponibles
/security-audit — auditoría de seguridad completa
/sprint-plan — planificación del sprint
/arco-check — verificación de compliance LFPDPPP
/poleana-audit — estado de migración server-authoritative

# Optimización de tokens
Consulta también el archivo CLAUDE_RULES.md para directrices de eficiencia de tokens.
