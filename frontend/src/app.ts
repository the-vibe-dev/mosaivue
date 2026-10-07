import { ApiError, api, getAuth, login, logout, setup } from './api.js';
import {
  aboutPage,
  backupPage,
  camerasPage,
  dashboardPage,
  displayPage,
  layoutEditorPage,
  layoutsPage,
  logsPage,
  remotePage,
  rendererPage,
  rotationsPage,
  systemPage,
} from './pages.js';
import { resolve, route, startRouter } from './router.js';
import type { AuthState, RendererConfig } from './types.js';
import { escapeHtml, icon, toast } from './ui.js';

const app = document.querySelector<HTMLElement>('#app')!;
let auth: AuthState | null = null;
let routerStarted = false;
let eventStream: EventSource | null = null;
let eventRefreshTimer: number | null = null;

type Theme = 'light' | 'dark' | 'auto';

const navigation = [
  { href: '/', label: 'Dashboard', icon: 'grid' as const },
  { href: '/cameras', label: 'Cameras', icon: 'camera' as const },
  { href: '/layouts', label: 'Layouts', icon: 'layout' as const },
  { href: '/rotations', label: 'Rotation groups', icon: 'rotate' as const },
  { href: '/display', label: 'Display', icon: 'display' as const },
  { href: '/renderer', label: 'Renderer', icon: 'gauge' as const },
  { href: '/system', label: 'System', icon: 'system' as const },
  { href: '/logs', label: 'Logs', icon: 'logs' as const },
  { href: '/backup', label: 'Backup', icon: 'backup' as const },
  { href: '/about', label: 'About', icon: 'info' as const },
];

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  const resolved = theme === 'auto'
    ? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
    : theme;
  document.documentElement.dataset.resolvedTheme = resolved;
  localStorage.setItem('mosaivue.theme', theme);
  document.querySelector<HTMLButtonElement>('#theme-toggle')?.setAttribute(
    'aria-label',
    `Theme: ${theme}`,
  );
}

function nextTheme(): Theme {
  const current = (document.documentElement.dataset.theme || 'auto') as Theme;
  return current === 'auto' ? 'dark' : current === 'dark' ? 'light' : 'auto';
}

function authShell(title: string, subtitle: string, body: string): void {
  app.innerHTML = `
    <main class="auth-screen">
      <section class="auth-panel" aria-labelledby="auth-title">
        <div class="auth-brand"><img class="brand-logo large" src="/brand/mosaivue-logo.png" alt="Mosaivue" /></div>
        <div class="auth-copy"><h1 id="auth-title">${escapeHtml(title)}</h1><p>${escapeHtml(subtitle)}</p></div>
        ${body}
        <footer><span>${icon('lock')} Credentials remain on this appliance.</span><span>Apache-2.0</span></footer>
      </section>
      <aside class="auth-visual" aria-hidden="true">
        <div class="auth-wall">
          <div class="auth-tile tile-a"><span></span><strong>Driveway</strong></div>
          <div class="auth-tile tile-b"><span></span><strong>Front door</strong></div>
          <div class="auth-tile tile-c"><span></span><strong>Garage</strong></div>
          <div class="auth-tile tile-d"><span></span><strong>Rotating cameras</strong></div>
        </div>
        <div class="auth-visual-copy"><strong>One camera registry.<br/>Any layout.</strong><span>Drag, resize, rotate, and recover without editing coordinate files.</span></div>
      </aside>
    </main>
    <div id="toast-region" class="toast-region" aria-live="polite"></div>`;
}

