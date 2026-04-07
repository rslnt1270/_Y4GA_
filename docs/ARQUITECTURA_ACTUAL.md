# YAGA — Arquitectura Actual (abril 2026)

Documento verificado contra el codigo fuente en produccion. No incluye roadmap ni aspiraciones.

---

## 1. Stack tecnologico

| Capa | Tecnologia | Version | Notas |
|------|-----------|---------|-------|
| Backend | FastAPI (Python) | 0.5.0 | Monolito modular, un solo proceso |
| Base de datos | PostgreSQL | 16-alpine | asyncpg (pool 2-10 conexiones) |
| Cache | Redis | 7-alpine | maxmemory 128MB, allkeys-lru |
| ORM parcial | SQLAlchemy async | - | Solo en `routers/auth.py` y `dependencies.py` (Sistema B) |
| DB directa | asyncpg | - | En `services/database.py` (Sistema A: jornadas, viajes, gastos, auth) |
| Cifrado PII | cryptography (AESGCM) | - | AES-256-GCM, IV 12 bytes + tag 16 bytes |
| Auth JWT | python-jose + bcrypt | - | HS256, secret en env var |
| Frontend | HTML/CSS/JS monolitico | - | Un solo `index.html` (~2700 lineas), no React/TS |
| PWA | Service Worker + manifest | - | Scope `/yaga/`, offline parcial |
| Voz | Web Speech API | - | `webkitSpeechRecognition`, solo Chrome/Edge |
| NLP | Clasificador determinista | - | 7 intents, keyword matching, sin LLM |
| Infra | Docker Compose en EC2 | t3.small | Amazon Linux 2023 |
| Proxy | Nginx | - | Reverse proxy a localhost:8000 |
| Poleana | Mismo backend FastAPI | - | Router con WebSocket, rooms in-memory |

**Nota critica sobre el frontend:** CLAUDE.md describe "PWA React 18+ TypeScript + Vite + Tailwind". En produccion el frontend es un **archivo HTML monolitico con vanilla JS**. No hay build step, no hay React, no hay TypeScript, no hay Vite.

---

## 2. Mapa de endpoints

### 2.1 Autenticacion (Sistema A — `api/v1/auth.py`)

| Metodo | URL | Funcion | Servicio | Tabla DB |
|--------|-----|---------|----------|----------|
| POST | `/api/v1/auth/register` | `register()` | `auth_service.hash_password`, `crypto.encrypt_value` | `usuarios` |
| POST | `/api/v1/auth/login` | `login()` | `auth_service.verify_password`, `create_token` | `usuarios` |
| GET | `/api/v1/auth/me` | `me()` | `auth_service.decode_token` | `usuarios` |
| POST | `/api/v1/auth/forgot-password` | `forgot_password()` | Redis `reset:{token}` TTL 1h, SMTP | `usuarios` |
| POST | `/api/v1/auth/reset-password` | `reset_password()` | Redis lookup + `hash_password` | `usuarios` |

### 2.2 Autenticacion (Sistema B — `routers/auth.py`) [LEGACY/DUAL]

| Metodo | URL | Funcion | Servicio | Tabla DB |
|--------|-----|---------|----------|----------|
| POST | `/auth/register` | `register()` | SQLAlchemy + `pgp_sym_encrypt` | `usuarios` |
| POST | `/auth/login` | `login()` | SQLAlchemy + `core.security` | `usuarios` |
| POST | `/auth/refresh` | `refresh()` | Redis refresh tokens | - |
| POST | `/auth/logout` | `logout()` | Redis blacklist | `auditoria` |

### 2.3 Comandos y NLP (`api/v1/nlp.py`)

| Metodo | URL | Funcion | Servicio | Tabla DB |
|--------|-----|---------|----------|----------|
| POST | `/api/v1/command` | `process_command()` | `classify()` + `jornada_service.*` | `jornadas`, `viajes`, `gastos` |
| GET | `/api/v1/resumen` | `get_resumen()` | `jornada_service.get_resumen_jornada` | `jornadas`, `viajes`, `gastos` |
| GET | `/api/v1/comparativa` | `comparativa_endpoint()` | `jornada_service.get_comparativa` | `jornadas`, `viajes` |

### 2.4 Vehiculo (`api/v1/vehiculo.py`)

