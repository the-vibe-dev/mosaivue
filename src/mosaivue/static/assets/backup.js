import { api, download } from './api.js';
import { escapeHtml, icon, openDialog, pageHeader, toast } from './ui.js';
const errorMessage = (error) => error instanceof Error ? error.message : String(error);
export const MAX_JSON_IMPORT_BYTES = 32 * 1024 * 1024;
export const MAX_ARCHIVE_IMPORT_BYTES = 100 * 1024 * 1024;
/** Route JSON to the configuration API, leaving encrypted/archive bytes untouched. */
export async function buildRestoreRequest(file, merge, passphrase) {
    if (file.name.toLowerCase().endsWith('.json')) {
        if (file.size > MAX_JSON_IMPORT_BYTES)
            throw new Error('JSON configuration exceeds the 32 MiB limit');
        let document;
        try {
            document = JSON.parse(await file.text());
        }
        catch {
            throw new Error('Unable to read the JSON configuration. Choose a valid Mosaivue JSON export.');
        }
        if (!document || typeof document !== 'object' || Array.isArray(document))
            throw new Error('The JSON configuration must be an object. Choose a Mosaivue JSON export.');
        return { path: '/backup/import', options: { method: 'POST', body: JSON.stringify({ document, merge }) } };
    }
    if (!/\.(zip|cwbackup)$/i.test(file.name))
        throw new Error('Choose a .json export, .zip backup, or .cwbackup archive');
    if (file.size > MAX_ARCHIVE_IMPORT_BYTES)
        throw new Error('Backup exceeds the 100 MiB limit');
    const body = new FormData();
    body.append('file', file);
    body.append('passphrase', passphrase);
    body.append('merge', String(merge));
    return { path: '/backup/restore', options: { method: 'POST', body } };
}
export function restoreWarning(result) {
    return result.renderer_warning || (result.renderer_applied === false ? 'Configuration was restored, but the display has not applied it. Restart the renderer or apply a layout.' : null);
}
export async function renderBackup(root) {
    root.innerHTML = `${pageHeader('Backup & restore', 'Configuration exports, encrypted credentials, and validated imports')}
    <div class="backup-grid">
      <section class="panel backup-card"><span class="large-icon">${icon('download')}</span><h2>Sanitized export</h2><p>Download cameras, layouts, schedules, and settings without saved passwords.</p><button class="button button-primary" id="export-config">Download JSON</button></section>
      <section class="panel backup-card"><span class="large-icon">${icon('lock')}</span><h2>Encrypted configuration backup</h2><p>Includes camera credentials inside an AES-GCM encrypted archive protected by your passphrase.</p><button class="button button-secondary" id="encrypted-backup">Create encrypted backup</button></section>
      <section class="panel backup-card"><span class="large-icon">${icon('upload')}</span><h2>Restore or merge</h2><p>Import a JSON export, ZIP backup, or encrypted archive. Merge updates matching objects and preserves other existing data.</p><button class="button button-ghost" id="restore-backup">Choose configuration</button><input type="file" id="restore-file" hidden accept=".json,.zip,.cwbackup,application/json" /></section>
    </div><p class="form-help">Configuration backups do not include operating-system files, user accounts, or appliance installation settings. Keep the appliance's master key and installation configuration in your separate system backup.</p>`;
    root.querySelector('#export-config')?.addEventListener('click', async (event) => {
        const button = event.currentTarget;
        button.disabled = true;
        try {
            await download('/backup/export', 'mosaivue-export.json');
        }
        catch (error) {
            toast(errorMessage(error), 'error');
        }
        finally {
            button.disabled = false;
        }
    });
    root.querySelector('#encrypted-backup')?.addEventListener('click', () => {
        openDialog({ title: 'Encrypt configuration backup', body: '<label><span>Passphrase</span><input class="input" type="password" name="passphrase" required minlength="12" autocomplete="new-password" /></label><p class="form-help">Mosaivue cannot recover a lost backup passphrase.</p>', submitLabel: 'Create backup', onSubmit: async (dialog) => {
                const passphrase = dialog.querySelector('[name="passphrase"]').value;
                if (passphrase.length < 12) {
                    toast('Use at least 12 characters', 'warning');
                    return false;
                }
                await download('/backup/create', 'mosaivue-backup.cwbackup', { method: 'POST', body: JSON.stringify({ include_credentials: true, passphrase }) });
                toast('Encrypted backup created', 'success');
                return true;
            } });
    });
    const fileInput = root.querySelector('#restore-file');
    root.querySelector('#restore-backup')?.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', () => {
        const file = fileInput.files?.[0];
        if (!file)
            return;
        fileInput.value = '';
        const isJson = file.name.toLowerCase().endsWith('.json');
        openDialog({ title: isJson ? 'Import JSON configuration' : 'Restore configuration archive', body: `<p>Selected: <strong>${escapeHtml(file.name)}</strong></p>
      ${isJson ? '<p class="form-help">Sanitized exports omit saved passwords. Existing credentials are retained in merge mode; newly imported cameras may need their credentials entered.</p>' : '<label><span>Passphrase, if encrypted</span><input class="input" type="password" name="passphrase" /></label>'}
      <fieldset class="restore-mode"><legend>Import mode</legend><label class="checkbox-row"><input type="radio" name="mode" value="merge" checked /><span>Merge: update matching objects and keep other existing data</span></label><label class="checkbox-row"><input type="radio" name="mode" value="replace" /><span>Replace: remove existing cameras, groups, layouts, profiles, schedules, and stored settings before importing</span></label></fieldset>
      <p class="form-help">The server validates the complete configuration before committing it. A restored active wall may restart display streams and end camera focus.</p>`, submitLabel: 'Validate and import', onSubmit: async (dialog) => {
                const merge = dialog.querySelector('[name="mode"]:checked').value === 'merge';
                if (!merge && !confirm('Replace the existing configuration? Cameras, groups, layouts, display profiles, schedules, and stored settings will be removed. Keep a backup before continuing.'))
                    return false;
                const request = await buildRestoreRequest(file, merge, dialog.querySelector('[name="passphrase"]')?.value ?? '');
                const result = await api(request.path, request.options);
                const count = Object.values(result.imported).reduce((a, b) => a + b, 0);
                const warning = restoreWarning(result);
                toast(`Imported ${count} objects${warning ? ' · display needs attention' : ''}`, warning ? 'warning' : 'success');
                root.querySelector('#restore-result')?.remove();
                const message = document.createElement('section');
                message.id = 'restore-result';
                message.className = 'panel restore-result';
                message.setAttribute('role', 'status');
                message.innerHTML = `<h2>${warning ? 'Configuration imported; display needs attention' : 'Configuration imported'}</h2><p>${count} objects imported.</p>${warning ? `<p>${escapeHtml(warning)}</p><a class="button button-secondary" href="/renderer" data-route>Open renderer</a>` : ''}`;
                root.append(message);
                return true;
            } });
    });
}
//# sourceMappingURL=backup.js.map