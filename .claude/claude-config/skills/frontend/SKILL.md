---
name: frontend
description: "Contexto profundo del frontend PWA de YAGA: dashboard cockpit, GPS tracking, consentimientos, offline-first, y patrones React/TS."
---

# Frontend YAGA — Referencia Técnica

## Estructura
```
frontend/
├── src/
│   ├── components/
│   │   ├── Dashboard/     # Cockpit principal
│   │   ├── Auth/          # Login, registro
│   │   ├── ARCO/          # Acceso, rectificación, cancelación
│   │   └── GPS/           # GpsDashboard.js
│   ├── hooks/
│   │   ├── useAuth.ts     # JWT en memoria, refresh automático
│   │   └── useGps.ts      # Geolocation wrapper
│   ├── store/             # Zustand stores
│   ├── services/          # API calls
│   └── App.tsx
├── public/
│   ├── manifest.json      # PWA manifest
│   └── sw.js              # Service worker offline
└── vite.config.ts
```

## Dashboard cockpit — principios
- **Periférico**: el conductor MIRA el tablero, no lo OPERA. Info visible en <1s
- **Alto contraste**: fondo oscuro, texto blanco/verde, alertas en rojo
- **Touch targets**: mínimo 48×48px, separación 8px
- **Sin scroll**: toda la info crítica en viewport sin scrollear
- **Modo noche automático**: reduce brillo blue-light después de 20:00

## GPS Dashboard (GpsDashboard.js)
```javascript
// Parámetros anti-drenaje
const GPS_CONFIG = {
    enableHighAccuracy: false,  // 3× menos batería
    maximumAge: 10000,          // Reutiliza caché 10s
    timeout: 15000
};
const THROTTLE_MS = 5000;       // 1 punto cada 5s
const FLUSH_INTERVAL = 30000;   // Batch cada 30s
const IDLE_THRESHOLD = 60000;   // Pausa si <2 km/h por 60s
```

## Auth flow
1. Login → recibe `access_token` (15min) + `refresh_token` (HttpOnly cookie, 7 días)
2. `access_token` se guarda en variable Zustand (NUNCA localStorage)
3. Interceptor Axios: si 401 → auto-refresh vía cookie → retry
4. Logout → POST /auth/logout → limpia store + cookie

## Pantallas ARCO
- **Acceso**: botón "Descargar mis datos" → JSON download
- **Rectificación**: formulario email/phone con doble confirmación
- **Cancelación**: modal con warning "Tus datos transaccionales se conservan 7 años por ley fiscal"
- **Oposición**: toggles para marketing/investigación

## Consentimientos
- Finalidad `operacion`: toggle deshabilitado (obligatoria)
- Finalidad `marketing`: toggle activo, default OFF
- Finalidad `investigacion`: toggle activo, default OFF

## Offline-first
- Service worker cachea shell + última jornada
- Comandos de voz se encolan en IndexedDB si no hay red
- Al recuperar conexión: flush queue → sync con server
- GPS points se bufferizan local y se envían en batch

## Anti-patterns
- ❌ localStorage para tokens
- ❌ `any` en TypeScript
- ❌ Inline styles (usar Tailwind classes)
- ❌ `console.log` en producción (usar logger service)
