// © YAGA Project — Todos los derechos reservados
// modules/api-client.js — apiFetch con auto-refresh 401 (Sprint 11)

const API = '/api/v1';

export async function apiFetch(path, opts = {}) {
  const { getToken, bootSession } = await import('./auth.js');
  const token = getToken();
  const headers = Object.assign(
    { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
    opts.headers || {}
  );
  const merged = Object.assign({ credentials: 'include' }, opts, { headers });
  let res = await fetch(API + path, merged);
  if (res.status === 401 && !opts._retried && path !== '/auth/refresh') {
    const ok = await bootSession({ silent: true });
    if (ok) {
      const { getToken: gt } = await import('./auth.js');
      const retryHeaders = Object.assign({}, headers, { 'Authorization': 'Bearer ' + gt() });
      const retryOpts = Object.assign({}, merged, { headers: retryHeaders, _retried: true });
      res = await fetch(API + path, retryOpts);
    }
  }
  return res;
}