| Metodo | URL | Funcion | Tabla DB |
|--------|-----|---------|----------|
| GET | `/api/v1/vehiculo` | `fetchVehiculo` (frontend) | `vehiculos` |
| POST | `/api/v1/vehiculo/km` | Registrar km | `vehiculos` |
| POST | `/api/v1/vehiculo/aceite` | Reset aceite | `vehiculos` |
| POST | `/api/v1/vehiculo/servicio` | Reset servicio | `vehiculos` |
| POST | `/api/v1/vehiculo/perfil` | Crear/actualizar perfil | `vehiculos` |

### 2.5 Historico (`api/v1/historico.py`)

| Metodo | URL | Funcion | Tabla DB |
|--------|-----|---------|----------|
| GET | `/api/v1/historico/mapa` | Datos para heatmap | `viajes_historicos` |
| POST | `/api/v1/historico/import/json` | Import CSV/JSON | `viajes_historicos` |

### 2.6 GPS (`api/v1/gps.py`)

| Metodo | URL | Funcion | Tabla DB |
|--------|-----|---------|----------|
| POST | `/api/v1/gps/track` | Registrar coordenada cifrada | `gps_tracks` |

### 2.7 Poleana (`api/poleana_router.py`)

| Metodo | URL | Funcion | Tabla DB |
|--------|-----|---------|----------|
| GET | `/api/v1/poleana/health` | Health check | - |
| POST | `/api/v1/poleana/register` | Registro usuario Poleana | `poleana_users` |
| POST | `/api/v1/poleana/login` | Login Poleana | `poleana_users` |
| GET | `/api/v1/poleana/stats/{username}` | Estadisticas jugador | `poleana_users` |
| POST | `/api/v1/poleana/games` | Crear sala | `poleana_games` + in-memory `_rooms` |
| GET | `/api/v1/poleana/games/{code}` | Info sala | in-memory `_rooms` |
| WS | `/api/v1/poleana/ws/{code}` | Juego en tiempo real | in-memory `_rooms` |

### 2.8 Otros

| Metodo | URL | Funcion | Notas |
|--------|-----|---------|-------|
| GET | `/health` | `health()` | Healthcheck Docker/Nginx |
| POST | `/api/v1/jornada/cerrar` | `cerrar_jornada()` | Legacy, sin autenticacion, hardcodea HISTORICO_REF=72.94 |
| - | `/consentimientos/*` | CRUD consentimientos | Router LFPDPPP |

---

## 3. Flujo de autenticacion

```
1. Usuario ingresa email + password en la PWA
2. Frontend: doLogin() → POST /api/v1/auth/login
   Body: { email, password }

3. Backend auth.py:
   a. Normaliza email (lowercase, strip)
   b. SELECT id, nombre, password_hash FROM usuarios WHERE email = $1 AND deleted_at IS NULL
   c. bcrypt.checkpw(password, password_hash)
   d. Si valido: create_token(conductor_id, email)
      → jwt.encode({ sub: conductor_id, email, exp: now+7d }, JWT_SECRET, HS256)
   e. Response: { token, conductor_id, nombre }

4. Frontend:
   a. _authToken = token  (variable JS en memoria, NUNCA localStorage)
   b. localStorage/sessionStorage: conductor_id, nombre, email (datos no sensibles)
   c. Oculta authScreen, muestra dashboard

5. Requests autenticados:
   Headers: { Authorization: "Bearer " + getToken() }

6. Validacion en backend (dependencies.py):
   a. OAuth2PasswordBearer extrae token del header
   b. decode_token(token) → jwt.decode(token, JWT_SECRET, HS256)
   c. SELECT Usuario WHERE id = payload.sub AND deleted_at IS NULL
   d. Retorna objeto Usuario o 401

7. Polling:
   setInterval(fetchResumen, 30000) — refresca dashboard cada 30s

8. Sesion:
   - Al recargar pagina: _authToken = null → usuario debe hacer login de nuevo
   - 401 en cualquier fetch → clearInterval + clearSession + mostrar login
```

---

## 4. Flujo de registro de comando de voz

Secuencia completa desde que el conductor habla hasta que el dato esta en PostgreSQL:

