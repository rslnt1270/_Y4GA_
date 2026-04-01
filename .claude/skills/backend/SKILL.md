---
name: backend
description: "Contexto profundo del backend FastAPI de YAGA: endpoints, modelos, servicios, cifrado, NLP, y patrones. Se activa automáticamente cuando el agente backend trabaja en app/."
---

# Backend YAGA — Referencia Técnica

## Estructura de archivos
```
app/
├── api/v1/
│   ├── auth.py           # POST login/register/refresh/logout
│   ├── consentimientos.py # PUT gestión de finalidades
│   ├── arco.py           # GET acceso, PUT rectificacion, POST cancelacion/oposicion
│   ├── gps.py            # POST /gps/batch, POST /jornada/cerrar-v2
│   ├── nlp.py            # POST /nlp/process (clasificador determinista)
│   └── vehiculo.py       # CRUD mantenimiento vehicular
├── services/
│   ├── auth_service.py   # JWT generation, refresh rotation
│   ├── gps_service.py    # Cifrado GPS, Haversine, bulk insert
│   ├── nlp_service.py    # Clasificador 7 intents
│   └── arco_service.py   # Anonimización, export JSON
├── models/
│   ├── usuario.py        # SQLAlchemy model con campos cifrados
│   ├── viaje.py          # Incluye tipo_servicio, ganancia_real_calculada
│   ├── jornada.py
│   └── gps_log.py        # lat_cifrado/lng_cifrado BYTEA
├── core/
│   ├── crypto.py         # AES-256-GCM: encrypt_pii(), decrypt_pii(), encrypt_value()
│   ├── config.py         # Settings con Pydantic BaseSettings
│   └── deps.py           # get_db(), get_current_user()
└── main.py               # FastAPI app con CORS, middleware
```

## Patrones de código

### Endpoint tipo
```python
@router.post("/gps/batch", response_model=GpsBatchResponse)
async def gps_batch(
    data: GpsBatchRequest,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # 1. Validar ownership: jornada pertenece al usuario
    # 2. Filtrar teleportación (>300 km/h)
    # 3. Cifrar lat/lng con encrypt_value()
    # 4. Bulk insert con UNNEST
    # 5. Registrar en auditoría
```

### Cifrado PII
```python
from app.core.crypto import encrypt_pii, decrypt_pii
# Cifrar ANTES de escribir a DB
email_cifrado = encrypt_pii(email_plano)
# Descifrar DESPUÉS de leer de DB
email_plano = decrypt_pii(email_cifrado)
# IV es único por registro (12 bytes random)
# Tag de autenticación: 16 bytes
```

### NLP Engine — 7 intents
```
registrar_viaje    → monto, plataforma, metodo_pago, propina
registrar_gasto    → monto, categoria_gasto
iniciar_jornada    → (sin entidades, dispara GPS start)
cerrar_jornada     → (sin entidades, dispara GPS stop + resumen)
consultar_resumen  → (sin entidades)
consultar_total    → (sin entidades)
unknown            → fallback
```
Latencia requerida: <200ms. Sin LLM. Keywords + regex en español MX con slang.

## Endpoints GPS (Sprint 3)
- `POST /api/v1/gps/batch`: arrays de hasta 500 puntos, cifrado server-side
- `POST /api/v1/jornada/cerrar-v2`: cierra jornada + calcula distancia Haversine + ganancia_real

## Anti-patterns (NO hacer)
- ❌ Aceptar `ganancia_real_calculada` del cliente
- ❌ `pgp_sym_encrypt` en SQL
- ❌ Loops Python para bulk insert (usar UNNEST)
- ❌ Almacenar JWT en response body para localStorage
