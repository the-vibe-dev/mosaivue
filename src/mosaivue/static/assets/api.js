const API_BASE = '/api/v1';
let csrfToken = sessionStorage.getItem('mosaivue.csrf') ?? '';
export class ApiError extends Error {
    status;
    detail;
    constructor(status, message, detail) {
        super(message);
        this.status = status;
        this.detail = detail;
    }
}
export function setCsrf(value) {
    csrfToken = value;
    if (value)
        sessionStorage.setItem('mosaivue.csrf', value);
    else
        sessionStorage.removeItem('mosaivue.csrf');
}
export async function api(path, options = {}) {
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
        let detail;
        try {
            detail = await response.json();
        }
        catch {
            detail = await response.text();
        }
        const message = typeof detail === 'object' && detail && 'detail' in detail
            ? String(detail.detail)
            : response.statusText;
        throw new ApiError(response.status, message, detail);
    }
    if (response.status === 204)
        return undefined;
    const contentType = response.headers.get('content-type') ?? '';
    if (contentType.includes('application/json'))
        return response.json();
    return response.blob();
}
export async function getAuth() {
    try {
        const state = await api('/auth/me');
        setCsrf(state.csrf_token);
        return state;
    }
    catch (error) {
        if (error instanceof ApiError && error.status === 401)
            return null;
        throw error;
    }
}
export async function login(username, password) {
    const state = await api('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
    });
    setCsrf(state.csrf_token);
    return state;
}
export async function setup(setupToken, username, password, rendererBackend) {
    const state = await api('/auth/setup', {
        method: 'POST',
        body: JSON.stringify({ setup_token: setupToken, username, password, renderer_backend: rendererBackend }),
    });
    setCsrf(state.csrf_token);
    return state;
}
export async function logout() {
    await api('/auth/logout', { method: 'POST' });
    setCsrf('');
}
export async function download(path, filename, options = {}) {
    const blob = await api(path, options);
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    anchor.click();
    URL.revokeObjectURL(url);
}
//# sourceMappingURL=api.js.map