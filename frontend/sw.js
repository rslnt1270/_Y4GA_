// © YAGA Project — Todos los derechos reservados
// sw.js — Service Worker YAGA PWA v1.1
// Estrategia: Cache-first para shell estático, Network-first para API.
// Background Sync para GPS batch (offline-first).
// Scope: /yaga/

'use strict';

const CACHE_NAME  = 'yaga-shell-v11';
const API_PREFIX  = '/api/';

// ── GPS Background Sync — config ─────────────────────────────────────────────
const GPS_BATCH_PATH  = '/api/v1/gps/batch';
const GPS_SYNC_TAG    = 'gps-sync';
const GPS_IDB_NAME    = 'yaga-gps-offline';
const GPS_IDB_VERSION = 1;
const GPS_IDB_STORE   = 'gps-queue';

// ── IndexedDB helpers (promisified, no deps) ─────────────────────────────────

function _openGpsDB() {
    return new Promise((resolve, reject) => {
        const req = indexedDB.open(GPS_IDB_NAME, GPS_IDB_VERSION);
        req.onupgradeneeded = () => {
            const db = req.result;
            if (!db.objectStoreNames.contains(GPS_IDB_STORE)) {
                db.createObjectStore(GPS_IDB_STORE, { keyPath: 'id' });
            }
        };
        req.onsuccess = () => resolve(req.result);
        req.onerror   = () => reject(req.error);
    });
}

/** Guardar un batch GPS pendiente en IndexedDB */
function _saveGpsBatch(entry) {
    return _openGpsDB().then(db => new Promise((resolve, reject) => {
        const tx    = db.transaction(GPS_IDB_STORE, 'readwrite');
        const store = tx.objectStore(GPS_IDB_STORE);
        store.put(entry);
        tx.oncomplete = () => { db.close(); resolve(); };
        tx.onerror    = () => { db.close(); reject(tx.error); };
    }));
}

/** Leer todos los batches pendientes */
function _getAllGpsBatches() {
    return _openGpsDB().then(db => new Promise((resolve, reject) => {
        const tx    = db.transaction(GPS_IDB_STORE, 'readonly');
        const store = tx.objectStore(GPS_IDB_STORE);
        const req   = store.getAll();
        req.onsuccess = () => { db.close(); resolve(req.result); };
        req.onerror   = () => { db.close(); reject(req.error); };
    }));
}

/** Eliminar un batch por id tras enviarlo exitosamente */
function _deleteGpsBatch(id) {
    return _openGpsDB().then(db => new Promise((resolve, reject) => {
        const tx    = db.transaction(GPS_IDB_STORE, 'readwrite');
        const store = tx.objectStore(GPS_IDB_STORE);
        store.delete(id);
        tx.oncomplete = () => { db.close(); resolve(); };
        tx.onerror    = () => { db.close(); reject(tx.error); };
    }));
}

