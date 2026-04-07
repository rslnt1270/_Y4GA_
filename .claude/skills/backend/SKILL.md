---
name: backend
description: "Contexto profundo del backend FastAPI de YAGA: endpoints reales, asyncpg, HS256, NLP, cifrado, y patrones. Se activa automáticamente cuando el agente backend trabaja en app/."
---

# Backend YAGA — Referencia Técnica (actualizada abril 2026)

## Estructura REAL de archivos
```
app/
├── api/v1/
│   ├── auth.py           # GET /auth/me · POST /login /register /forgot-password /reset-password
│   ├── nlp.py            # POST /command · GET /resumen · GET /comparativa
│   ├── gps.py            # POST /gps/batch
│   ├── historico.py      # GET /historico (viajes_historicos)
│   ├── vehiculo.py       # CRUD mantenimiento vehicular
│   ├── poleana.py        # WebSocket juego de mesa
│   └── nlp_router.py     # Router alternativo NLP (legacy)
├── services/
│   ├── auth_service.py   # hash_password, verify_password, create_token (HS256), decode_token
│   ├── database.py       # get_pool() → asyncpg.Pool
│   ├── jornada_service.py # get_resumen_jornada, registrar_viaje, registrar_gasto, get_comparativa
│   ├── gps_service.py    # cifrado GPS, Haversine, bulk insert UNNEST
│   ├── historico_service.py
│   ├── vehiculo_service.py
│   └── nlp/
│       ├── classifier.py  # classify(text: str) → ClassificationResult
│       └── intent_catalog.py # DriverIntent enum
├── core/
│   ├── crypto.py         # encrypt_value(plaintext) → bytes · decrypt_value(ciphertext) → str
│   ├── config.py         # Settings Pydantic
│   └── auth.py           # ⚠️ LEGACY RS256 — no usar en endpoints nuevos
├── models/
│   └── usuario.py        # asyncpg Record wrapper
├── dependencies.py       # get_current_user() → usa auth_service.decode_token() [HS256]
└── main.py
```

## Auth — Sistema A (HS256) es el ÚNICO activo
```python
# dependencies.py — correcto desde abril 2026
from services.auth_service import decode_token

async def get_current_user(token: str = Depends(oauth2_scheme), db=Depends(get_db)):
    try:
        payload = decode_token(token)  # HS256 — compatible con frontend
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")
    ...
```

## Patrón de endpoint (asyncpg)
```python
@router.post("/command")
async def process_command(body: CommandRequest, current_user=Depends(get_current_user), pool=Depends(get_pool)):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id FROM jornadas WHERE conductor_id=$1", str(current_user.id))
    ...
```

## NLP — 7 intents reales
```
REGISTRAR_VIAJE    → monto, plataforma, metodo_pago, propina
REGISTRAR_GASTO    → monto, categoria
INICIAR_JORNADA
CERRAR_JORNADA     → get_comparativa() + cerrar_jornada()
CONSULTAR_RESUMEN  → get_resumen_jornada()
CONSULTAR_TOTAL
UNKNOWN            → fallback con sugerencia
```
Ejemplo de comando: `"viaje uber efectivo 90"` → REGISTRAR_VIAJE, monto=90, plataforma=uber, metodo=efectivo

## Forgot Password Flow
```python
# POST /auth/forgot-password
reset_token = secrets.token_urlsafe(32)
await redis.setex(f"reset:{reset_token}", 3600, conductor_id)
# Si SMTP configurado → enviar email; si no → retornar reset_url (modo dev)

# POST /auth/reset-password
conductor_id = await redis.get(f"reset:{token}")
await redis.delete(f"reset:{token}")  # un solo uso
nuevo_hash = hash_password(nueva_password)
```

## Anti-patterns (NO hacer)
- ❌ `verify_token` de `core/auth.py` en nuevos endpoints
- ❌ `pgp_sym_encrypt` en SQL — usar `encrypt_value()` de `core/crypto`
- ❌ Aceptar `ganancia_real_calculada` del cliente
- ❌ Loops Python para bulk insert (usar UNNEST)
- ❌ Almacenar JWT en response para localStorage

## Caso real: 401 en cascada (abril 2026)
```
Problema: dependencies.py usaba verify_token (RS256) pero tokens son HS256
Fix: cambiar import a decode_token de services/auth_service
Impacto: 52+ requests fallando, NLP inaccesible, sin registro de viajes
```
