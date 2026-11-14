const API_BASE = '/api/v1';
let csrfToken = sessionStorage.getItem('mosaivue.csrf') ?? '';
export class ApiError extends Error {
    status;
    detail;
    constructor(status, message, detail) {
        super(message);
        this.status = status;
        this.detail = detail;
        this.name = 'ApiError';
    }
}
export function apiErrorMessage(detail, fallback) {
    const value = typeof detail === 'object' && detail && 'detail' in detail
        ? detail.detail : detail;
    if (typeof value === 'object' && value && 'errors' in value && Array.isArray(value.errors)) {
        return value.errors.filter((item) => typeof item === 'string').join('; ') || fallback;
    }
    if (typeof value === 'object' && value && 'message' in value && typeof value.message === 'string')
        return value.message.slice(0, 1000);
    if (Array.isArray(value)) {
        return value.map((item) => {
            const field = item.loc?.filter((part) => part !== 'body').join(' → ');
            return `${field ? `${field}: ` : ''}${item.msg ?? 'Invalid value'}`;
        }).join('; ') || fallback;
    }
    if (typeof value === 'string' && value.trim() && !value.trim().startsWith('<'))
        return value.slice(0, 1000);
    return fallback;
}
export function layoutRevisionConflict(error) {
    if (!(error instanceof ApiError) || error.status !== 409)
        return null;
    const detail = error.detail && typeof error.detail === 'object' && 'detail' in error.detail ? error.detail.detail : error.detail;
    if (!detail || typeof detail !== 'object' || !('code' in detail) || !['layout_revision_conflict', 'layout_changed_during_apply'].includes(String(detail.code)))
        return null;
    const conflict = detail;
    if (typeof conflict.message !== 'string')
        return null;
    if (conflict.code === 'layout_changed_during_apply')
        return conflict.renderer_applied === true ? conflict : null;
    return (conflict.expected_revision == null || Number.isInteger(conflict.expected_revision)) && Number.isInteger(conflict.current_revision) ? conflict : null;
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
        const body = await response.text();
        let detail = body;
        try {
            detail = JSON.parse(body);
        }
        catch { /* Plain-text proxy errors are valid responses. */ }
        const message = apiErrorMessage(detail, response.statusText || `Request failed (${response.status})`);
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
    const result = await api(path, options);
    const blob = result instanceof Blob ? result : new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    anchor.click();
    // Give the browser time to begin consuming the download before releasing it.
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
//# sourceMappingURL=api.js.map