// Archivos del shell que se pre-cachean en install
const SHELL_URLS = [
    '/yaga/',
    '/yaga/manifest.json',
    '/yaga/offline.html',
    '/yaga/styles/tokens.css',
    '/yaga/modules/auth.js',
    '/yaga/modules/api-client.js',
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

    // ── GPS Batch: Network con fallback a IndexedDB + Background Sync ────────
    if (url.pathname === GPS_BATCH_PATH && request.method === 'POST') {
        event.respondWith(gpsBatchWithSync(request));
        return;
    }

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

// ── GPS Batch: intentar red, si falla → IndexedDB + Background Sync ──────────

async function gpsBatchWithSync(request) {
    // Clonar antes de leer el body (los Request solo se pueden leer una vez)
    const clonedReq = request.clone();

    try {
        const response = await fetch(request);
        // Si el servidor respondio (incluso con error HTTP), devolver tal cual.
        // Solo guardamos en offline queue cuando la red falla completamente.
        return response;
    } catch (networkError) {
        // Red no disponible — guardar en IndexedDB para reenviar después
        console.warn('[SW] GPS batch sin red — guardando offline para sync');

        try {
            // Extraer token del header Authorization del request original
            const authHeader = clonedReq.headers.get('Authorization') || '';
            const bodyJson   = await clonedReq.json();

            const entry = {
                id:        _generateId(),
                jornadaId: bodyJson.jornada_id || null,
                puntos:    bodyJson.puntos || [],
                token:     authHeader,  // "Bearer xxx..." completo
                ts:        Date.now(),
            };

            await _saveGpsBatch(entry);

            // Registrar Background Sync para reenvío automático al reconectar
            if (self.registration && self.registration.sync) {
                await self.registration.sync.register(GPS_SYNC_TAG);
            }

            // Devolver respuesta sintética para que GpsDashboard no re-encole
            return new Response(
                JSON.stringify({
                    offline: true,
                    queued: true,
                    detail: 'Puntos GPS guardados offline — se enviarán al reconectar.',
                    puntos_guardados: entry.puntos.length,
                }),
                {
                    status: 202,  // Accepted — encolado para procesamiento posterior
                    headers: {
                        'Content-Type': 'application/json',
                        'X-YAGA-Offline': '1',
                        'X-YAGA-GPS-Queued': '1',
                    },
                }
            );
        } catch (idbError) {
            console.error('[SW] Error guardando GPS en IndexedDB:', idbError);
            // Fallback: devolver 503 como haría networkFirstAPI
            return new Response(
                JSON.stringify({
                    offline: true,
                    detail: 'Sin conexión — no se pudieron guardar los puntos GPS.',
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
}

/** Generar un ID único para cada entry en IndexedDB */
function _generateId() {
    // crypto.randomUUID disponible en Service Workers en navegadores modernos
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
        return crypto.randomUUID();
    }
    // Fallback: timestamp + random
    return Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
}

// ── Background Sync: reenviar batches GPS pendientes al reconectar ───────────

self.addEventListener('sync', event => {
    if (event.tag === GPS_SYNC_TAG) {
        event.waitUntil(_syncGpsBatches());
    }
});

async function _syncGpsBatches() {
    const batches = await _getAllGpsBatches();
    if (!batches.length) {
        console.info('[SW] GPS sync: no hay batches pendientes');
        return;
    }

    console.info(`[SW] GPS sync: reenviando ${batches.length} batch(es) pendientes`);

    // Procesar secuencialmente para no saturar la red al reconectar
    const errores = [];
    for (const entry of batches) {
        try {
            const response = await fetch(GPS_BATCH_PATH, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': entry.token,  // "Bearer xxx..." guardado
                },
                body: JSON.stringify({
                    jornada_id: entry.jornadaId,
                    puntos:     entry.puntos,
                }),
            });

            if (response.ok) {
                // Enviado exitosamente — eliminar de la cola offline
                await _deleteGpsBatch(entry.id);
                console.info(`[SW] GPS sync: batch ${entry.id} enviado OK (${entry.puntos.length} puntos)`);
            } else if (response.status === 401) {
                // Token expirado — no reintentar (el usuario debe hacer login)
                // Mantener en la cola pero no lanzar error para evitar retry infinito
                console.warn(`[SW] GPS sync: batch ${entry.id} — token expirado (401), se mantiene en cola`);
            } else {
                // Error del servidor (5xx, etc.) — lanzar para que Background Sync reintente
                errores.push(entry.id);
                console.warn(`[SW] GPS sync: batch ${entry.id} — error ${response.status}`);
            }
        } catch (fetchError) {
            // Sigue sin red — lanzar para que Background Sync reintente con backoff
            errores.push(entry.id);
            console.warn(`[SW] GPS sync: batch ${entry.id} — sin red`);
        }
    }

    // Si hubo errores en algún batch, lanzar para que el browser reintente
    if (errores.length > 0) {
        throw new Error(`GPS sync incompleto: ${errores.length} batch(es) fallaron, se reintentará`);
    }

    // Notificar a los clientes que el sync se completó
    const clients = await self.clients.matchAll({ type: 'window' });
    clients.forEach(client => {
        client.postMessage({
            type: 'GPS_SYNC_COMPLETE',
            batchesEnviados: batches.length,
            puntosTotal: batches.reduce((sum, b) => sum + b.puntos.length, 0),
        });
    });
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
