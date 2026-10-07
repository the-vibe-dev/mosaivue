const paths = {
    grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    camera: '<path d="M14.5 6 16 3h-8l1.5 3"/><rect x="3" y="6" width="18" height="14" rx="2"/><circle cx="12" cy="13" r="4"/>',
    layout: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M14 4v16M14 11h7"/>',
    rotate: '<path d="M20 7h-6V1"/><path d="M20 7a9 9 0 1 0 2 8"/>',
    display: '<rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/>',
    gauge: '<path d="M4 19a9 9 0 1 1 16 0"/><path d="m12 13 4-4"/><path d="M5 13h2M17 13h2M12 6v2"/>',
    system: '<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M9 9h6v6H9zM9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 15h3M1 9h3M1 15h3"/>',
    logs: '<path d="M5 3h14v18H5zM8 7h8M8 11h8M8 15h5"/>',
    backup: '<path d="M12 3v12M7 10l5 5 5-5"/><path d="M4 19h16"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',
    remote: '<rect x="7" y="2" width="10" height="20" rx="3"/><circle cx="12" cy="7" r="1"/><path d="M10 17h4"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.42-1.42M17.66 6.34l1.41-1.41"/>',
    moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8Z"/>',
    menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    edit: '<path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4Z"/>',
    trash: '<path d="M3 6h18M8 6V3h8v3M6 6l1 15h10l1-15M10 10v7M14 10v7"/>',
    play: '<path d="m8 5 11 7-11 7Z"/>',
    pause: '<path d="M8 5h3v14H8zM13 5h3v14h-3z"/>',
    refresh: '<path d="M20 6v5h-5M4 18v-5h5"/><path d="M18.5 9a7 7 0 0 0-12-2L4 11M5.5 15a7 7 0 0 0 12 2L20 13"/>',
    check: '<path d="m4 12 5 5L20 6"/>',
    warning: '<path d="M12 3 2 21h20L12 3Z"/><path d="M12 9v5M12 18h.01"/>',
    offline: '<path d="M2 2l20 20M8.5 8.5A5 5 0 0 0 7 12v6h10v-2.5M17 11V8a5 5 0 0 0-7.5-4.3M5 18h14"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
    save: '<path d="M4 3h13l3 3v15H4zM8 3v6h8V3M8 21v-7h8v7"/>',
    undo: '<path d="M9 7 4 12l5 5"/><path d="M4 12h9a7 7 0 0 1 7 7"/>',
    redo: '<path d="m15 7 5 5-5 5"/><path d="M20 12h-9a7 7 0 0 0-7 7"/>',
    copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/>',
    lock: '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
    unlock: '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 7.5-2"/>',
    chevron: '<path d="m9 18 6-6-6-6"/>',
    close: '<path d="M6 6l12 12M18 6 6 18"/>',
    test: '<path d="M10 2v7l-5 9a2 2 0 0 0 2 3h10a2 2 0 0 0 2-3l-5-9V2M8 14h8"/>',
    download: '<path d="M12 3v12M7 10l5 5 5-5M4 21h16"/>',
    upload: '<path d="M12 21V9M7 14l5-5 5 5M4 3h16"/>',
    focus: '<path d="M8 3H3v5M16 3h5v5M8 21H3v-5M16 21h5v-5"/>'
};
export function icon(name, className = '') {
    return `<svg class="icon ${className}" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${paths[name]}</svg>`;
}
export function escapeHtml(value) {
    return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}
export function toast(message, kind = 'info') {
    const region = document.querySelector('#toast-region');
    if (!region)
        return;
    const item = document.createElement('div');
    item.className = `toast toast-${kind}`;
    item.innerHTML = `${icon(kind === 'success' ? 'check' : kind === 'error' ? 'offline' : kind === 'warning' ? 'warning' : 'info')}<span>${escapeHtml(message)}</span>`;
    region.append(item);
    requestAnimationFrame(() => item.classList.add('is-visible'));
    setTimeout(() => {
        item.classList.remove('is-visible');
        setTimeout(() => item.remove(), 220);
    }, 4200);
}
export function formatBytes(value) {
    if (!Number.isFinite(value) || value <= 0)
        return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
    return `${(value / 1024 ** index).toFixed(index > 1 ? 1 : 0)} ${units[index]}`;
}
export function formatDuration(seconds) {
    if (!Number.isFinite(seconds))
        return '—';
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return [days ? `${days}d` : '', hours ? `${hours}h` : '', `${minutes}m`].filter(Boolean).join(' ');
}
export function badge(label, tone = 'neutral') {
    return `<span class="status-badge status-${tone}"><span class="status-dot"></span>${escapeHtml(label)}</span>`;
}
export function openDialog(options) {
    const dialog = document.createElement('dialog');
    dialog.className = `modal ${options.wide ? 'modal-wide' : ''}`;
    dialog.innerHTML = `
    <form method="dialog" class="modal-shell">
      <header class="modal-header"><h2>${escapeHtml(options.title)}</h2><button class="icon-button" value="cancel" aria-label="Close">${icon('close')}</button></header>
      <div class="modal-body">${options.body}</div>
      <footer class="modal-footer">
        <button class="button button-ghost" value="cancel">Cancel</button>
        ${options.onSubmit ? `<button class="button ${options.destructive ? 'button-danger' : 'button-primary'}" value="submit">${escapeHtml(options.submitLabel ?? 'Save')}</button>` : ''}
      </footer>
    </form>`;
    document.body.append(dialog);
    dialog.addEventListener('close', () => dialog.remove());
    const form = dialog.querySelector('form');
    form.addEventListener('submit', async (event) => {
        const submitter = event.submitter;
        if (submitter?.value !== 'submit' || !options.onSubmit)
            return;
        event.preventDefault();
        submitter.disabled = true;
        submitter.classList.add('is-loading');
        try {
            const shouldClose = await options.onSubmit(dialog);
            if (shouldClose !== false)
                dialog.close('submit');
        }
        finally {
            submitter.disabled = false;
            submitter.classList.remove('is-loading');
        }
    });
    dialog.showModal();
    return dialog;
}
export function emptyState(iconName, title, text, action = '') {
    return `<div class="empty-state"><div class="empty-icon">${icon(iconName)}</div><h3>${escapeHtml(title)}</h3><p>${escapeHtml(text)}</p>${action}</div>`;
}
export function pageHeader(title, description, actions = '') {
    return `<div class="page-header"><div><h1>${escapeHtml(title)}</h1><p>${escapeHtml(description)}</p></div><div class="page-actions">${actions}</div></div>`;
}
export function skeleton(rows = 4) {
    return `<div class="skeleton-list">${Array.from({ length: rows }, () => '<div class="skeleton-row"></div>').join('')}</div>`;
}
//# sourceMappingURL=ui.js.map