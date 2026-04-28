// © YAGA Project — Todos los derechos reservados
// modules/auth.js — Gestión de sesión y autenticación (Sprint 11)

const API = '/api/v1';
let _authToken = null;

export const getToken = () => _authToken;
export const isAuthenticated = () => !!_authToken;

export function getYaga(key) {
  return localStorage.getItem(key) || sessionStorage.getItem(key);
}

export function saveSession(token, conductorId, nombre, email, remember) {
  _authToken = token;
  const store = remember ? localStorage : sessionStorage;
  store.setItem('yaga_conductor_id', conductorId);
  store.setItem('yaga_nombre', nombre);
  store.setItem('yaga_email', email);
  localStorage.removeItem('yaga_token');
  sessionStorage.removeItem('yaga_token');
}

export function clearSession() {
  _authToken = null;
  ['yaga_conductor_id', 'yaga_nombre', 'yaga_email'].forEach(k => {
    localStorage.removeItem(k);
    sessionStorage.removeItem(k);
  });
  localStorage.removeItem('yaga_token');
  sessionStorage.removeItem('yaga_token');
}

export async function bootSession(opts = {}) {
  try {
    const res = await fetch(API + '/auth/refresh', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
    });
    if (!res.ok) return false;
    const d = await res.json();
    _authToken = d.access_token;
    return true;
  } catch {
    return false;
  }
}

export async function logout() {
  try {
    await fetch(API + '/auth/logout', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': 'Bearer ' + _authToken },
    });
  } catch {}
  clearSession();
}
