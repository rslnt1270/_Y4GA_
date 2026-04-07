---
name: frontend
description: "Contexto profundo del frontend YAGA: HTML monolítico, JS vanilla, auth en memoria, service worker, y flujos de UI reales."
---

# Frontend YAGA — Referencia Técnica (actualizada abril 2026)

## Realidad del stack
- `frontend/index.html` — SPA monolítico ~2,650 líneas (HTML + CSS inline + JS vanilla)
- **No hay React, TypeScript, ni Vite** en la versión actual de producción
- Service worker: `frontend/sw.js` — network-first para API, cache-first para shell
- Web Speech API: `SpeechRecognition` (Chrome/Edge) o `webkitSpeechRecognition`

## Variables globales clave
```javascript
let _authToken = null;       // JWT en memoria — null en page load
let resumenInterval = null;  // referencia al polling de /resumen (cancelable)
let CONDUCTOR_ID;            // UUID conductor (sessionStorage/localStorage)
const API = '/api/v1';       // base URL del backend
```

## Auth flow (post-fix abril 2026)
```javascript
// Token NUNCA en storage — solo en memoria
function getToken() { return _authToken; }

function saveSession(token, conductorId, nombre, email, remember) {
    _authToken = token;  // memoria
    var store = remember ? localStorage : sessionStorage;
    store.setItem('yaga_conductor_id', conductorId);
    store.setItem('yaga_nombre', nombre);
    store.setItem('yaga_email', email);
}

function clearSession() {
    _authToken = null;
    // limpiar datos no-sensibles del storage
    ['yaga_conductor_id','yaga_nombre','yaga_email'].forEach(k => {
        localStorage.removeItem(k);
        sessionStorage.removeItem(k);
    });
}
```

## Polling de /resumen — manejo correcto de 401
```javascript
let resumenInterval = null;

async function fetchResumen() {
    const token = getToken();
    if (!token) return;  // sin token, no hacer request
    const res = await fetch(`${API}/resumen`, {
        headers: { 'Authorization': 'Bearer ' + token }
    });
    if (res.status === 401) {
        clearInterval(resumenInterval);  // detener polling
        clearSession();
        $('authScreen').classList.remove('hidden');
        return;
    }
    // ... renderizar
}

// En INIT:
resumenInterval = setInterval(fetchResumen, 30000);
```

## Comando de voz → NLP
```javascript
recognition.onresult = e => {
    const transcript = e.results[0][0].transcript;
    sendCommand(transcript);  // POST /api/v1/command
};
// Firefox: SpeechRecognition no disponible → mostrar banner
```

## Forgot Password UI (implementado abril 2026)
```
formLogin → link "¿Olvidaste tu contraseña?" → mostrarForgot()
formForgot → input email → doForgot() → POST /auth/forgot-password
  → si SMTP no configurado: mostrar reset_url (modo dev/admin)
formReset → activado cuando URL tiene ?reset_token=...
  → doReset() → POST /auth/reset-password → login automático
```

## Service Worker — comportamiento real
- `sw.js:75` aparece como initiator en Network tab → es interceptor, no retry
- Si la red falla (catch) → devuelve `{offline: true}` con status 503
- Si el server responde 401 → SW lo pasa al cliente sin reintentar
- El loop de requests venía del `setInterval` sin manejo de error (corregido)

## Deploy
```bash
# Estático — SCP directo, disponible inmediatamente
scp -i yaga_backend.pem frontend/index.html ec2-user@EC2:~/yaga-project/frontend/index.html
```

## Anti-patterns (NO hacer)
- ❌ localStorage/sessionStorage para JWT
- ❌ `innerHTML` sin sanitizar datos de API (XSS)
- ❌ `setInterval` sin referencia (no se puede cancelar con clearInterval)
- ❌ Llamar `fetchResumen()` sin verificar que `getToken()` no sea null
