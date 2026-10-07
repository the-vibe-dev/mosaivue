const routes = [];
export function route(pattern, handler) {
    const keys = [];
    const regex = pattern
        .split('/')
        .map((part) => {
        if (part.startsWith(':')) {
            keys.push(part.slice(1));
            return '([^/]+)';
        }
        return part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    })
        .join('/');
    routes.push({ pattern: new RegExp(`^${regex}/?$`), keys, handler });
}
export async function resolve(path = location.pathname) {
    for (const item of routes) {
        const match = path.match(item.pattern);
        if (!match)
            continue;
        const params = {};
        item.keys.forEach((key, index) => { params[key] = decodeURIComponent(match[index + 1] ?? ''); });
        await item.handler(params);
        window.dispatchEvent(new CustomEvent('mosaivue:route', { detail: { path } }));
        return;
    }
    const fallback = routes.find((item) => item.pattern.test('/'));
    if (fallback)
        await fallback.handler({});
}
export function navigate(path) {
    if (path === location.pathname)
        return;
    history.pushState({}, '', path);
    void resolve(path);
}
export function startRouter() {
    window.addEventListener('popstate', () => void resolve());
    document.addEventListener('click', (event) => {
        const anchor = event.target.closest('a[data-route]');
        if (!anchor || anchor.target || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey)
            return;
        event.preventDefault();
        navigate(anchor.pathname);
    });
    void resolve();
}
//# sourceMappingURL=router.js.map