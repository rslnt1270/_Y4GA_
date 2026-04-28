// © YAGA Project — Todos los derechos reservados
// src/worker.js — Cloudflare Worker: sirve los assets estáticos del frontend YAGA

export default {
  async fetch(request, env) {
    return env.ASSETS.fetch(request);
  },
};
