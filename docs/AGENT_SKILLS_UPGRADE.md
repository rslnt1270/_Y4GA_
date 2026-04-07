# © YAGA Project — Todos los derechos reservados
# AGENT SKILLS UPGRADE — Abril 2026

Plan de mejora y actualización de los subagentes especializados de YAGA.

---

## Resumen ejecutivo

Los agentes tenían desfases críticos con la arquitectura real. Este documento registra
los cambios aplicados, los casos de estudio incorporados, y el protocolo de orquestación
entre agentes.

---

## Desfases encontrados vs arquitectura real

| Agente | Desfase crítico | Impacto |
|--------|----------------|---------|
| backend | Documentaba JWT RS256 — real es HS256 | Causaría que el agente genere código con el sistema incorrecto |
| backend | Rutas de archivos incorrectas (SQLAlchemy vs asyncpg) | Código generado incompatible con el stack real |
| frontend | Describía React/TypeScript/Zustand — real es HTML vanilla | Agente propone stack que no existe |
| frontend | Auth en HttpOnly cookie — real es variable en memoria | Reproduce la vulnerabilidad del localStorage |
| security | No conocía el dual-auth system bug | No detectaría recurrencia del bug |
| devops | No documentaba el patrón `docker cp` para hot-reload | Destruiría contenedores innecesariamente |
| data | No conocía `viajes_historicos` con 3,299 registros | No podría responder consultas sobre el historial real |

---

## Cambios aplicados por agente

### @agent-backend-security
**Archivo**: `.claude/agents/backend.md`

Nuevas capacidades:
- Tabla comparativa de los dos sistemas de auth (HS256 vs RS256) con semáforo visual
- Protocolo de diagnóstico de 401 en 5 pasos ordenados
- Documentación del módulo forgot-password (tokens Redis, SMTP, flujo completo)
- Esquema real de `viajes_historicos` con notas sobre el tipo TEXT del `conductor_id`
- Instrucción de deploy via `docker cp` (código bakeado, no en volumen)
- Caso real documentado: 401 en cascada (abril 2026)

### @agent-frontend
**Archivo**: `.claude/agents/frontend.md`

Nuevas capacidades:
- Corrección de stack: HTML monolítico (no React/TS)
- Diagrama de secciones de `index.html` con líneas de referencia
- Auth flow real post-fix: `_authToken` en memoria, patrón `clearInterval`
- Flujo completo de forgot-password UI (3 formularios + detección de `?reset_token=`)
- Diagnóstico de service worker: aclaración de que SW no hace retry (el loop era el `setInterval`)
- Detección de Firefox vs Chrome para Web Speech API
- Caso real documentado: loop de 52 requests con 401

### @agent-devops-sre
**Archivo**: `.claude/agents/devops.md`

Nuevas capacidades:
- Host EC2 y PEM documentados explícitamente
- Patrón crítico `SCP → docker cp → WatchFiles reload` (código bakeado en imagen)
- Distinción entre nombre de servicio (`api`) y container name (`yaga_api`)
- Credenciales DB para consultas de administración
- Comandos de reset de contraseña desde el container (evitando escape de `$` en shell)
- Variables de entorno para SMTP (forgot-password)

### @agent-data-engineer
**Archivo**: `.claude/agents/data.md`

Nuevas capacidades:
- Tabla `viajes_historicos`: schema completo, 3,299 registros, conductor principal
- Snapshot de usuarios registrados (10 usuarios, estado abril 2026)
- Queries correctas con `::text cast` para UUID vs TEXT en JOINs
- Procedimiento seguro de reset de contraseña (usando Python/asyncpg para evitar escape de `$`)
- Aclaración: `lat/lng` en `viajes_historicos` son NUMERIC (sin cifrar), a diferencia de `jornada_gps_logs`

### @agent-security-engineer
**Archivo**: `.claude/agents/security.md`

Nuevas capacidades:
- Tabla de vulnerabilidades conocidas con estado (corregida/pendiente)
- Checklist actualizado con estado real del sistema
- Sección específica sobre riesgo del dual-auth system
- Comandos de auditoría rápida desde EC2
- Caso real documentado: dual auth 401 con análisis de vector, impacto y lección

---

## Caso de estudio: 401 en cascada (diagnóstico exitoso, abril 2026)

### Contexto
El usuario reportó que los comandos de voz no se registraban. La Network tab mostraba
52+ requests a `/resumen` con status 401, alternando entre `yaga/:1809` y `sw.js:75`.

### Protocolo de diagnóstico aplicado

