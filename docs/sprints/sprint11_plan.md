# © YAGA Project — Todos los derechos reservados
# Sprint 11 — UX Fase 01 + Modularización frontend + ARCO sessiones

**Duración**: 2 semanas (2026-04-28 → 2026-05-11)
**Pre-requisitos**: Sprint 10 cerrado (refresh tokens live, frontend puede "guardar sesión")
**Rama base**: `main`

---

## Objetivos de negocio

1. **Visible para el usuario**: rediseño Fase 01 (colores, tipografía, empty states) → primera impresión más profesional sin cambiar flujo.
2. **Higiene técnica**: extraer `auth.js`, `api-client.js` y `gps-dashboard.js` del monolito HTML (3,339 líneas → objetivo < 3,100).
3. **Compliance**: panel ARCO muestra sesiones activas y permite revocarlas una a una.

## Tareas

### [P0 - UX] Stitch Fase 01 — Design tokens + empty states (CSS puro)
- **Archivos**: `frontend/styles/tokens.css` (nuevo), `frontend/index.html` (reemplazar variables inline).
- Colores con semántica (`--color-success`, `--color-warning`, etc.) · tipografía con 4 pesos consistentes · componentes de estado vacío para cockpit y ARCO.
- Usar MCP Stitch para generar mockups; CSS a mano para preservar PWA offline.
- **Criterio**: comparación lado-a-lado muestra paleta limpia; sin cambios estructurales; Lighthouse contrast 100.

### [P0 - Frontend] Modularizar `auth.js` + `api-client.js` (ESM nativo)
- **Archivos**: `frontend/modules/auth.js` (~250 líneas extraídas), `frontend/modules/api-client.js` (~60 líneas), `frontend/index.html` (reemplazar bloque), `frontend/sw.js` (actualizar precache).
- `AuthManager` clase: `login, register, logout, forgotPassword, resetPassword, bootSession, isAuthenticated`.
- `apiFetch` con auto-refresh en 401 (ya existe inline en Sprint 10; promoverlo a módulo).
- Import `<script type="module" src="/yaga/modules/auth.js?v=11.0">` en index.
- **Criterio**: F5 mantiene sesión (regresión Sprint 10); logout invalida cookie en <1s.

### [P1 - Backend] Panel ARCO — sesiones activas + revocación
- **Archivos**: `app/api/v1/arco.py` (agregar `GET /arco/sesiones` y `DELETE /arco/sesiones/{familia_id}`); `app/services/refresh_service.py` (helper `list_families_for_user`); frontend ARCO panel.
- Schema respuesta: `[{familia_id, creado_en, ip, user_agent_resumido, dispositivo_actual:bool}]`.
- **Criterio**: usuario puede ver sus sesiones activas; al revocar una, el next refresh en ese dispositivo cae a login.

### [P1 - Backend] Llamar `revoke_all_families_for_user` desde `/arco/rectificacion`
- Cambio de email → invalidar todas las sesiones (hook ya preparado en Sprint 10, solo wiring).
- **Criterio**: cambiar email en panel ARCO cierra todas las sesiones; auditoría `arco_rectificacion_email`.

### [P2 - Frontend] Modularizar `GpsTracker.js` y `VoiceInput.js`
- Convertir `frontend/GpsDashboard.js` a ESM (`frontend/modules/gps-dashboard.js`).
- Extraer `webkitSpeechRecognition` + UI micrófono a `frontend/modules/voice-input.js`.
- Usar `apiFetch` (auto-refresh) en vez de `fetch` directo.
- **Criterio**: GPS y voz siguen funcionando igual; offline queue intacto.

### [P2 - Ops] Liberar EIP huérfana de `YAGA_development`
- `eipalloc-0689b2582ce7154a8` / `3.128.21.79` asociada a instancia **stopped** → cobro ~$3.6/mes innecesario.
- Acción: confirmar con owner que no se usa → `disassociate-address` → `release-address`.
- **Criterio**: `aws ec2 describe-addresses` solo muestra la de Backend.

## Fuera de alcance (Sprint 12)

- Modularización completa del resto del monolito (`Storage.js`, módulos de jornadas, vehículo, histórico).
- Reducir access token TTL de `/login` y `/register` a 15 min (necesita 100% de clientes en el frontend modular).
- Stitch Fase 02 (hero stat, voz rediseñada, animaciones).

## Riesgos

1. **Service Worker cachea versiones viejas**: al promover a módulos ESM, primer F5 post-deploy puede cargar HTML viejo. Mitigación: bumpear versión en `sw.js` + query-string `?v=11.x` en cada script.
2. **`revoke_all_families` en `/arco/rectificacion`**: cierra sesiones en otros dispositivos del mismo usuario → UX potencialmente confusa. Mitigación: mostrar aviso antes de guardar.
3. **Stitch genera CSS vanilla que choca con el existente**: dejar `tokens.css` como fuente de verdad y refactorizar incrementalmente; nunca usar `!important` para forzar.
