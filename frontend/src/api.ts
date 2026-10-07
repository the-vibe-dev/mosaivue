import type { AuthState } from './types.js';

const API_BASE = '/api/v1';
let csrfToken = sessionStorage.getItem('mosaivue.csrf') ?? '';

export class ApiError extends Error {
  constructor(public status: number, message: string, public detail?: unknown) {
    super(message);
  }
}

export function setCsrf(value: string): void {
  csrfToken = value;
  if (value) sessionStorage.setItem('mosaivue.csrf', value);
  else sessionStorage.removeItem('mosaivue.csrf');
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  const method = (options.method ?? 'GET').toUpperCase();
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && csrfToken) {
    headers.set('X-CSRF-Token', csrfToken);
  }
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    credentials: 'same-origin',
  });
  if (!response.ok) {
    let detail: unknown;
    try { detail = await response.json(); } catch { detail = await response.text(); }
    const message = typeof detail === 'object' && detail && 'detail' in detail
      ? String((detail as { detail: unknown }).detail)
      : response.statusText;
    throw new ApiError(response.status, message, detail);
  }
  if (response.status === 204) return undefined as T;
  const contentType = response.headers.get('content-type') ?? '';
  if (contentType.includes('application/json')) return response.json() as Promise<T>;
  return response.blob() as Promise<T>;
}

export async function getAuth(): Promise<AuthState | null> {
  try {
    const state = await api<AuthState>('/auth/me');
    setCsrf(state.csrf_token);
    return state;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}

export async function login(username: string, password: string): Promise<AuthState> {
  const state = await api<AuthState>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
  setCsrf(state.csrf_token);
  return state;
}

export async function setup(setupToken: string, username: string, password: string, rendererBackend: string): Promise<AuthState> {
  const state = await api<AuthState>('/auth/setup', {
    method: 'POST',
    body: JSON.stringify({ setup_token: setupToken, username, password, renderer_backend: rendererBackend }),
  });
  setCsrf(state.csrf_token);
  return state;
}

export async function logout(): Promise<void> {
  await api('/auth/logout', { method: 'POST' });
  setCsrf('');
}

export async function download(path: string, filename: string, options: RequestInit = {}): Promise<void> {
  const blob = await api<Blob>(path, options);
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