async function showSetup(renderer: RendererConfig): Promise<void> {
  const backendLabels: Record<string, string> = { auto: 'Automatic', omxplayer: 'OMXPlayer (legacy Pi)', gstreamer: 'GStreamer (modern)' };
  const backendOptions = renderer.options.map((option) => `<option value="${escapeHtml(option.name)}" ${option.name === renderer.selected ? 'selected' : ''} ${!option.available ? 'disabled' : ''}>${escapeHtml(backendLabels[option.name] ?? option.name)}${option.available ? '' : ' — unavailable'}</option>`).join('');
  authShell(
    'Finish appliance setup',
    'Use the one-time token printed by the installer, then create the local administrator account.',
    `<form class="auth-form" id="setup-form">
      <label><span>Setup token</span><input class="input mono" name="token" autocomplete="one-time-code" required placeholder="XXXXX-XXXXX" /></label>
      <label><span>Administrator username</span><input class="input" name="username" autocomplete="username" required minlength="3" value="admin" /></label>
      <label><span>Password</span><input class="input" name="password" type="password" autocomplete="new-password" required minlength="12" /></label>
      <label><span>Confirm password</span><input class="input" name="confirm" type="password" autocomplete="new-password" required minlength="12" /></label>
      <label><span>Display player</span><select class="select" name="renderer_backend">${backendOptions}</select></label>
      <p class="form-help">Automatic chooses OMXPlayer on supported older Pi models and GStreamer elsewhere.</p>
      <button class="button button-primary button-full" type="submit">Create administrator</button>
      <p class="form-help">The setup token is stored at <code>/etc/mosaivue/setup-token</code> until it is used.</p>
    </form>`,
  );
  const form = document.querySelector<HTMLFormElement>('#setup-form')!;
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const submit = form.querySelector<HTMLButtonElement>('button[type="submit"]')!;
    const data = new FormData(form);
    const password = String(data.get('password') ?? '');
    if (password !== String(data.get('confirm') ?? '')) {
      toast('Passwords do not match', 'warning');
      return;
    }
    submit.disabled = true;
    try {
      auth = await setup(String(data.get('token') ?? ''), String(data.get('username') ?? ''), password, String(data.get('renderer_backend') ?? 'auto'));
      await showApplication();
      if (auth?.renderer_restart_requested) {
        toast('Display player is restarting', 'success');
        window.setTimeout(() => location.reload(), 12000);
      }
    } catch (error) {
      toast(errorText(error), 'error');
    } finally {
      submit.disabled = false;
    }
  });
}

function showLogin(): void {
  authShell(
    'Welcome back',
    'Sign in to manage cameras, layouts, renderer health, and the physical display.',
    `<form class="auth-form" id="login-form">
      <label><span>Username</span><input class="input" name="username" autocomplete="username" required autofocus /></label>
      <label><span>Password</span><input class="input" name="password" type="password" autocomplete="current-password" required /></label>
      <button class="button button-primary button-full" type="submit">Sign in</button>
      <p class="form-help">Administration is not exposed anonymously. Access is protected by a local session and CSRF token.</p>
    </form>`,
  );
  const form = document.querySelector<HTMLFormElement>('#login-form')!;
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const submit = form.querySelector<HTMLButtonElement>('button[type="submit"]')!;
    const data = new FormData(form);
    submit.disabled = true;
    try {
      auth = await login(String(data.get('username') ?? ''), String(data.get('password') ?? ''));
      await showApplication();
    } catch (error) {
      toast(errorText(error), 'error');
    } finally {
      submit.disabled = false;
    }
  });
}

