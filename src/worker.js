// © YAGA Project — Todos los derechos reservados
// src/worker.js — Cloudflare Worker: sirve assets estáticos y proxea API al EC2

// HTTP directo a FastAPI — el TLS lo termina Cloudflare en el edge, no el EC2
const BACKEND_ORIGIN = 'http://ec2-3-19-35-76.us-east-2.compute.amazonaws.com:8000';

const SECURITY_HEADERS = {
  'Strict-Transport-Security': 'max-age=63072000; includeSubDomains; preload',
  'X-Frame-Options': 'DENY',
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'strict-origin-when-cross-origin',
  'Permissions-Policy': 'geolocation=(self), microphone=(self), camera=(), payment=(), usb=(), bluetooth=()',
  'Cross-Origin-Opener-Policy': 'same-origin',
  'X-Permitted-Cross-Domain-Policies': 'none',
  'Content-Security-Policy': [
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline' https://unpkg.com https://cdn.jsdelivr.net",
    "script-src-elem 'self' 'unsafe-inline' https://unpkg.com https://cdn.jsdelivr.net",
    "style-src 'self' 'unsafe-inline' https://unpkg.com https://fonts.googleapis.com",
    "style-src-elem 'self' 'unsafe-inline' https://unpkg.com https://fonts.googleapis.com",
    "font-src 'self' data: https://fonts.gstatic.com",
    "img-src 'self' data: blob: https://*.basemaps.cartocdn.com https://*.tile.openstreetmap.org https://unpkg.com",
    "connect-src 'self' https://fonts.googleapis.com https://fonts.gstatic.com https://ec2-3-19-35-76.us-east-2.compute.amazonaws.com wss://ec2-3-19-35-76.us-east-2.compute.amazonaws.com https://nominatim.openstreetmap.org https://router.project-osrm.org https://*.basemaps.cartocdn.com https://cdn.jsdelivr.net",
    "worker-src 'self'",
    "manifest-src 'self'",
    "frame-ancestors 'none'",
    "form-action 'self'",
    "base-uri 'self'",
    "object-src 'none'",
  ].join('; '),
};

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // ── Redirigir raíz a landing page ──────────────────────────────────────────
    if (url.pathname === '/') {
      return Response.redirect(url.origin + '/landing.html', 302);
    }

    // ── Proxy /api/* /ws/* /poleana/* /health al backend EC2 ──────────────────
    if (url.pathname.startsWith('/api/') ||
        url.pathname.startsWith('/ws/') ||
        url.pathname.startsWith('/poleana/') ||
        url.pathname === '/poleana' ||
        url.pathname === '/health') {
      const backendUrl = new URL(url.pathname + url.search, 'http://ec2-3-19-35-76.us-east-2.compute.amazonaws.com');

      // WebSocket upgrade
      if (request.headers.get('Upgrade') === 'websocket') {
        return fetch(new Request(backendUrl.toString(), request));
      }

      const proxyReq = new Request(backendUrl.toString(), {
        method: request.method,
        headers: request.headers,
        body: ['GET', 'HEAD'].includes(request.method) ? null : request.body,
        redirect: 'follow',
      });
      return fetch(proxyReq);
    }

    // ── Servir static assets con security headers ───────────────────────────────
    const response = await env.ASSETS.fetch(request);
    const mutableResponse = new Response(response.body, response);

    for (const [header, value] of Object.entries(SECURITY_HEADERS)) {
      mutableResponse.headers.set(header, value);
    }

    // Cache-Control por tipo de recurso
    const path = url.pathname;
    if (path === '/sw.js' || path === '/manifest.json') {
      mutableResponse.headers.set('Cache-Control', 'no-cache, must-revalidate');
    } else if (path === '/' || path.endsWith('.html')) {
      mutableResponse.headers.set('Cache-Control', 'no-cache, must-revalidate');
    } else if (path.endsWith('.js') || path.endsWith('.css')) {
      mutableResponse.headers.set('Cache-Control', 'public, max-age=3600');
    } else if (path.endsWith('.png') || path.endsWith('.svg') || path.endsWith('.ico')) {
      mutableResponse.headers.set('Cache-Control', 'public, max-age=86400');
    }

    return mutableResponse;
  },
};
