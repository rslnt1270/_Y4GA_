// © YAGA Project — Todos los derechos reservados
// sw.js — Service Worker YAGA PWA v1.0
// Estrategia: Cache-first para shell estático, Network-first para API.
// Scope: /yaga/

'use strict';

const CACHE_NAME  = 'yaga-shell-v1';
const API_PREFIX  = '/api/';

// Archivos del shell que se pre-cachean en install
const SHELL_URLS = [
    '/yaga/',
    '/yaga/manifest.json',
    '/yaga/offline.html',
];

// ── INSTALL: pre-cachear el shell ─────────────────────────────────────────────
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => {
            // addAll falla si algún recurso no responde — usamos add individual
            return Promise.allSettled(
                SHELL_URLS.map(url =>
                    cache.add(url).catch(() => {
                        console.warn('[SW] No se pudo pre-cachear:', url);
                    })
                )
            );
        }).then(() => self.skipWaiting())
    );
});

// ── ACTIVATE: limpiar caches viejos ──────────────────────────────────────────
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(keys =>
            Promise.all(
                keys
                    .filter(k => k !== CACHE_NAME)
                    .map(k => caches.delete(k))
            )
        ).then(() => self.clients.claim())
    );
});

// ── FETCH: interceptar requests ───────────────────────────────────────────────
self.addEventListener('fetch', event => {
    const { request } = event;
    const url = new URL(request.url);

    // Solo interceptar mismo origen
    if (url.origin !== self.location.origin) return;

    // ── API: Network-first con fallback JSON ─────────────────────────────────
    if (url.pathname.startsWith(API_PREFIX)) {
        event.respondWith(networkFirstAPI(request));
        return;
    }

    // ── Navegación (HTML): Network-first con fallback a shell cacheado ────────
    if (request.mode === 'navigate') {
        event.respondWith(networkFirstNavigate(request));
        return;
    }

    // ── Assets estáticos: Cache-first ────────────────────────────────────────
    event.respondWith(cacheFirst(request));
});

// ── Estrategias ───────────────────────────────────────────────────────────────

async function networkFirstAPI(request) {
    try {
        const response = await fetch(request.clone());
        return response;
    } catch {
        // Red caída — devolver respuesta JSON de error controlado
        const isWrite = ['POST', 'PUT', 'DELETE', 'PATCH'].includes(request.method);
        return new Response(
            JSON.stringify({
                offline: true,
                detail: isWrite
                    ? 'Sin conexión — el servidor no está disponible. Intenta de nuevo cuando tengas red.'
                    : 'Datos no disponibles en modo offline.',
            }),
            {
                status: 503,
                headers: {
                    'Content-Type': 'application/json',
                    'X-YAGA-Offline': '1',
                },
            }
        );
    }
}

async function networkFirstNavigate(request) {
    try {
        const response = await fetch(request);
        // Actualizar la caché de navegación
        const cache = await caches.open(CACHE_NAME);
        cache.put(request, response.clone()).catch(() => {});
        return response;
    } catch {
        // Sin red — servir desde caché
        const cached = await caches.match(request)
            || await caches.match('/yaga/')
            || await caches.match('/yaga/offline.html');
        if (cached) return cached;
        return offlinePage();
    }
}

async function cacheFirst(request) {
    const cached = await caches.match(request);
    if (cached) return cached;
    try {
        const response = await fetch(request);
        if (response.ok) {
            const cache = await caches.open(CACHE_NAME);
            cache.put(request, response.clone()).catch(() => {});
        }
        return response;
    } catch {
        return new Response('Recurso no disponible offline', { status: 503 });
    }
}

function offlinePage() {
    return new Response(
        `<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>YAGA — Sin conexión</title>
  <style>
    body{background:#0f1923;color:#e8f0f7;font-family:system-ui,sans-serif;
         display:flex;flex-direction:column;align-items:center;justify-content:center;
         min-height:100dvh;margin:0;padding:2rem;text-align:center;gap:1rem}
    .logo{font-size:2rem;font-weight:800;color:#00e5a0}
    .msg{color:#6b8299;font-size:.9rem;max-width:320px;line-height:1.6}
    button{background:#00e5a0;color:#0f1923;border:none;border-radius:12px;
           padding:.75rem 1.5rem;font-weight:700;font-size:1rem;cursor:pointer;margin-top:.5rem}
  </style>
</head>
<body>
  <div class="logo">Y4GA</div>
  <div style="font-size:1.1rem;font-weight:600">Sin conexión</div>
  <p class="msg">
    No hay conexión con el servidor.
    Verifica tu red e intenta de nuevo.
  </p>
  <button onclick="location.reload()">Reintentar</button>
</body>
</html>`,
        { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } }
    );
}
