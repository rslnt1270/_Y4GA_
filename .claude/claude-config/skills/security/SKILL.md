---
name: security
description: "Modelo de amenazas, controles de seguridad, compliance LFPDPPP, y checklist de auditoría para YAGA."
---

# Seguridad YAGA — Modelo de Amenazas

## Controles implementados

### Cifrado
| Dato | Tipo | Método | Ubicación |
|------|------|--------|-----------|
| email | PII | AES-256-GCM, IV 12B | email_cifrado BYTEA |
| phone | PII | AES-256-GCM, IV 12B | phone_cifrado BYTEA |
| GPS lat/lng | PII sensible | AES-256-GCM, IV 12B | lat_cifrado/lng_cifrado BYTEA |
| password | Auth | bcrypt (12 rounds) | password_hash TEXT |
| Clave maestra | Secret | env var → Secrets Manager | DB_ENCRYPT_KEY |

### Autenticación
- JWT RS256 con RSA 2048-bit
- Access token: 15min TTL
- Refresh token: 7 días TTL, HttpOnly cookie, rotación por uso
- Blacklist en Redis: `refresh:{user_id}`
- Rate limiting: 5/min en /auth/login, /auth/register
- GPS batch: 60/min por conductor_id

### LFPDPPP — Finalidades
- `operacion` (obligatoria): cuentas, pagos, KYC, GPS tracking
- `marketing` (opt-out): promociones
- `investigacion` (opt-out): análisis agregado

### ARCO
- Acceso: export JSON completo
- Rectificación: re-cifra PII actualizada
- Cancelación: soft delete + anonimiza PII + retiene transaccionales 7 años + revoca tokens
- Oposición: revoca finalidad secundaria
- Toda acción → tabla `auditoria`

## Vectores de ataque por prioridad

### CRITICAL
- GPS tracking sin consentimiento explícito → agregar aviso en onboarding
- Clave RSA/DB_ENCRYPT_KEY expuesta en repo → git filter-repo + rotación

### HIGH
- Coordenadas GPS en texto plano → cifrar como PII
- Inyección SQL vía NLP input → parametrized queries siempre
- ARCO cancelación no anonimiza GPS → incluir gps_logs en proceso

### MEDIUM
- Poleana client-authoritative → migrar validación al servidor
- CORS demasiado permisivo → restringir a y4ga.app + poleana.y4ga.app
- Token en WebSocket URL → migrar a header o ticket temporal

### LOW
- Enumeración de usuarios vía timing en /auth/login → constante-time compare
- Rate limit bypass vía IP rotation → Cloudflare Bot Management

## Checklist de auditoría (ejecutar con /security-audit)
1. `grep -rn "password\|secret\|key\|token" app/ --include="*.py" | grep -v ".pyc"`
2. `grep -rn "localStorage\|sessionStorage" frontend/src/`
3. `grep -rn "pgp_sym_encrypt\|pgp_sym_decrypt" app/`
4. Verificar que `.env` está en `.gitignore`
5. `docker compose config | grep -i secret`
6. Verificar `Content-Security-Policy` header en nginx