```
PASO 1 — Captura de audio
  Navegador: Web Speech API (webkitSpeechRecognition)
  recognition.lang = 'es-MX'
  recognition.continuous = false
  recognition.interimResults = false
  Conductor presiona boton microfono → recognition.start()

PASO 2 — Transcripcion
  recognition.onresult → transcript = e.results[0][0].transcript
  Se muestra en cmdInput.value

PASO 3 — Envio al backend
  sendCommand(transcript) →
  POST /api/v1/command
  Headers: { Content-Type: application/json, Authorization: Bearer + token }
  Body: { text: transcript }

PASO 4 — Autenticacion
  FastAPI dependency: get_current_user(token)
  → decode_token(token) usando jose.jwt.decode(token, JWT_SECRET, HS256)
  → payload.sub = conductor_id
  → SQLAlchemy: SELECT Usuario WHERE id = conductor_id AND deleted_at IS NULL
  → Retorna objeto Usuario con user.id

PASO 5 — Clasificacion NLP
  classify(text):
  a. normalize(text) — NFKD, lowercase, remove combining chars
  b. Para cada IntentPattern en INTENT_PATTERNS:
     - Busca keywords que aparezcan en el texto normalizado
     - Score = matched/total + bonus por longitud de keywords
  c. Selecciona intent con mayor score
  d. extract_entities(text):
     - Montos: regex \d+(\.\d+)?
     - Plataforma: uber/didi/cabify/indriver (default: uber)
     - Metodo pago: efectivo/cash → "efectivo", else → "app"
     - Propina: logica especial si "propina" en texto
  e. Retorna ClassificationResult(intent, confidence, entities)

  Intents disponibles (7):
  - INICIAR_JORNADA, CERRAR_JORNADA
  - REGISTRAR_VIAJE, REGISTRAR_GASTO
  - CONSULTAR_RESUMEN, CONSULTAR_TOTAL
  - UNKNOWN

PASO 6 — Logica de negocio (jornada_service.py)
  Interceptor: si "cerrar" + "jornada" en texto → cerrar_jornada directamente
  Si UNKNOWN → responder con sugerencia de ejemplo
  Si CONSULTAR_RESUMEN → get_resumen_jornada(conductor_id)
  Si REGISTRAR_VIAJE o REGISTRAR_GASTO:
    a. get_or_create_jornada(conductor_id)
       → SELECT jornadas WHERE conductor_id AND fecha=today AND estado='activa'
       → Si no existe: INSERT INTO jornadas(...) RETURNING id
    b. registrar_viaje(jornada_id, entities):
       → INSERT INTO viajes (jornada_id, monto, propina, plataforma, metodo_pago)
       o registrar_gasto(jornada_id, entities):
       → INSERT INTO gastos (jornada_id, monto, categoria)

PASO 7 — Persistencia
  asyncpg pool (2-10 conexiones) → PostgreSQL 16
  Conexion directa via pool.acquire(), NO via SQLAlchemy
  Retorna dict con datos insertados (id, monto, plataforma, etc.)

PASO 8 — Response al frontend
  { intent: "registrar_viaje", message: "Viaje guardado: $90 en uber (efectivo)", data: {...} }

PASO 9 — Actualizacion de UI
  a. showToast(data.message, 'success') — notificacion temporal 3s
  b. Si intent != cerrar_jornada: fetchResumen()
     → GET /api/v1/resumen + Bearer token
     → Retorna { total_viajes, ingresos_brutos, total_gastos, ganancia_neta, viajes_detalle, gastos_detalle }
  c. renderResumen(data):
     - Actualiza totalViajes, ingresosBrutos, totalGastos, gananciaNeta
     - Renderiza lista de viajes en tripsList
     - Actualiza barras de metricas
  d. statusDot cambia a verde (accent) si OK, rojo (danger) si error
```

---

## 5. Estado de datos en DB

- **Usuarios:** 10 registros en tabla `usuarios`
- **Viajes historicos:** 3,299 registros en `viajes_historicos` (importados de y.ortega.316197595@gmail.com)
- **Tablas principales:** usuarios, consentimientos, auditoria, jornadas, viajes, gastos, vehiculos, gps_tracks, viajes_historicos
- **Tablas Poleana:** poleana_users, poleana_games

---

## 6. Vulnerabilidades conocidas

### 6.1 Sistema dual de autenticacion

Existen **dos sistemas de auth corriendo simultaneamente**:

