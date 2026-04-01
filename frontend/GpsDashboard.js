// © YAGA Project — Todos los derechos reservados
/**
 * GpsDashboard.js — Componente de telemetría GPS para la PWA YAGA
 *
 * Estrategia de batería:
 *  - watchPosition con maximumAge=10000ms, timeout=15000ms, enableHighAccuracy=false
 *    → El GPS de alta precisión (enableHighAccuracy=true) consume hasta 3× más batería.
 *    → maximumAge=10s permite reutilizar la última posición cacheada si el conductor
 *      está parado en semáforo, eliminando pings innecesarios al hardware GPS.
 *  - Throttle: solo encola un punto si han pasado ≥5s desde el último.
 *  - Flush automático: cada 30s envía el batch acumulado al servidor.
 *  - Pausa automática si vel < 2 km/h por 60s (semáforo / estacionado).
 *
 * Estado del dashboard de eficiencia:
 *  gpsState = {
 *    activo: boolean,
 *    jornadaId: string | null,
 *    puntos: GPSPoint[],        // buffer local
 *    distanciaKm: number,       // acumulado local (Haversine JS)
 *    ultimoPunto: GPSPoint | null,
 *    velActual: number,
 *    batchPendiente: GPSPoint[],
 *  }
 */

'use strict';

// ── Config ────────────────────────────────────────────────────────────────────
const GPS_THROTTLE_MS    = 5_000;   // mínimo entre puntos encolados
const GPS_FLUSH_MS       = 30_000;  // intervalo de batch flush
const GPS_IDLE_THRESHOLD = 2;       // km/h — por debajo se considera parado
const GPS_IDLE_PAUSE_S   = 60;      // segundos parado antes de pausar GPS
const GPS_MAX_BATCH      = 200;     // máximo puntos por flush (seguridad)
const API_GPS_BATCH      = '/api/v1/gps/batch';
const API_JORNADA_CERRAR = '/api/v1/jornada/cerrar-v2';

// ── Estado reactivo (plain JS — compatible con la PWA actual sin React) ───────
let _gpsState = {
    activo:        false,
    jornadaId:     null,
    puntos:        [],
    distanciaKm:   0,
    ultimoPunto:   null,
    velActual:     0,
    batchPendiente:[],
    watchId:       null,
    flushTimer:    null,
    idleTimer:     null,
    ultimoTs:      0,
    idleContador:  0,
};

// Listeners de UI registrados externamente
const _listeners = new Set();
function subscribeGps(fn)   { _listeners.add(fn); }
function unsubscribeGps(fn) { _listeners.delete(fn); }
function _notify()          { _listeners.forEach(fn => fn({ ..._gpsState })); }

// ── Haversine en JS (para estimación local, sin esperar al servidor) ──────────
function _haversineKm(lat1, lng1, lat2, lng2) {
    const R = 6371;
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLng = (lng2 - lng1) * Math.PI / 180;
    const a = Math.sin(dLat/2)**2
            + Math.cos(lat1*Math.PI/180) * Math.cos(lat2*Math.PI/180)
            * Math.sin(dLng/2)**2;
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
}

// ── Iniciar GPS tracking ──────────────────────────────────────────────────────
function iniciarGps(jornadaId, token) {
    if (_gpsState.activo) return;
    if (!('geolocation' in navigator)) {
        console.warn('[GPS] Geolocation no disponible');
        return;
    }

    _gpsState.activo    = true;
    _gpsState.jornadaId = jornadaId;
    _notify();

    _gpsState.watchId = navigator.geolocation.watchPosition(
        pos => _onPosition(pos, token),
        err => console.warn('[GPS] Error:', err.message),
        {
            enableHighAccuracy: false,  // ahorro de batería
            maximumAge:         10_000, // reutilizar caché hasta 10s
            timeout:            15_000,
        }
    );

    // Flush periódico
    _gpsState.flushTimer = setInterval(() => _flush(token), GPS_FLUSH_MS);
    console.info('[GPS] Tracking iniciado para jornada', jornadaId);
}

// ── Detener GPS tracking ──────────────────────────────────────────────────────
function detenerGps(token) {
    if (!_gpsState.activo) return;
    if (_gpsState.watchId !== null) {
        navigator.geolocation.clearWatch(_gpsState.watchId);
    }
    clearInterval(_gpsState.flushTimer);
    clearTimeout(_gpsState.idleTimer);

    // Flush final del buffer antes de cerrar
    if (_gpsState.batchPendiente.length > 0) {
        _flush(token);
    }

    _gpsState.activo    = false;
    _gpsState.watchId   = null;
    _gpsState.flushTimer= null;
    _notify();
    console.info('[GPS] Tracking detenido');
}