**Paso 1 — Frontend** (agente frontend):
- Identificó que `setInterval(fetchResumen, 30000)` no manejaba 401
- Identificó que `resumenInterval` no tenía referencia (no podía cancelarse)
- Clarificó que el SW no hacía retry — el loop venía del `setInterval`

**Paso 2 — Backend** (agente backend):
- Leyó `app/dependencies.py` → encontró `verify_token` de `core/auth.py` (RS256)
- Comparó con `app/services/auth_service.py` → tokens son HS256
- Identificó root cause: sistema A (HS256) vs sistema B (RS256) incompatibles

**Paso 3 — Coordinación**:
- Backend fix: cambiar import en `dependencies.py` + rename `get_comparativa` (shadowing)
- Frontend fix: `fetchResumen` maneja 401, `resumenInterval` cancelable, guard `if (!token) return`
- Security fix: JWT de `_authToken` en memoria (eliminar localStorage)

**Resultado**: 3 archivos modificados, deploy via `docker cp`, `200 OK` confirmado en logs.

### Lecciones incorporadas a los agentes
1. Siempre verificar qué sistema de auth usa cada endpoint antes de cualquier cambio
2. `setInterval` sin referencia → bug de resources leak cuando hay error
3. El service worker aparece como initiator pero no es el causante del loop
4. El reset de contraseñas con bcrypt debe hacerse via Python — no con psql y shell escaping

---

## Protocolo de orquestación entre agentes

### Orden de invocación para diagnósticos
```
1. @agent-backend-security  → verificar logs y endpoint directo
2. @agent-frontend          → verificar Network tab y flujo de UI
3. @agent-security-engineer → evaluar si hay vulnerabilidad vs bug de config
4. @agent-devops-sre        → deploy del fix en EC2
5. @agent-data-engineer     → verificar integridad de datos en DB
```

### Contexto compartido obligatorio
Cuando un agente pase contexto a otro, debe incluir:
- Archivos modificados con rutas absolutas
- Sistema de auth en uso (HS256 en este proyecto)
- Estado de la DB (asyncpg pool, no SQLAlchemy)
- Método de deploy (docker cp, no restart)

### Formato de salida estandarizado
Todo diagnóstico debe incluir:
```
## Diagnóstico
**Síntoma**: [qué observó el usuario]
**Causa raíz**: [archivo:función — descripción exacta]
**Evidencia**: [log, respuesta HTTP, o snippet de código]

## Fix aplicado
[archivos modificados, cambio específico]

## Verificación
[comando ejecutado y respuesta esperada]

## Lección
[qué regla o patrón se agrega a los agentes]
```

---

## Vulnerabilidades pendientes (backlog de seguridad)

| Prioridad | Issue | Archivo | Sprint sugerido |
|-----------|-------|---------|-----------------|
| HIGH | JWT_SECRET hardcodeado como default | `services/auth_service.py:9` | Sprint 4 |
| HIGH | `pgp_sym_encrypt` en SQL | `routers/auth.py:50-51` | Sprint 4 |
| MEDIUM | Sistema B (RS256) no eliminado | `core/auth.py` | Sprint 5 |
| MEDIUM | No hay refresh token de sesión | Todo el auth flow | Sprint 5 |
| LOW | `lat/lng` sin cifrar en viajes_historicos | `viajes_historicos` | Sprint 6 |

---

## Próximas mejoras a los agentes (roadmap)

### Sprint 4
- Agente backend: conocer el endpoint de histórico (`/historico`) para servir `viajes_historicos` al dashboard
- Agente data: queries de análisis de eficiencia por día/semana para el dashboard

### Sprint 5
- Agente security: protocolo de rotación de JWT_SECRET sin downtime
- Agente frontend: implementar refresh token flow (HttpOnly cookie + interceptor)

### Sprint 6
- Agente architect: diseño de migración Docker → EKS con datos reales del EC2
- Todos los agentes: conocer el API de Poleana (WebSocket) para no interferir en deploys

---

## Verificación de actualización

```bash
# Confirmar que los agentes reflejan el stack real
grep "HS256" .claude/agents/backend.md        # debe aparecer como Sistema A
grep "HTML monolítico" .claude/agents/frontend.md  # debe aparecer
grep "docker cp" .claude/agents/devops.md    # debe aparecer como patrón de deploy
grep "viajes_historicos" .claude/agents/data.md   # debe aparecer con 3,299 registros
grep "dual auth" .claude/agents/security.md  # debe aparecer como riesgo documentado
```