| | Sistema A (`api/v1/auth.py`) | Sistema B (`routers/auth.py`) |
|---|---|---|
| Prefijo | `/api/v1/auth/*` | `/auth/*` |
| DB driver | asyncpg directo | SQLAlchemy async |
| Cifrado PII | `crypto.encrypt_value` (AES-256-GCM) | `pgp_sym_encrypt` (pgcrypto en SQL) |
| JWT | HS256 via `jose` | Posiblemente RS256 via `core.auth` |
| Refresh tokens | No implementado | Redis `refresh:{user_id}` |
| Auditoria | No | Si (tabla `auditoria`) |

**Riesgo:** El frontend solo consume Sistema A. Sistema B esta montado en el router pero nadie lo llama desde la PWA. Sin embargo, sus endpoints estan expuestos y accesibles.

### 6.2 JWT_SECRET hardcodeado

```python
SECRET_KEY = os.getenv("JWT_SECRET", "yaga-secret-2026-change-in-prod")
```

Si `JWT_SECRET` no esta configurado como variable de entorno, el fallback es un string predecible. Cualquier persona que lea este codigo puede firmar tokens validos.

### 6.3 pgp_sym_encrypt en Sistema B

`routers/auth.py` usa `func.pgp_sym_encrypt(user_data.email, os.getenv("DB_ENCRYPT_KEY"))`, violando la regla "PROHIBIDO usar pgp_sym_encrypt en SQL" de CLAUDE.md. El cifrado debe ser en capa de aplicacion (como hace Sistema A con `core.crypto`).

### 6.4 Endpoint legacy sin autenticacion

`POST /api/v1/jornada/cerrar` en `main.py` cierra la jornada activa de **cualquier conductor** sin requerir token. Ademas, hardcodea `HISTORICO_REF = 72.94` en lugar de calcularlo dinamicamente.

### 6.5 Poleana: client-authoritative

El WebSocket de Poleana acepta `STATE` del cliente y lo rebroadcastea. Solo valida turno pero el cliente envia el estado completo del juego. Vulnerable a manipulacion.

### 6.6 Rooms in-memory

`_rooms: dict = {}` en `poleana_router.py` se pierde en cada restart del container. No hay persistencia de partidas activas.

### 6.7 CORS restringido pero endpoints abiertos

CORS solo permite `y4ga.app` pero los endpoints no tienen rate limiting implementado (slowapi esta en CLAUDE.md como requerimiento pero no se ve en `main.py`).

---

## 7. Infraestructura EC2

### 7.1 Containers (Docker Compose)

```
yaga_postgres  — postgres:16-alpine     — puerto 5432
yaga_redis     — redis:7-alpine         — puerto 6379 (128MB max)
yaga_api       — build ./app            — puerto 8000
```

### 7.2 Volumenes

- `postgres_data` — persistencia de datos PostgreSQL
- `./secrets:/app/secrets:ro` — claves JWT RSA (montadas pero usadas solo por Sistema B)

### 7.3 Patron de deploy

```bash
# Desde maquina local:
docker cp ./app yaga_api:/app
docker restart yaga_api

# O rebuild completo:
docker compose up -d --build api
```

No hay CI/CD. Los deploys son manuales via SSH + docker cp.

### 7.4 Healthchecks

- PostgreSQL: `pg_isready -U yaga_user -d yaga_db` cada 10s
- Redis: `redis-cli ping` cada 10s
- API: `curl -sf http://localhost:8000/health` cada 30s

### 7.5 Nginx

Reverse proxy en el host EC2 (no containerizado):
- `y4ga.app/api/*` → `localhost:8000`
- `y4ga.app/yaga/*` → archivos estaticos del frontend
- SSL via Let's Encrypt / certbot

### 7.6 Labels K8s

Todos los servicios tienen labels `app.kubernetes.io/*` preparando migracion a EKS, pero actualmente no tienen efecto.

---

## Apendice: Discrepancias CLAUDE.md vs realidad

| CLAUDE.md dice | Realidad |
|----------------|----------|
| Frontend: PWA React 18+ TypeScript + Vite + Tailwind | HTML monolitico + vanilla JS |
| JWT: RS256 con RSA 2048-bit | HS256 con secret string (Sistema A) |
| Rate limiting: slowapi + Redis | No implementado |
| Refresh tokens: Redis TTL 7d | Solo en Sistema B (no usado por frontend) |
| Frontend: JWT en memoria, refresh en HttpOnly cookie | JWT en memoria (correcto), no hay refresh token en cookie |
| Poleana: Cloudflare Pages (frontend) | Frontend Poleana servido desde mismo EC2 |
