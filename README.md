# YAGA

**Co-piloto financiero por voz para conductores de Uber y DiDi en México.**

![Python](https://img.shields.io/badge/python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)
![PWA](https://img.shields.io/badge/PWA-offline--first-5A0FC8)
![License](https://img.shields.io/badge/license-Proprietary-lightgrey)

Dominio: **[y4ga.app](https://y4ga.app)** · Fase de validación con ~50 conductores piloto.

---

## Qué es YAGA

Los conductores de plataforma en México manejan 10 a 14 horas diarias y rara vez pueden detenerse a capturar cada viaje, cada gasto de gasolina o cada propina. Al final de la semana no saben cuánto ganaron realmente después de restar combustible, comisiones y mantenimiento. Las apps de contabilidad tradicionales piden demasiado y se vuelven una carga extra; las hojas de Excel se abandonan en dos semanas.

YAGA resuelve ese problema con **una sola interfaz: la voz**. El conductor dice "registra viaje de 180 pesos en Uber efectivo" y la app lo guarda, lo compara contra su histórico, lo suma a la jornada del día y le responde en voz alta cuánto lleva ganado. Todo sin soltar el volante, sin teclear, sin tocar la pantalla más que para encender el cockpit al iniciar el turno.

El producto es una **PWA offline-first** que funciona en cualquier Android de gama media, se instala como app nativa y sigue registrando viajes aunque el conductor pierda cobertura en un túnel o en un estacionamiento subterráneo. Cuando vuelve la red, sincroniza en batch. La interfaz está diseñada como tablero de cabina: alto contraste, lectura periférica, cero scroll en la información crítica.

---

## Cómo funciona el NLP

El clasificador de intenciones es **determinista por keywords + regex**, en español mexicano, sin LLMs ni llamadas externas. Esta decisión no es accidental:

- **Latencia sub-200ms** end-to-end (clasificación + extracción + persistencia), imprescindible para que el conductor sienta respuesta inmediata mientras maneja.
- **Costo marginal cero** por request — no hay tarifas de API por viaje registrado.
- **Predictibilidad total**: cada frase que funciona, seguirá funcionando exactamente igual mañana.
- **Privacidad**: el audio nunca sale del dispositivo hasta que es texto, y el texto nunca sale de nuestra infraestructura.

El motor reconoce **13 intents**: `registrar_viaje`, `registrar_gasto`, `consultar_resumen`, `consultar_comparativa`, `consultar_historico`, `cerrar_jornada`, `abrir_jornada`, `consultar_vehiculo`, `registrar_mantenimiento`, `consultar_arco`, `registrar_propina`, `corregir_ultimo`, `ayuda`.

Ejemplo real de clasificación y extracción:

```python
INTENTS = {
    "registrar_viaje": [
        r"\b(registra|anota|apunta|suma)\b.*\b(viaje|carrera|servicio)\b",
        r"\bhice un viaje\b",
    ],
    "registrar_gasto": [
        r"\b(gasto|gaste|gasté|pague|pagué)\b.*\b(gasolina|comida|peaje|taller)\b",
    ],
}

MONTO_RE      = re.compile(r"(?:\$|mxn|pesos?)?\s*(\d+(?:[.,]\d{1,2})?)", re.I)
PLATAFORMA    = {"uber", "didi", "cabify", "indrive"}
METODO_PAGO   = {"efectivo", "tarjeta", "app", "qr"}

# "registra viaje de 180 pesos en Uber efectivo con 20 de propina"
# → intent: registrar_viaje
# → entidades: { monto: 180.00, plataforma: "uber",
#                metodo: "efectivo", propina: 20.00 }
```

Si ninguna regla matchea, el comando cae al intent `desconocido` y se registra en la tabla `nlp_failed_commands`. Esa tabla es la fuente de verdad para refinar patrones — en lugar de "entrenar un modelo", nosotros leemos frases reales cada semana y extendemos las regex.

---

## Flujo GPS end-to-end

El GPS no solo dibuja una línea en un mapa: alimenta las comparativas de eficiencia (km por peso ganado) y detecta tiempos muertos. Todo cifrado en reposo.

```text
Navegador                Filtro              Cifrado AES-256      Batch (30s)
(watchPosition)   →   accuracy ≤ 50m    →   IV único/registro →  hasta 60 pts
enableHighAccuracy    velocidad ≤ 300     lat/lng/speed BYTEA        │
maximumAge: 5000      km/h (anti-salto)                              ▼
                                                           POST /api/v1/gps/batch
                                                                     │
                                                                     ▼
                                               PostgreSQL jornada_gps_logs
                                               (particionada por mes, índice
                                                temporal en columna plana)
                                                                     │
                                                                     ▼
                                          Leaflet + OSM tiles en cockpit
                                          (descifrado server-side, solo el
                                           dueño del viaje ve sus datos)
```

El filtrado en cliente descarta lecturas con `accuracy > 50m` y rechaza puntos que implicarían velocidad imposible respecto al anterior (típicamente saltos de GPS en zonas urbanas densas). El cifrado es **AES-256-GCM** con IV único por registro, ejecutado en la capa de aplicación — **nunca** con `pgp_sym_encrypt` en SQL, para evitar que la clave circule por el motor de base de datos.

---

## Arquitectura e infraestructura

| Capa          | Tecnología                                                                      |
|---------------|----------------------------------------------------------------------------------|
| Backend       | FastAPI (Python 3.11), asyncpg directo (sin ORM), JWT HS256, bcrypt rounds=12   |
| Base de datos | PostgreSQL 16 con particionado por mes en tablas de alto volumen                 |
| Cache / sesión| Valkey (compatible Redis 7) para refresh tokens y rate limiting                  |
| Frontend      | HTML monolítico (~2,700 líneas), JS/CSS vanilla inline, Service Worker, PWA      |
| Infra         | Docker Compose sobre AWS EC2 **t3.small** en `us-east-2`, nginx + Let's Encrypt  |
| CDN / DNS     | Cloudflare (free tier) + Route53                                                 |

**Costo mensual total** de toda la stack de producción:

| Recurso                        | Costo aprox. |
|--------------------------------|--------------|
| EC2 t3.small on-demand         | ~$17         |
| EBS gp3 20 GB                  | ~$1.6        |
| Elastic IP (in-use)            | $0           |
| Cloudflare (free tier)         | $0           |
| Route53 (zona hosted)          | ~$0.5        |
| **Total**                      | **~$20/mes** |

¿Por qué una sola t3.small soporta la carga actual? Porque el tráfico real es **<1 req/s promedio** y los picos de voz consumen <200ms de CPU. Sobre-dimensionar antes de tiempo es la forma más rápida de quemar runway sin aprender nada del producto.

La autenticación vive en dos niveles: **access token JWT en memoria JS** (nunca en `localStorage`, se pierde al recargar — comportamiento intencional), y **refresh token en cookie `yaga_rt` HttpOnly + Secure + SameSite=Strict**, con rotación en cada uso, detección de reuse por familia y store en Valkey.

---

## Desarrollo con subagentes Claude Code

Este repo es desarrollado por una sola persona apoyada en un pipeline de **subagentes especializados** de Claude Code, cada uno con su contexto y sus reglas:

| Subagente                  | Responsabilidad                                                |
|----------------------------|----------------------------------------------------------------|
| `@agent-backend-security`  | Endpoints FastAPI, asyncpg, cifrado, ARCO, NLP                 |
| `@agent-frontend`          | Cockpit HTML/JS vanilla, service worker, comandos de voz       |
| `@agent-devops-sre`        | Docker en EC2, SSH, `docker cp`, CI/CD                         |
| `@agent-data-engineer`     | SQL, migraciones, anonimización, datasets                      |
| `@agent-security-engineer` | OWASP, LFPDPPP, auditorías de vulnerabilidad                   |
| `@agent-architect`         | Decisiones arquitectónicas, trade-offs, roadmap                |

Cada agente tiene sus propias directrices de contexto (archivos, comandos, convenciones) y puede invocar los demás cuando una tarea cruza dominios. La velocidad observada versus un equipo tradicional equivalente ronda el **2.5x–3x**: un sprint completo que incluyó refresh tokens con rotación, frontend integrado y suite de tests se resolvió en una sola jornada de desarrollo.

El valor no está en escribir código más rápido — está en que cada rol entra al problema con el contexto correcto ya cargado, sin context switching humano.

---

## Roadmap de escalabilidad

El stack actual es deliberadamente simple y tiene un camino claro de crecimiento:

| Fase                          | Usuarios      | Infra                                                                                      |
|-------------------------------|---------------|---------------------------------------------------------------------------------------------|
| Hoy (validación)              | <100          | Docker Compose + EC2 única                                                                  |
| Crecimiento                   | 100 – 1,000   | RDS Multi-AZ para Postgres, ElastiCache para Valkey, CloudFront/S3 para frontend            |
| Escala                        | >1,000 o ≥3 devs | EKS con HPA, External Secrets Operator, OpenTelemetry + CloudWatch, blue-green con Argo Rollouts |

El código ya está dockerizado de forma idempotente y sigue 12-factor desde el día uno, así que el salto a Kubernetes no implica reescribir — implica empaquetar.

---

## Análisis técnico integral

Esta sección condensa las decisiones de ingeniería que sostienen el stack actual, por qué se eligieron así y cómo están preparadas para escalar sin reescrituras dolorosas.

### Infraestructura y optimización de costo

La producción corre sobre una única **EC2 t3.small** con **Elastic IP fija** en `us-east-2`, orquestada por Docker Compose. Sobre esa instancia conviven cuatro contenedores con healthchecks individuales:

```text
EC2 t3.small (2 GB RAM, 2 vCPU burstable)
┌──────────────────────────────────────────────────┐
│  WAF (ModSecurity CRS + nginx)   ~80 MB          │
│  api  (FastAPI + uvicorn)        ~180 MB         │
│  postgres 16                     ~220 MB         │
│  valkey 7 (Redis-compatible)     ~40 MB          │
│  ───────────────────────────────────────         │
│  Uso total ≈ 560 MB  (~28% de RAM disponible)    │
└──────────────────────────────────────────────────┘
```

La densidad ronda el **28% de RAM utilizada**, dejando espacio para picos de tráfico y para Postgres antes de necesitar un nodo aparte. El costo total de la plataforma es de **~$15–20 USD/mes**. Este es el modelo "compute a demanda" correcto para la fase de validación: pagar solo por lo que mueve el producto.

### FastAPI como columna vertebral

Se eligió **FastAPI** sobre Django o Flask por cuatro razones concretas: validación declarativa con Pydantic v2, async nativo del runtime, capacidad de exponer **WebSockets** (Poleana) sobre la misma aplicación que sirve los endpoints REST, y ausencia de ORM — usamos `asyncpg` directo con **pool de 2 a 10 conexiones**. Evitamos la abstracción de SQLAlchemy porque cada milisegundo cuenta en la respuesta al conductor y porque las consultas son pocas, pero muy calientes. El rate limiting vive en `slowapi` con políticas estrictas en los endpoints sensibles (login, registro) y más laxas en telemetría (GPS batch).

### Docker y el patrón `docker cp` + WatchFiles

El código Python se **bakea** dentro de la imagen Docker. Para actualizar sin rebuild completo, copiamos el archivo al contenedor con `docker cp` y dejamos que **WatchFiles** (uvicorn `--reload`) recargue el proceso en **<2 segundos**. Un rebuild tradicional tomaría 60–90 segundos y obligaría a reiniciar el contenedor. El volumen `postgres_data` es el único estado persistente real; todo lo demás es recreable. Los cuatro servicios tienen `healthcheck` propio, de modo que Compose puede orquestar el orden de arranque correctamente. La migración de **Redis a Valkey** (Sprint 7) ya está hecha, motivada por el cambio de licencia de Redis (SSPL) hacia una licencia BSD más permisiva.

### Desarrollo multi-agente con Claude Code

Seis subagentes especializados (`backend-security`, `frontend`, `devops-sre`, `data-engineer`, `security-engineer`, `architect`) se orquestan con un protocolo de contexto compartido. La diferencia clave frente a "usar un LLM generalista" es que cada agente arranca con su dominio precargado: rutas, convenciones, reglas de seguridad y memoria institucional acumulada sprint a sprint.

| Actividad                  | Con subagentes Claude Code | Equipo tradicional      |
|----------------------------|----------------------------|-------------------------|
| 9 sprints completos        | 10 semanas                 | 22–30 semanas estimadas |
| Sprint con múltiples capas | 1 jornada                  | 1–2 semanas             |
| Context switching humano   | delegado al agente         | alto                    |

La aceleración observada es de **2.5x a 3x**, no porque se escriba código más rápido, sino porque el rol correcto entra al problema con contexto correcto y sin costo de re-orientación.

### Logística de escalabilidad

| Fase                 | Usuarios       | Stack                                                  | Costo aprox. |
|----------------------|----------------|--------------------------------------------------------|--------------|
| 1 — Validación (hoy) | ~50–100        | EC2 única + Docker Compose                             | ~$20/mes     |
| 2 — Crecimiento      | 500 – 1,000    | EKS + RDS Multi-AZ + ElastiCache + CloudFront          | ~$200–400/mes|
| 3 — Escala regional  | >10,000        | Multi-región + CDN edge + réplicas de lectura          | ~$1,000+/mes |

La preparación para la fase 2 ya está hecha: labels compatibles con Kubernetes en `docker-compose.yml`, secretos externalizables, healthchecks estandarizados, código 12-factor. Haber arrancado directamente en EKS hubiera significado ~$150–200/mes de gasto mínimo antes de tener un solo usuario — un **90% de overhead** en la fase donde lo importante es aprender del producto, no del clúster.

---

## Estructura del repositorio

```text
.
├── app/                    # Backend FastAPI
│   ├── api/v1/             # Routers versionados (auth, command, resumen, gps, arco)
│   ├── services/           # auth_service, nlp_service, refresh_service
│   ├── core/               # crypto, config, logging
│   └── main.py
├── frontend/
│   ├── index.html          # PWA monolítica, cockpit + auth + mapa
│   ├── sw.js               # Service Worker offline-first
│   └── public/manifest.json
├── Poleana_Project/        # Juego de mesa mexicano multijugador (WebSocket, submódulo)
├── nginx/
│   └── conf.d/             # WAF + reglas de proxy (ModSecurity CRS)
├── infrastructure/
│   └── database/migrations/
├── scripts/                # backup, operaciones de producción
├── docs/                   # Arquitectura, workflows
├── docker-compose.yml
└── README.md
```

---

## Quickstart local

```bash
git clone --recurse-submodules https://github.com/<tu-org>/yaga.git
cd yaga
cp .env.example .env             # completa JWT_SECRET, DB_ENCRYPT_KEY, VALKEY_PASSWORD
docker compose up -d             # nginx-proxy, api, postgres, valkey
curl http://localhost/health     # verifica que el WAF enruta al api
# Frontend PWA: servir frontend/index.html con cualquier servidor estático
# (p. ej. `python3 -m http.server --directory frontend 8080`)
```

El `.env.example` documenta cada variable requerida. Las rutas `/docs`, `/redoc` y `/openapi.json` están **bloqueadas por el WAF** — para explorar la API en desarrollo, revisa directamente los routers en `app/api/v1/`. Los comandos de voz requieren Chrome/Edge (Firefox no expone `SpeechRecognition`); el service worker se registra aunque el entorno no tenga HTTPS real.

---

## Licencia

© YAGA Project — Todos los derechos reservados.
