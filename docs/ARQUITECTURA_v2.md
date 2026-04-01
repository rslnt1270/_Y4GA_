# © YAGA Project — Todos los derechos reservados
# Documento de Arquitectura v2.0 — Sprint 3
**Última actualización:** 2026-03-31

## Visión General

Ecosistema digital `y4ga.app` con dos productos principales:
- **YAGA.app** — Asistente financiero NLP para conductores de plataformas (Uber/DiDi/Cabify)
- **Poleana** — Juego de mesa mexicano multijugador online

Comparten: Auth JWT RS256 · PostgreSQL 16 · Redis 7 · nginx proxy

**Principio rector:** *Justicia de datos* — el conductor siempre ve su ganancia real neta, no el monto bruto que muestra la app.

---

## Stack Tecnológico

| Capa | Tecnología | Notas |
|------|-----------|-------|
| Backend | FastAPI 0.115 · Python 3.11 | Async, determinista |
| Base de datos | PostgreSQL 16 (pgcrypto) | PII cifrada AES-256 en app |
| Caché / sesiones | Redis 7 | Refresh tokens, rate limiting |
| Frontend | PWA vanilla JS | offline-first, sin framework |
| Infra actual | AWS EC2 t3.small + Docker Compose | Amazon Linux 2023 |
| CDN / Edge | Cloudflare Pages + Workers | Poleana frontend |
| Proxy | nginx | TLS termination + proxy_pass |
| Infra futura | AWS EKS (Kubernetes) | Preparado con labels |

---

## Esquema de Base de Datos (Sprint 3)

### Tablas existentes
- `usuarios` — PII cifrada AES-256 (`email_cifrado`, `phone_cifrado` BYTEA)
- `consentimientos` — LFPDPPP (operacion/marketing/investigacion)
- `auditoria` — Toda acción crítica con IP, user_agent, detalles JSONB
- `jornadas` — Jornadas de trabajo por conductor y fecha
- `gastos` — Gastos registrados por voz

### Tabla `viajes` — Campos nuevos (migración 001)
```sql
tipo_servicio          VARCHAR(20)   -- x, xl, comfort, flash, moto, cargo
monto_oferta_inicial   NUMERIC(10,2) -- lo que mostró la app al conductor
monto_final_app        NUMERIC(10,2) -- lo que liquidó la app
ganancia_real_calculada NUMERIC(10,2) -- calculado server-side
caseta                 NUMERIC(8,2)  -- peajes del viaje
distancia_gps_km       NUMERIC(8,3)  -- desde GPS logs (geopy Haversine)
duracion_real_min      NUMERIC(8,2)  -- tiempo real del viaje
```

### Tabla `jornada_gps_logs` — Nueva (migración 001)
```sql
id            BIGSERIAL
jornada_id    UUID → jornadas(id)
lat_cifrado   BYTEA   -- AES-256, IV único por fila
lng_cifrado   BYTEA
vel_kmh       NUMERIC(6,1)  -- en claro (no PII)
precision_m   NUMERIC(8,2)
ts            TIMESTAMPTZ
```
**Particionado:** por rango mensual. **Índices:** BRIN en `ts` (series temporales), BTree en `(jornada_id, ts DESC)`.

### Tabla `viajes_historicos`
Histórico de Uber importado via `import_historico.py`. 3,299 viajes cargados (Jun 2024 – Feb 2026).

---

## Endpoints API (Sprint 3 — Nuevos)

### GPS
```
POST /api/v1/gps/batch
  Body: { jornada_id, puntos: [{lat, lng, vel_kmh, ts}, ...] }
  Auth: Bearer JWT
  Rate limit: 60 req/min
  Max puntos: 500 por request
  Cifrado: lat/lng → AES-256 en gps_service.py
```

### Jornada
```
POST /api/v1/jornada/cerrar-v2
  Auth: Bearer JWT
  Calcula: distancia GPS real (Haversine via geopy)
  Calcula: ganancia_neta = ingresos - gastos
  Calcula: eficiencia MXN/km
  Actualiza: distancia_gps_km y ganancia_real_calculada en viajes
```

---

## Seguridad

| Control | Implementación |
|---------|---------------|
| PII cifrada | AES-256 en `core/crypto.py`, IV único por registro |
| JWT | RS256, RSA 2048-bit, refresh en Redis TTL 7d |
| GPS coords | Cifradas AES-256 antes de persistir; descifradas en memoria para cálculos |
| Rate limiting | slowapi: 60/min GPS batch, 5/min auth |
| Derechos ARCO | Retención 7 años, anonimización lat/lng a 2 decimales |
| Consentimiento GPS | Finalidad `operacion` cubre tracking (LFPDPPP) |

---

## NLP Determinista

Sin LLMs externos. Clasificador por keywords en español MX (<200ms).

**Intents activos:**
1. `inicio_viaje` → dispara `GpsDashboard.iniciarGps()`
2. `fin_viaje` → dispara `GpsDashboard.detenerGps()` + `cerrar-v2`
3. `balance_jornada` → resumen financiero en tiempo real
4. `oferta_viaje_recibida` → registra `monto_oferta_inicial`
5. `final_viaje_app` → registra `monto_final_app` + calcula `ganancia_real`

---

## Roadmap EKS

### Fase 1 — Preparación (actual, Sprint 3)
- [x] Labels `app.kubernetes.io/*` en docker-compose.yml
- [x] Secrets como archivos montados (compatibles con K8s Secret volumes)
- [x] Health checks en contenedores
- [x] Migraciones SQL versionadas (schema_migrations)

### Fase 2 — Migración
- [ ] `eksctl create cluster --name yaga --region us-east-2 --nodegroup-managed`
- [ ] Convertir docker-compose → Helm chart con `kompose convert`
- [ ] RDS PostgreSQL 16 (reemplaza contenedor postgres)
- [ ] ElastiCache Redis (reemplaza contenedor redis)
- [ ] External Secrets Operator → AWS Secrets Manager (reemplaza env vars)
- [ ] NGINX Ingress Controller (reemplaza nginx en EC2)
- [ ] Horizontal Pod Autoscaler en `yaga-api` (min 2, max 10)

### Fase 3 — Observabilidad
- [ ] Prometheus + Grafana (via Helm)
- [ ] Alertas: latencia p99 >500ms, error rate >1%
- [ ] Distributed tracing: OpenTelemetry → AWS X-Ray

---

## GPS Dashboard — Frontend

**Archivo:** `frontend/GpsDashboard.js`

**Estrategia de batería:**
- `enableHighAccuracy: false` — usa red/WiFi para posición inicial
- `maximumAge: 10000ms` — reutiliza caché si el conductor está parado
- Throttle: mínimo 5s entre puntos encolados
- Flush batch: cada 30s via `POST /api/v1/gps/batch`
- Offline-first: si no hay red, los puntos se re-encolan para el siguiente flush

**Integración con NLP:**
```javascript
// En el handler de intent inicio_viaje:
GpsDashboard.iniciarGps(jornadaId, getToken());

// En el handler de intent fin_viaje:
const resumen = await GpsDashboard.cerrarJornadaGps(getToken());
mostrarResumenJornada(resumen);
```