function shellMarkup(): string {
  const username = auth?.user.username ?? 'admin';
  return `
    <div class="app-shell">
      <aside class="sidebar" id="sidebar">
        <a href="/" data-route class="product-lockup" aria-label="Mosaivue home">
          <img class="brand-logo" src="/brand/mosaivue-logo.png" alt="Mosaivue" />
        </a>
        <nav class="primary-nav" aria-label="Primary">
          ${navigation.map((item) => `<a href="${item.href}" data-route data-nav="${item.href}">${icon(item.icon)}<span>${item.label}</span></a>`).join('')}
        </nav>
        <div class="sidebar-remote"><a href="/remote" data-route>${icon('remote')}<span><strong>Display remote</strong><small>Phone-friendly controls</small></span>${icon('chevron')}</a></div>
        <div class="sidebar-footer"><span class="privacy-mark">${icon('lock')}</span><span><strong>Local-first</strong><small>No telemetry or cloud account</small></span></div>
      </aside>
      <div class="main-column">
        <header class="topbar">
          <button class="icon-button mobile-menu" id="sidebar-toggle" aria-label="Open navigation">${icon('menu')}</button>
          <div class="topbar-context"><span class="topbar-status"><i></i>Appliance</span><span id="route-title">Camera wall</span></div>
          <div class="topbar-actions">
            <a class="topbar-remote" href="/remote" data-route>${icon('remote')} Remote</a>
            <button class="icon-button" id="theme-toggle" title="Change color theme">${icon('sun')}<span class="sr-only">Change theme</span></button>
            <div class="user-menu">
              <button class="user-button" id="user-button" aria-expanded="false"><span>${escapeHtml(username.slice(0, 1).toUpperCase())}</span><strong>${escapeHtml(username)}</strong>${icon('chevron')}</button>
              <div class="user-popover" id="user-popover" hidden>
                <button id="change-password">${icon('lock')} Change password</button>
                <button id="logout">${icon('offline')} Sign out</button>
              </div>
            </div>
          </div>
        </header>
        <main id="page-content" class="page-content" tabindex="-1"></main>
      </div>
      <button class="sidebar-scrim" id="sidebar-scrim" aria-label="Close navigation"></button>
    </div>
    <div id="toast-region" class="toast-region" aria-live="polite"></div>`;
}

function registerRoutes(): void {
  route('/', dashboardPage);
  route('/cameras', camerasPage);
  route('/layouts', layoutsPage);
  route('/layouts/:id/edit', ({ id }) => layoutEditorPage(id ?? ''));
  route('/rotations', rotationsPage);
  route('/display', displayPage);
  route('/renderer', rendererPage);
  route('/system', systemPage);
  route('/logs', logsPage);
  route('/backup', backupPage);
  route('/about', aboutPage);
  route('/remote', remotePage);
}

function updateActiveNavigation(path = location.pathname): void {
  const matching = navigation
    .map((item) => item.href)
    .filter((href) => href === '/' ? path === '/' : path.startsWith(href))
    .sort((a, b) => b.length - a.length)[0];
  document.querySelectorAll<HTMLElement>('[data-nav]').forEach((link) => {
    link.classList.toggle('is-active', link.dataset.nav === matching);
    if (link.dataset.nav === matching) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });
  const label = navigation.find((item) => item.href === matching)?.label ?? (path === '/remote' ? 'Display remote' : 'Mosaivue');
  const title = document.querySelector<HTMLElement>('#route-title');
  if (title) title.textContent = label;
  closeSidebar();
  document.querySelector<HTMLElement>('#page-content')?.focus({ preventScroll: true });
}

function closeSidebar(): void {
  document.body.classList.remove('sidebar-open');
  document.querySelector<HTMLButtonElement>('#sidebar-toggle')?.setAttribute('aria-expanded', 'false');
}

