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
├── Poleana_Project/        # Juego de mesa mexicano multijugador (WebSocket)
├── infrastructure/
│   └── database/migrations/
├── scripts/                # backup, operaciones de producción
├── docs/                   # Arquitectura, workflows, reportes ejecutivos
├── docker-compose.yml
└── README.md
```

---

## Quickstart local

```bash
git clone https://github.com/<tu-org>/yaga.git
cd yaga
cp .env.example .env              # completa JWT_SECRET y DB_ENCRYPT_KEY
docker compose up -d              # api, postgres, valkey, nginx
open http://localhost:8000/docs   # Swagger UI
open http://localhost:8080        # Frontend PWA
```

El `.env.example` documenta cada variable requerida. Para desarrollo sin HTTPS real, el service worker se registra igual y los comandos de voz funcionan en Chrome/Edge (Firefox no expone `SpeechRecognition`).

---

## Licencia

© YAGA Project — Todos los derechos reservados.