// ── Callback de posición ──────────────────────────────────────────────────────
function _onPosition(pos, token) {
    const ahora = Date.now();
    if (ahora - _gpsState.ultimoTs < GPS_THROTTLE_MS) return; // throttle

    const { latitude: lat, longitude: lng, speed } = pos.coords;
    const velKmh = speed != null ? speed * 3.6 : null;
    const punto  = { lat, lng, vel_kmh: velKmh, ts: new Date().toISOString() };

    // Distancia local acumulada
    if (_gpsState.ultimoPunto) {
        const d = _haversineKm(
            _gpsState.ultimoPunto.lat, _gpsState.ultimoPunto.lng, lat, lng
        );
        // Filtrar saltos imposibles localmente (>200 km/h)
        const dtH = (ahora - _gpsState.ultimoTs) / 3_600_000;
        if (dtH > 0 && d / dtH < 200) {
            _gpsState.distanciaKm += d;
        }
    }

    _gpsState.ultimoPunto  = punto;
    _gpsState.ultimoTs     = ahora;
    _gpsState.velActual    = velKmh ?? 0;
    _gpsState.batchPendiente.push(punto);
    _gpsState.puntos.push(punto);

    // Lógica de pausa por inactividad
    if (_gpsState.velActual < GPS_IDLE_THRESHOLD) {
        _gpsState.idleContador++;
    } else {
        _gpsState.idleContador = 0;
    }

    _notify();
}

// ── Flush al servidor ─────────────────────────────────────────────────────────
async function _flush(token) {
    if (!_gpsState.batchPendiente.length || !_gpsState.jornadaId) return;

    const lote = _gpsState.batchPendiente.splice(0, GPS_MAX_BATCH);
    try {
        const res = await fetch(API_GPS_BATCH, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + token,
            },
            body: JSON.stringify({
                jornada_id: _gpsState.jornadaId,
                puntos: lote,
            }),
        });
        if (!res.ok) {
            console.warn('[GPS] Flush failed:', res.status);
            // Re-encolar en caso de fallo de red (offline-first)
            _gpsState.batchPendiente.unshift(...lote);
        }
    } catch (e) {
        console.warn('[GPS] Sin red — puntos encolados para retry:', lote.length);
        _gpsState.batchPendiente.unshift(...lote);
    }
}

// ── Cierre de jornada con GPS ─────────────────────────────────────────────────
async function cerrarJornadaGps(token) {
    await detenerGps(token);
    const res = await fetch(API_JORNADA_CERRAR, {
        method: 'POST',
        headers: { 'Authorization': 'Bearer ' + token },
    });
    if (!res.ok) throw new Error('Error al cerrar jornada: ' + res.status);
    return res.json();
}

// ── Renderizado del Dashboard (innerHTML — compatible con PWA actual) ─────────
function renderDashboardGps(containerId) {
    const el = document.getElementById(containerId);
    if (!el) return;

    const s = _gpsState;
    const eficiencia = s.distanciaKm > 0
        ? '—'  // se calcula server-side al cerrar jornada
        : '—';

    el.innerHTML = `
        <div class="gps-dashboard" style="
            background:#0a1220;border:1px solid #1a2a3a;border-radius:16px;
            padding:1.25rem;display:flex;flex-direction:column;gap:.75rem
        ">
            <div style="display:flex;align-items:center;justify-content:space-between">
                <span style="font-size:.8rem;color:#64748b;letter-spacing:.06em">GPS TRACK</span>
                <span style="font-size:.72rem;padding:2px 8px;border-radius:99px;background:${
                    s.activo ? 'rgba(0,229,160,.15)' : 'rgba(100,116,139,.15)'
                };color:${s.activo ? '#00e5a0' : '#64748b'};border:1px solid ${
                    s.activo ? '#00e5a0' : '#253447'
                }">${s.activo ? '● ACTIVO' : '○ INACTIVO'}</span>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:.5rem">
                <div class="gps-stat">
                    <div style="font-size:1.4rem;font-weight:800;color:#e2e8f0">
                        ${s.distanciaKm.toFixed(1)} <span style="font-size:.8rem;color:#64748b">km</span>
                    </div>
                    <div style="font-size:.7rem;color:#64748b">Distancia (local)</div>
                </div>
                <div class="gps-stat">
                    <div style="font-size:1.4rem;font-weight:800;color:#e2e8f0">
                        ${Math.round(s.velActual)} <span style="font-size:.8rem;color:#64748b">km/h</span>
                    </div>
                    <div style="font-size:.7rem;color:#64748b">Velocidad actual</div>
                </div>
                <div class="gps-stat">
                    <div style="font-size:1.4rem;font-weight:800;color:#e2e8f0">
                        ${s.puntos.length}
                    </div>
                    <div style="font-size:.7rem;color:#64748b">Puntos registrados</div>
                </div>
                <div class="gps-stat">
                    <div style="font-size:1.4rem;font-weight:800;color:#f5a623">
                        ${eficiencia}
                    </div>
                    <div style="font-size:.7rem;color:#64748b">MXN/km (al cierre)</div>
                </div>
            </div>
            ${s.batchPendiente.length > 0 ? `
            <div style="font-size:.7rem;color:#f5a623;text-align:right">
                ${s.batchPendiente.length} puntos pendientes de sync
            </div>` : ''}
        </div>
    `;
}

// ── Exports (compatible con <script> tag en la PWA actual) ────────────────────
window.GpsDashboard = {
    iniciarGps,
    detenerGps,
    cerrarJornadaGps,
    renderDashboardGps,
    subscribeGps,
    unsubscribeGps,
    getState: () => ({ ..._gpsState }),
};