function wireShell(): void {
  document.querySelector('#sidebar-toggle')?.addEventListener('click', () => {
    const isOpen = document.body.classList.toggle('sidebar-open');
    document.querySelector<HTMLButtonElement>('#sidebar-toggle')?.setAttribute('aria-expanded', String(isOpen));
  });
  document.querySelector('#sidebar-scrim')?.addEventListener('click', closeSidebar);
  document.querySelector('#theme-toggle')?.addEventListener('click', () => applyTheme(nextTheme()));
  const userButton = document.querySelector<HTMLButtonElement>('#user-button')!;
  const popover = document.querySelector<HTMLElement>('#user-popover')!;
  userButton.addEventListener('click', () => {
    popover.hidden = !popover.hidden;
    userButton.setAttribute('aria-expanded', String(!popover.hidden));
  });
  document.addEventListener('click', (event) => {
    const target = event.target as Node;
    if (!popover.hidden && !popover.contains(target) && !userButton.contains(target)) {
      popover.hidden = true;
      userButton.setAttribute('aria-expanded', 'false');
    }
  });
  document.querySelector('#logout')?.addEventListener('click', async () => {
    try { await logout(); } catch { /* Cookie expiry still handled on reload. */ }
    eventStream?.close();
    eventStream = null;
    auth = null;
    history.replaceState({}, '', '/');
    showLogin();
  });
  document.querySelector('#change-password')?.addEventListener('click', () => {
    const dialog = document.createElement('dialog');
    dialog.className = 'modal';
    dialog.innerHTML = `<form method="dialog" class="modal-shell" id="password-form">
      <header class="modal-header"><h2>Change password</h2><button class="icon-button" value="cancel">${icon('close')}</button></header>
      <div class="modal-body form-grid"><label><span>Current password</span><input class="input" type="password" name="current" autocomplete="current-password" required /></label><label><span>New password</span><input class="input" type="password" name="password" autocomplete="new-password" minlength="12" required /></label><label><span>Confirm new password</span><input class="input" type="password" name="confirm" autocomplete="new-password" minlength="12" required /></label></div>
      <footer class="modal-footer"><button class="button button-ghost" value="cancel">Cancel</button><button class="button button-primary" value="save">Change password</button></footer>
    </form>`;
    document.body.append(dialog);
    dialog.addEventListener('close', () => dialog.remove());
    dialog.querySelector('form')?.addEventListener('submit', async (event) => {
      const submitter = (event as SubmitEvent).submitter as HTMLButtonElement | null;
      if (submitter?.value !== 'save') return;
      event.preventDefault();
      const form = event.currentTarget as HTMLFormElement;
      const data = new FormData(form);
      if (data.get('password') !== data.get('confirm')) { toast('Passwords do not match', 'warning'); return; }
      submitter.disabled = true;
      try {
        await api('/auth/password', { method: 'POST', body: JSON.stringify({ current_password: data.get('current'), new_password: data.get('password') }) });
        toast('Password changed', 'success');
        dialog.close();
      } catch (error) { toast(errorText(error), 'error'); }
      finally { submitter.disabled = false; }
    });
    dialog.showModal();
  });
  window.addEventListener('mosaivue:route', ((event: CustomEvent<{ path: string }>) => updateActiveNavigation(event.detail.path)) as EventListener);
}

function connectEvents(): void {
  eventStream?.close();
  eventStream = new EventSource('/api/v1/events', { withCredentials: true });
  eventStream.onmessage = (event) => {
    let message: { type?: string } = {};
    try { message = JSON.parse(event.data) as { type?: string }; } catch { return; }
    if (!['renderer.status', 'layout.activated', 'camera.health', 'rotation.changed'].includes(message.type ?? '')) return;
    if (eventRefreshTimer !== null) window.clearTimeout(eventRefreshTimer);
    eventRefreshTimer = window.setTimeout(() => {
      if (['/', '/renderer', '/remote'].includes(location.pathname)) void resolve();
    }, 500);
  };
  eventStream.onerror = () => {
    // EventSource reconnects automatically. Do not make intermittent renderer restarts noisy.
  };
}

async function showApplication(): Promise<void> {
  app.innerHTML = shellMarkup();
  wireShell();
  applyTheme((localStorage.getItem('mosaivue.theme') as Theme | null) ?? 'light');
  if (!routerStarted) {
    registerRoutes();
    routerStarted = true;
    startRouter();
  } else {
    await resolve();
  }
  updateActiveNavigation();
  connectEvents();
}

async function boot(): Promise<void> {
  applyTheme((localStorage.getItem('mosaivue.theme') as Theme | null) ?? 'light');
  try {
    auth = await getAuth();
    if (auth) {
      await showApplication();
      return;
    }
    const state = await api<{ setup_required: boolean; renderer: RendererConfig }>('/auth/setup/status');
    if (state.setup_required) await showSetup(state.renderer);
    else showLogin();
  } catch (error) {
    const message = error instanceof ApiError && error.status === 503
      ? 'The Mosaivue control service is starting. Refresh after the service becomes available.'
      : errorText(error);
    authShell('Mosaivue is unavailable', message, '<button class="button button-primary button-full" id="retry-boot">Retry connection</button>');
    document.querySelector('#retry-boot')?.addEventListener('click', () => void boot());
  }
}

matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
  if (document.documentElement.dataset.theme === 'auto') applyTheme('auto');
});

void boot();
