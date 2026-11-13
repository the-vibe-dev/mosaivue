export type RouteHandler = (params: Record<string, string>) => void | Promise<void>;

type Route = { pattern: RegExp; keys: string[]; handler: RouteHandler };
const routes: Route[] = [];
let navigationGuard: (() => boolean) | null = null;
let currentPath = location.pathname;
let currentIndex = Number(history.state?.mosaivueIndex ?? 0);
let restoringHistory = false;

export function setNavigationGuard(guard: (() => boolean) | null): void {
  navigationGuard = guard;
}

export function route(pattern: string, handler: RouteHandler): void {
  const keys: string[] = [];
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

export async function resolve(path = location.pathname): Promise<void> {
  for (const item of routes) {
    const match = path.match(item.pattern);
    if (!match) continue;
    const params: Record<string, string> = {};
    item.keys.forEach((key, index) => { params[key] = decodeURIComponent(match[index + 1] ?? ''); });
    await item.handler(params);
    window.dispatchEvent(new CustomEvent('mosaivue:route', { detail: { path } }));
    return;
  }
  const fallback = routes.find((item) => item.pattern.test('/'));
  if (fallback) await fallback.handler({});
}

export function navigate(path: string): void {
  if (path === location.pathname) return;
  if (navigationGuard && !navigationGuard()) return;
  currentIndex += 1;
  currentPath = path;
  history.pushState({ mosaivueIndex: currentIndex }, '', path);
  void resolve(path);
}

export function startRouter(): void {
  history.replaceState({ ...history.state, mosaivueIndex: currentIndex }, '', location.href);
  window.addEventListener('popstate', () => {
    if (restoringHistory) { restoringHistory = false; return; }
    const nextIndex = Number(history.state?.mosaivueIndex);
    if (navigationGuard && !navigationGuard()) {
      if (Number.isFinite(nextIndex) && nextIndex !== currentIndex) {
        restoringHistory = true;
        history.go(currentIndex - nextIndex);
      } else history.pushState({ mosaivueIndex: currentIndex }, '', currentPath);
      return;
    }
    currentIndex = Number.isFinite(nextIndex) ? nextIndex : currentIndex;
    currentPath = location.pathname;
    void resolve();
  });
  document.addEventListener('click', (event) => {
    const anchor = (event.target as HTMLElement).closest<HTMLAnchorElement>('a[data-route]');
    if (!anchor || anchor.target || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    navigate(anchor.pathname);
  });
  void resolve();
}
