import { api, download } from './api.js';
import { LayoutEditor } from './editor.js';
import { newId } from './ids.js';
import { templateGeometry } from './templates.js';
import { navigate } from './router.js';
import type { Camera, DisplayProfile, Layout, RendererConfig, RendererStatus, RotationGroup, StreamHealth, SystemStatus } from './types.js';
import { badge, emptyState, escapeHtml, formatBytes, formatDuration, icon, openDialog, pageHeader, skeleton, toast } from './ui.js';

const content = (): HTMLElement => document.querySelector<HTMLElement>('#page-content')!;
let activeEditor: LayoutEditor | null = null;

function cleanEditor(): void {
  activeEditor?.destroy();
  activeEditor = null;
  document.body.classList.remove('editor-mode');
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function streamCounts(stream: StreamHealth): string {
  const hint = stream.last_restart_reason
    ? `Last restart: ${stream.last_restart_reason}`
    : 'Counts since renderer start; planned camera changes are switches';
  const switches = stream.switch_count ?? 0;
  return `<span class="restart-count" title="${escapeHtml(hint)}">${stream.restart_count} restarts${switches ? ` · ${switches} switches` : ''}</span>`;
}

export async function dashboardPage(): Promise<void> {
  cleanEditor();
  const root = content();
  root.innerHTML = pageHeader('Dashboard', 'Live health and appliance overview', `<a class="button button-primary" href="/layouts" data-route>${icon('layout')} Open layouts</a>`) + skeleton(5);
  try {
    const [status, layouts, cameras, rendererConfig] = await Promise.all([
      api<SystemStatus>('/system/status'),
      api<Layout[]>('/layouts'),
      api<Camera[]>('/cameras'),
      api<RendererConfig>('/renderer/config'),
    ]);
    const backendLabels: Record<string, string> = { auto: 'Automatic', omxplayer: 'OMXPlayer (legacy Pi)', gstreamer: 'GStreamer (modern)' };
    const backendOptions = rendererConfig.options.map((option) => `<option value="${escapeHtml(option.name)}" ${option.name === rendererConfig.selected ? 'selected' : ''} ${!option.available ? 'disabled' : ''}>${escapeHtml(backendLabels[option.name] ?? option.name)}${option.available ? '' : ' — unavailable'}</option>`).join('');
    const active = layouts.find((item) => item.active);
    const streams = Object.values(status.renderer.streams ?? {});
    const live = streams.filter((item) => item.state === 'LIVE').length;
    const failed = streams.filter((item) => !['LIVE', 'CONNECTING'].includes(item.state)).length;
    const displayHealthy = status.renderer.state === 'RUNNING' && failed === 0;
    root.innerHTML = `
      ${pageHeader('Dashboard', 'Live health and appliance overview', `<a class="button button-primary" href="/layouts" data-route>${icon('layout')} Open layouts</a>`)}
      <section class="dashboard-hero">
        <div class="hero-copy">
          <div class="eyeline"><span class="live-pulse ${displayHealthy ? '' : 'needs-attention'}"></span>${displayHealthy ? 'Display online' : 'Renderer attention needed'}</div>
          <h2>${escapeHtml(active?.name ?? 'No layout active')}</h2>
          <p>${active ? `${active.revision?.data.slots.length ?? 0} display slots · revision ${active.current_revision}` : 'Create a layout and apply it to the HDMI display.'}</p>
          <div class="hero-actions">
            ${active ? `<a href="/layouts/${active.id}/edit" data-route class="button button-secondary">${icon('edit')} Edit active layout</a>` : `<a href="/layouts" data-route class="button button-secondary">${icon('plus')} Create layout</a>`}
            <a href="/remote" data-route class="button button-ghost">${icon('remote')} Remote control</a>
          </div>
        </div>
        <div class="wall-preview">
          ${active?.revision?.data.slots.slice(0, 8).map((slot) => {
            const camera = cameras.find((item) => item.id === (slot.selected_camera_id ?? slot.camera_id));
            const health = status.renderer.streams?.[slot.id];
            return `<div class="wall-preview-tile" style="left:${slot.x * 100}%;top:${slot.y * 100}%;width:${slot.width * 100}%;height:${slot.height * 100}%;z-index:${slot.z_index}">
              <span class="preview-noise"></span><strong>${escapeHtml(camera?.name ?? slot.label ?? slot.name)}</strong><i class="health-dot health-${(health?.state ?? 'CONNECTING').toLowerCase()}"></i>
            </div>`;
          }).join('') ?? '<div class="wall-preview-empty">No active layout</div>'}
        </div>
      </section>
      <section class="metric-strip">
        <article><span>Healthy streams</span><strong>${live}<small> / ${streams.length}</small></strong><em>${!streams.length ? 'No streams running' : failed ? `${failed} need attention` : 'All healthy'}</em></article>
        <article><span>CPU load</span><strong>${status.metrics.cpu_percent.toFixed(0)}<small>%</small></strong><em>${status.metrics.cpu_temperature_c != null ? `${status.metrics.cpu_temperature_c.toFixed(1)}°C` : 'temperature unavailable'}</em></article>
        <article><span>Memory</span><strong>${status.metrics.memory.percent.toFixed(0)}<small>%</small></strong><em>${formatBytes(status.metrics.memory.used_bytes)} used</em></article>
        <article><span>Renderer</span><strong class="metric-word">${escapeHtml(status.renderer.backend ?? 'offline')}</strong><em>${escapeHtml(status.renderer.sink ?? status.renderer.state)}</em></article>
      </section>
      <div class="dashboard-grid">
        <section class="panel stream-health-panel">
          <div class="panel-header"><div><h2>Stream health</h2><p>Independent recovery state for every active tile</p></div><a href="/renderer" data-route>Renderer details ${icon('chevron')}</a></div>
          <div class="health-list">
            ${streams.length ? streams.map((stream) => {
              const camera = cameras.find((item) => item.id === stream.camera_id);
              const tone = stream.state === 'LIVE' ? 'good' : ['CONNECTING','RECONNECTING'].includes(stream.state) ? 'warn' : 'bad';
              return `<div class="health-row"><span class="camera-avatar">${icon('camera')}</span><div><strong>${escapeHtml(camera?.name ?? stream.camera_id)}</strong><small>${escapeHtml(stream.detail ?? `Slot ${stream.slot_id.slice(0, 8)}`)}</small></div>${badge(stream.state, tone)}${streamCounts(stream)}<button class="icon-button" data-restart-slot="${stream.slot_id}" title="Restart this stream">${icon('refresh')}</button></div>`;
            }).join('') : emptyState('camera', 'No active streams', 'Apply a layout to begin rendering cameras.')}
          </div>
        </section>
        <section class="panel quick-panel">
          <div class="panel-header"><div><h2>Appliance</h2><p>Local-first system details</p></div></div>
          <dl class="detail-list">
            <div><dt>Version</dt><dd>${escapeHtml(status.version)}</dd></div>
            <div><dt>Profile</dt><dd>${escapeHtml(status.settings.profile)}</dd></div>
            <div><dt>Output</dt><dd>${status.renderer.output ? `${status.renderer.output.width} × ${status.renderer.output.height}` : 'Not detected'}</dd></div>
            <div><dt>Renderer uptime</dt><dd>${formatDuration(status.renderer.uptime_seconds ?? 0)}</dd></div>
            <div><dt>Saved cameras</dt><dd>${status.counts.cameras}</dd></div>
            <div><dt>Saved layouts</dt><dd>${status.counts.layouts}</dd></div>
          </dl>
          <label class="backend-setting"><span>Display player</span><select class="select" id="dashboard-renderer-backend" ${rendererConfig.can_change ? '' : 'disabled'}>${backendOptions}</select></label>
          <p class="form-help">Changing the player restarts the display. The saved layout returns automatically.</p>
          <div class="panel-actions"><a href="/system" data-route class="button button-ghost">System health</a><a href="/backup" data-route class="button button-ghost">Backup</a></div>
        </section>
      </div>`;
    root.querySelectorAll<HTMLButtonElement>('[data-restart-slot]').forEach((button) => button.addEventListener('click', async () => {
      try { await api(`/renderer/streams/${button.dataset.restartSlot}/restart`, { method: 'POST' }); toast('Stream restart requested', 'success'); }
      catch (error) { toast(errorMessage(error), 'error'); }
    }));
    root.querySelector<HTMLSelectElement>('#dashboard-renderer-backend')?.addEventListener('change', async (event) => {
      const select = event.currentTarget as HTMLSelectElement;
      select.disabled = true;
      try {
        const result = await api<RendererConfig>('/renderer/config', { method: 'PUT', body: JSON.stringify({ renderer_backend: select.value }) });
        toast(result.restart_requested ? 'Display player is restarting' : 'Display player setting saved', 'success');
        window.setTimeout(() => void dashboardPage(), 12000);
      } catch (error) {
        select.value = rendererConfig.selected;
        toast(errorMessage(error), 'error');
      } finally {
        select.disabled = !rendererConfig.can_change;
      }
    });
  } catch (error) {
    root.innerHTML = pageHeader('Camera wall', 'Live health and appliance overview') + emptyState('offline', 'Unable to load dashboard', errorMessage(error), '<button class="button button-primary" onclick="location.reload()">Retry</button>');
  }
}

export async function camerasPage(): Promise<void> {
  cleanEditor();
  const root = content();
  root.innerHTML = pageHeader('Cameras', 'Save each RTSP camera once and reuse it everywhere', `<button class="button button-primary" id="add-camera">${icon('plus')} Add camera</button>`) + skeleton(5);
  const refresh = async (): Promise<void> => {
    const cameras = await api<Camera[]>('/cameras');
    root.innerHTML = `${pageHeader('Cameras', 'Save each RTSP camera once and reuse it everywhere', `<button class="button button-primary" id="add-camera">${icon('plus')} Add camera</button>`)}
      <section class="panel table-panel">
        <div class="table-toolbar"><label class="search-field">${icon('search')}<input id="camera-filter" type="search" placeholder="Search cameras, locations, or tags" /></label><span>${cameras.length} saved camera${cameras.length === 1 ? '' : 's'}</span></div>
        ${cameras.length ? `<div class="data-table-wrap"><table class="data-table"><thead><tr><th>Camera</th><th>Location</th><th>Profiles</th><th>Tags</th><th>Status</th><th></th></tr></thead><tbody>${cameras.map((camera) => `
          <tr data-camera-row="${camera.id}" data-filter="${escapeHtml(`${camera.name} ${camera.location ?? ''} ${camera.tags.join(' ')}`.toLowerCase())}">
            <td><div class="table-primary"><span class="camera-avatar">${icon('camera')}</span><span><strong>${escapeHtml(camera.name)}</strong><small>${escapeHtml(camera.vendor)}${camera.model ? ` · ${escapeHtml(camera.model)}` : ''}</small></span></div></td>
            <td>${escapeHtml(camera.location ?? camera.host ?? '—')}</td>
            <td>${camera.stream_profiles.map((profile) => `<span class="profile-label">${escapeHtml(profile.name)}${profile.width ? ` ${profile.width}p` : ''}</span>`).join(' ')}</td>
            <td><div class="tag-list">${camera.tags.slice(0, 3).map((tag) => `<span>${escapeHtml(tag)}</span>`).join('') || '—'}</div></td>
            <td>${badge(camera.enabled ? 'Enabled' : 'Disabled', camera.enabled ? 'good' : 'neutral')}</td>
            <td><div class="row-actions"><button class="icon-button" data-camera-test="${camera.id}" title="Test stream">${icon('test')}</button><button class="icon-button" data-camera-preview="${camera.id}" title="Preview">${icon('play')}</button><button class="icon-button" data-camera-edit="${camera.id}" title="Edit">${icon('edit')}</button><button class="icon-button" data-camera-delete="${camera.id}" title="Delete">${icon('trash')}</button></div></td>
          </tr>`).join('')}</tbody></table></div>` : emptyState('camera', 'No cameras saved', 'Add an RTSP stream to create the reusable camera registry.', `<button class="button button-primary" id="empty-add-camera">${icon('plus')} Add your first camera</button>`)}
      </section>`;
    const openCreate = (): void => cameraDialog(null, refresh);
    root.querySelector('#add-camera')?.addEventListener('click', openCreate);
    root.querySelector('#empty-add-camera')?.addEventListener('click', openCreate);
    const filter = root.querySelector<HTMLInputElement>('#camera-filter');
    filter?.addEventListener('input', () => root.querySelectorAll<HTMLElement>('[data-camera-row]').forEach((row) => { row.hidden = !(row.dataset.filter ?? '').includes(filter.value.toLowerCase()); }));
    root.querySelectorAll<HTMLButtonElement>('[data-camera-edit]').forEach((button) => button.addEventListener('click', () => cameraDialog(cameras.find((item) => item.id === button.dataset.cameraEdit) ?? null, refresh)));
    root.querySelectorAll<HTMLButtonElement>('[data-camera-test]').forEach((button) => button.addEventListener('click', () => void testCamera(button.dataset.cameraTest!)));
    root.querySelectorAll<HTMLButtonElement>('[data-camera-preview]').forEach((button) => button.addEventListener('click', () => void previewCamera(button.dataset.cameraPreview!)));
    root.querySelectorAll<HTMLButtonElement>('[data-camera-delete]').forEach((button) => button.addEventListener('click', async () => {
      if (!confirm('Delete this camera? Existing layouts that reference it will become invalid.')) return;
      try { await api(`/cameras/${button.dataset.cameraDelete}`, { method: 'DELETE' }); toast('Camera deleted', 'success'); await refresh(); }
      catch (error) { toast(errorMessage(error), 'error'); }
    }));
  };
  try { await refresh(); } catch (error) { root.innerHTML += emptyState('offline', 'Unable to load cameras', errorMessage(error)); }
}

function cameraDialog(camera: Camera | null, refresh: () => Promise<void>): void {
  const profiles: Array<Partial<import('./types.js').StreamProfile>> = camera?.stream_profiles.length ? camera.stream_profiles : [{ name: 'Main', url: '', transport: 'tcp', latency_profile: 'low', priority: 0 }];
  const body = `<div class="form-grid two">
      <label><span>Name</span><input class="input" name="name" required value="${escapeHtml(camera?.name ?? '')}" /></label>
      <label><span>Location</span><input class="input" name="location" value="${escapeHtml(camera?.location ?? '')}" placeholder="Front porch" /></label>
      <label><span>Vendor</span><input class="input" name="vendor" value="${escapeHtml(camera?.vendor ?? 'generic')}" /></label>
      <label><span>Model</span><input class="input" name="model" value="${escapeHtml(camera?.model ?? '')}" /></label>
      <label class="span-two"><span>Description</span><textarea class="textarea" name="description">${escapeHtml(camera?.description ?? '')}</textarea></label>
      <label><span>Username</span><input class="input" name="username" autocomplete="off" value="${escapeHtml(camera?.username ?? '')}" /></label>
      <label><span>Password ${camera?.has_password ? '<small>Leave blank to keep saved password</small>' : ''}</span><input class="input" type="password" name="password" autocomplete="new-password" /></label>
      <label class="span-two"><span>Tags</span><input class="input" name="tags" value="${escapeHtml(camera?.tags.join(', ') ?? '')}" placeholder="outside, door, priority" /></label>
      <label class="checkbox-row span-two"><input type="checkbox" name="enabled" ${camera?.enabled === false ? '' : 'checked'} /><span>Camera enabled</span></label>
    </div>
    <div class="form-section-title"><div><strong>Stream profiles</strong><small>Use lower-resolution substreams for small tiles.</small></div><button type="button" class="button button-ghost button-small" id="add-profile">${icon('plus')} Add profile</button></div>
    <div id="profile-list">${profiles.map((profile, index) => profileFields(profile, index)).join('')}</div>`;
  const dialog = openDialog({
    title: camera ? `Edit ${camera.name}` : 'Add camera', body, wide: true, submitLabel: camera ? 'Save changes' : 'Add camera',
    onSubmit: async (modal) => {
      const form = modal.querySelector('form')!;
      const value = (name: string): string => (form.elements.namedItem(name) as HTMLInputElement | HTMLTextAreaElement)?.value.trim() ?? '';
      const streamProfiles = [...modal.querySelectorAll<HTMLElement>('[data-profile]')].map((row, index) => ({
        name: row.querySelector<HTMLInputElement>('[name="profile_name"]')!.value.trim() || `Profile ${index + 1}`,
        url: row.querySelector<HTMLInputElement>('[name="profile_url"]')!.value.trim(),
        transport: row.querySelector<HTMLSelectElement>('[name="profile_transport"]')!.value,
        latency_profile: row.querySelector<HTMLSelectElement>('[name="profile_latency"]')!.value,
        width: Number(row.querySelector<HTMLInputElement>('[name="profile_width"]')!.value) || null,
        height: Number(row.querySelector<HTMLInputElement>('[name="profile_height"]')!.value) || null,
        priority: index,
      })).filter((profile) => profile.url);
      if (!value('name') || !streamProfiles.length) { toast('Name and at least one RTSP URL are required', 'warning'); return false; }
      const password = value('password');
      const payload: Record<string, unknown> = {
        name: value('name'), location: value('location') || null, vendor: value('vendor') || 'generic', model: value('model') || null,
        description: value('description'), username: value('username') || null, tags: value('tags').split(',').map((item) => item.trim()).filter(Boolean),
        enabled: (form.elements.namedItem('enabled') as HTMLInputElement).checked, stream_profiles: streamProfiles,
      };
      if (password || !camera) payload.password = password;
      try {
        await api(camera ? `/cameras/${camera.id}` : '/cameras', { method: camera ? 'PUT' : 'POST', body: JSON.stringify(payload) });
        toast(camera ? 'Camera updated' : 'Camera added', 'success'); await refresh(); return true;
      } catch (error) { toast(errorMessage(error), 'error'); return false; }
    },
  });
  let profileIndex = profiles.length;
  dialog.querySelector('#add-profile')?.addEventListener('click', () => {
    dialog.querySelector('#profile-list')?.insertAdjacentHTML('beforeend', profileFields({ name: `Profile ${profileIndex + 1}`, url: '', transport: 'tcp', latency_profile: 'low' }, profileIndex++));
    attachProfileRemove(dialog);
  });
  attachProfileRemove(dialog);
}

function profileFields(profile: Partial<Camera['stream_profiles'][number]>, index: number): string {
  return `<div class="profile-form" data-profile="${index}"><div class="profile-form-head"><strong>Profile ${index + 1}</strong><button type="button" class="icon-button" data-remove-profile title="Remove profile">${icon('trash')}</button></div><div class="form-grid profile-grid">
    <label><span>Name</span><input class="input" name="profile_name" value="${escapeHtml(profile.name ?? 'Main')}" /></label>
    <label class="profile-url"><span>RTSP / RTSPS URL</span><input class="input mono" name="profile_url" value="${escapeHtml(profile.url ?? '')}" placeholder="rtsp:// or rtsps://camera/stream" /></label>
    <label><span>Transport</span><select class="select" name="profile_transport"><option value="tcp" ${profile.transport === 'tcp' ? 'selected' : ''}>TCP</option><option value="udp" ${profile.transport === 'udp' ? 'selected' : ''}>UDP</option><option value="auto" ${profile.transport === 'auto' ? 'selected' : ''}>Auto</option></select></label>
    <label><span>Latency</span><select class="select" name="profile_latency">${['ultra-low','low','normal','stable'].map((value) => `<option value="${value}" ${profile.latency_profile === value ? 'selected' : ''}>${value}</option>`).join('')}</select></label>
    <label><span>Width</span><input class="input" type="number" name="profile_width" value="${profile.width ?? ''}" placeholder="1920" /></label>
    <label><span>Height</span><input class="input" type="number" name="profile_height" value="${profile.height ?? ''}" placeholder="1080" /></label>
  </div></div>`;
}

function attachProfileRemove(dialog: HTMLDialogElement): void {
  dialog.querySelectorAll<HTMLButtonElement>('[data-remove-profile]').forEach((button) => button.onclick = () => {
    if (dialog.querySelectorAll('[data-profile]').length <= 1) { toast('At least one stream profile is required', 'warning'); return; }
    button.closest('[data-profile]')?.remove();
  });
}

async function testCamera(cameraId: string): Promise<void> {
  const dialog = openDialog({ title: 'Testing stream', body: `<div class="probe-progress"><span class="spinner"></span><p>Connecting and discovering the camera stream…</p></div>` });
  try {
    const result = await api<Record<string, unknown>>(`/cameras/${cameraId}/test`, { method: 'POST' });
    dialog.querySelector('.modal-body')!.innerHTML = result.success ? `<div class="probe-result success">${icon('check')}<h3>Stream connected</h3><dl class="detail-list"><div><dt>Response</dt><dd>${escapeHtml(result.response_time_ms)} ms</dd></div><div><dt>Codec</dt><dd>${escapeHtml(result.codec ?? 'Unknown')}</dd></div><div><dt>Resolution</dt><dd>${escapeHtml(result.width)} × ${escapeHtml(result.height)}</dd></div><div><dt>Frame rate</dt><dd>${escapeHtml(result.framerate ?? 'Unknown')}</dd></div></dl></div>` : `<div class="probe-result error">${icon('offline')}<h3>Connection failed</h3><p>${escapeHtml(result.error)}</p></div>`;
  } catch (error) { dialog.querySelector('.modal-body')!.innerHTML = `<div class="probe-result error">${icon('offline')}<h3>Test unavailable</h3><p>${escapeHtml(errorMessage(error))}</p></div>`; }
}

async function previewCamera(cameraId: string): Promise<void> {
  const dialog = openDialog({ title: 'Camera preview', body: `<div class="preview-loading"><span class="spinner"></span></div>`, wide: true });
  try {
    const blob = await api<Blob>(`/cameras/${cameraId}/preview?width=960`);
    const url = URL.createObjectURL(blob);
    dialog.querySelector('.modal-body')!.innerHTML = `<img class="camera-preview-image" src="${url}" alt="Camera preview" />`;
    dialog.addEventListener('close', () => URL.revokeObjectURL(url));
  } catch (error) { dialog.querySelector('.modal-body')!.innerHTML = emptyState('offline', 'Preview unavailable', errorMessage(error)); }
}

export async function layoutsPage(): Promise<void> {
  cleanEditor();
  const root = content();
  root.innerHTML = pageHeader('Layouts', 'Reusable display arrangements with safe revision history', `<button class="button button-primary" id="create-layout">${icon('plus')} New layout</button>`) + skeleton(4);
  const refresh = async (): Promise<void> => {
    const [layouts, cameras] = await Promise.all([api<Layout[]>('/layouts'), api<Camera[]>('/cameras')]);
    root.innerHTML = `${pageHeader('Layouts', 'Reusable display arrangements with safe revision history', `<button class="button button-primary" id="create-layout">${icon('plus')} New layout</button>`)}
      <div class="layout-list">${layouts.length ? layouts.map((layout) => {
        const slots = layout.revision?.data.slots ?? [];
        return `<article class="layout-row ${layout.active ? 'is-active' : ''}">
          <div class="mini-layout" style="background:${escapeHtml(layout.revision?.data.background ?? '#05080c')}">${slots.slice(0,12).map((slot) => `<i style="left:${slot.x*100}%;top:${slot.y*100}%;width:${slot.width*100}%;height:${slot.height*100}%"></i>`).join('')}</div>
          <div class="layout-row-main"><div class="layout-name-line"><h2>${escapeHtml(layout.name)}</h2>${layout.active ? badge('Active', 'good') : ''}</div><p>${escapeHtml(layout.description || 'No description')}</p><span>${slots.length} slots · revision ${layout.current_revision} · updated ${new Date(layout.updated_at).toLocaleString()}</span></div>
          <div class="layout-row-actions"><button class="button button-ghost" data-layout-activate="${layout.id}" ${layout.active ? 'disabled' : ''}>${icon('play')} Apply</button><a class="button button-secondary" href="/layouts/${layout.id}/edit" data-route>${icon('edit')} Edit</a><button class="icon-button" data-layout-revisions="${layout.id}" title="Revision history">${icon('logs')}</button><button class="icon-button" data-layout-delete="${layout.id}" title="Delete" ${layout.active ? 'disabled' : ''}>${icon('trash')}</button></div>
        </article>`;
      }).join('') : emptyState('layout', 'No layouts yet', 'Create a visual layout, drag cameras into place, and apply it without rebooting.', `<button class="button button-primary" id="empty-create-layout">${icon('plus')} Create layout</button>`)}</div>`;
    const create = (): void => createLayoutDialog(cameras, refresh);
    root.querySelector('#create-layout')?.addEventListener('click', create);
    root.querySelector('#empty-create-layout')?.addEventListener('click', create);
    root.querySelectorAll<HTMLButtonElement>('[data-layout-activate]').forEach((button) => button.addEventListener('click', async () => {
      button.disabled = true;
      try { await api(`/layouts/${button.dataset.layoutActivate}/activate`, { method: 'POST' }); toast('Layout applied to display', 'success'); await refresh(); }
      catch (error) { toast(errorMessage(error), 'error'); button.disabled = false; }
    }));
    root.querySelectorAll<HTMLButtonElement>('[data-layout-delete]').forEach((button) => button.addEventListener('click', async () => {
      if (!confirm('Delete this layout and its revision history?')) return;
      try { await api(`/layouts/${button.dataset.layoutDelete}`, { method: 'DELETE' }); toast('Layout deleted', 'success'); await refresh(); }
      catch (error) { toast(errorMessage(error), 'error'); }
    }));
    root.querySelectorAll<HTMLButtonElement>('[data-layout-revisions]').forEach((button) => button.addEventListener('click', () => void revisionDialog(button.dataset.layoutRevisions!, refresh)));
  };
  try { await refresh(); } catch (error) { root.innerHTML += emptyState('offline', 'Unable to load layouts', errorMessage(error)); }
}

function createLayoutDialog(cameras: Camera[], refresh: () => Promise<void>): void {
  const dialog = openDialog({
    title: 'Create layout',
    body: `<div class="form-grid"><label><span>Name</span><input class="input" name="name" required placeholder="Main" /></label><label><span>Description</span><textarea class="textarea" name="description" placeholder="Primary camera wall"></textarea></label><fieldset><legend>Starting point</legend><div class="template-choice"><label><input type="radio" name="template" value="empty" checked /><span>Empty canvas</span></label>${Array.from({ length: 9 }, (_, index) => `<label><input type="radio" name="template" value="${index + 2}" /><span>${index + 2} cameras · featured first</span></label>`).join('')}</div></fieldset></div>`,
    submitLabel: 'Create and edit',
    onSubmit: async (modal) => {
      const name = modal.querySelector<HTMLInputElement>('[name="name"]')!.value.trim();
      const description = modal.querySelector<HTMLTextAreaElement>('[name="description"]')!.value.trim();
      const template = modal.querySelector<HTMLInputElement>('[name="template"]:checked')!.value;
      if (!name) { toast('Layout name is required', 'warning'); return false; }
      const data = initialLayoutData(template, cameras);
      try { const layout = await api<Layout>('/layouts', { method: 'POST', body: JSON.stringify({ name, description, data }) }); await refresh(); navigate(`/layouts/${layout.id}/edit`); return true; }
      catch (error) { toast(errorMessage(error), 'error'); return false; }
    },
  });
  dialog.querySelector<HTMLInputElement>('[name="name"]')?.focus();
}

function initialLayoutData(template: string, cameras: Camera[]): Record<string, unknown> {
  const count = Number(template);
  const geometry = Number.isInteger(count) && count >= 2 && count <= 10 ? templateGeometry(count) : [];
  return { schema_version: 1, background: '#05080c', output_width: 1920, output_height: 1080, grid_columns: 12, grid_rows: 12, slots: geometry.map(([x,y,width,height], index) => {
    const camera = cameras[index];
    return { id: newId(), name: camera?.name ?? `Slot ${index+1}`, type: camera ? 'fixed' : 'empty', x,y,width,height,z_index:0,enabled:true,camera_id:camera?.id ?? null,rotation_group_id:null,selected_camera_id:null,stream_profile_id:null,stream_selection:'automatic',aspect_mode:'cover',crop:{top:0,right:0,bottom:0,left:0},background:'#090d12',border:'#27313c',border_width:0,label:camera?.name ?? `Slot ${index+1}`,title_position:'bottom-left',muted:true,locked:false,opacity:1,pixel_override:null };
  })};
}

async function revisionDialog(layoutId: string, refresh: () => Promise<void>): Promise<void> {
  try {
    const revisions = await api<Array<{revision:number;status:string;created_at:string}>>(`/layouts/${layoutId}/revisions`);
    const dialog = openDialog({ title: 'Revision history', body: `<div class="revision-list">${revisions.map((revision) => `<div><span><strong>Revision ${revision.revision}</strong><small>${new Date(revision.created_at).toLocaleString()} · ${escapeHtml(revision.status)}</small></span><button class="button button-ghost button-small" data-restore-revision="${revision.revision}">Restore</button></div>`).join('')}</div>` });
    dialog.querySelectorAll<HTMLButtonElement>('[data-restore-revision]').forEach((button) => button.addEventListener('click', async () => {
      try { await api(`/layouts/${layoutId}/revisions/${button.dataset.restoreRevision}/restore`, { method: 'POST' }); toast('Revision restored as a new draft', 'success'); dialog.close(); await refresh(); }
      catch (error) { toast(errorMessage(error), 'error'); }
    }));
  } catch (error) { toast(errorMessage(error), 'error'); }
}

export async function layoutEditorPage(layoutId: string): Promise<void> {
  cleanEditor();
  const root = content();
  root.innerHTML = skeleton(6);
  try {
    const [layout, cameras, groups] = await Promise.all([api<Layout>(`/layouts/${layoutId}`), api<Camera[]>('/cameras'), api<RotationGroup[]>('/rotation-groups')]);
    root.innerHTML = '';
    activeEditor = new LayoutEditor(root, layout, cameras, groups);
    activeEditor.mount();
    document.body.classList.add('editor-mode');
  } catch (error) { root.innerHTML = pageHeader('Layout editor', 'Visual camera placement') + emptyState('offline', 'Unable to open layout', errorMessage(error), '<a class="button button-primary" href="/layouts" data-route>Back to layouts</a>'); }
}

export async function rotationsPage(): Promise<void> {
  cleanEditor();
  const root = content();
  root.innerHTML = pageHeader('Rotation groups', 'Rotate selected tiles independently while fixed cameras remain untouched', `<button class="button button-primary" id="add-rotation">${icon('plus')} New group</button>`) + skeleton(4);
  const refresh = async (): Promise<void> => {
    const [groups, cameras] = await Promise.all([api<RotationGroup[]>('/rotation-groups'), api<Camera[]>('/cameras')]);
    root.innerHTML = `${pageHeader('Rotation groups', 'Rotate selected tiles independently while fixed cameras remain untouched', `<button class="button button-primary" id="add-rotation">${icon('plus')} New group</button>`)}<div class="rotation-grid">${groups.length ? groups.map((group) => `<article class="rotation-card"><div class="rotation-card-head"><span class="rotation-icon">${icon('rotate')}</span><div><h2>${escapeHtml(group.name)}</h2><p>Every ${group.interval_seconds} seconds · ${escapeHtml(group.order_mode)}</p></div>${badge(group.enabled ? 'Enabled' : 'Disabled', group.enabled ? 'good' : 'neutral')}</div><div class="rotation-camera-stack">${group.camera_entries.map((entry, index) => { const camera = cameras.find((item) => item.id === entry.camera_id); return `<span><i>${index + 1}</i>${escapeHtml(camera?.name ?? 'Missing camera')}</span>`; }).join('')}</div><dl class="compact-details"><div><dt>Preload</dt><dd>${escapeHtml(group.preconnect)}</dd></div><div><dt>Failure</dt><dd>${escapeHtml(group.failure_behavior)}</dd></div></dl><div class="card-actions"><button class="button button-ghost" data-rotation-pause="${group.id}">${icon('pause')} Pause</button><button class="button button-secondary" data-rotation-edit="${group.id}">${icon('edit')} Edit</button><button class="icon-button" data-rotation-delete="${group.id}">${icon('trash')}</button></div></article>`).join('') : emptyState('rotate', 'No rotation groups', 'Create a group, choose cameras and an interval, then assign it to any layout tile.', `<button class="button button-primary" id="empty-add-rotation">${icon('plus')} Create group</button>`)}</div>`;
    const open = (group: RotationGroup | null): void => rotationDialog(group, cameras, refresh);
    root.querySelector('#add-rotation')?.addEventListener('click', () => open(null)); root.querySelector('#empty-add-rotation')?.addEventListener('click', () => open(null));
    root.querySelectorAll<HTMLButtonElement>('[data-rotation-edit]').forEach((button) => button.addEventListener('click', () => open(groups.find((item) => item.id === button.dataset.rotationEdit) ?? null)));
    root.querySelectorAll<HTMLButtonElement>('[data-rotation-pause]').forEach((button) => button.addEventListener('click', async () => { try { await api(`/rotation-groups/${button.dataset.rotationPause}/pause`, { method: 'POST' }); toast('Rotation paused', 'success'); } catch (error) { toast(errorMessage(error), 'error'); } }));
    root.querySelectorAll<HTMLButtonElement>('[data-rotation-delete]').forEach((button) => button.addEventListener('click', async () => { if (!confirm('Delete this rotation group?')) return; try { await api(`/rotation-groups/${button.dataset.rotationDelete}`, { method: 'DELETE' }); toast('Rotation group deleted', 'success'); await refresh(); } catch (error) { toast(errorMessage(error), 'error'); } }));
  };
  try { await refresh(); } catch (error) { root.innerHTML += emptyState('offline', 'Unable to load rotation groups', errorMessage(error)); }
}

function rotationDialog(group: RotationGroup | null, cameras: Camera[], refresh: () => Promise<void>): void {
  const selected = new Set(group?.camera_entries.map((entry) => entry.camera_id) ?? []);
  openDialog({ title: group ? `Edit ${group.name}` : 'New rotation group', wide: true, submitLabel: group ? 'Save group' : 'Create group', body: `<div class="form-grid two"><label><span>Name</span><input class="input" name="name" value="${escapeHtml(group?.name ?? '')}" required /></label><label><span>Interval seconds</span><input class="input" type="number" min="2" name="interval" value="${group?.interval_seconds ?? 15}" /></label><label><span>Order</span><select class="select" name="order">${['sequential','reverse','random','weighted'].map((value) => `<option value="${value}" ${group?.order_mode === value ? 'selected' : ''}>${value}</option>`).join('')}</select></label><label><span>Preload</span><select class="select" name="preconnect">${['off','next'].map((value) => `<option value="${value}" ${group?.preconnect === value ? 'selected' : ''}>${value}</option>`).join('')}</select></label><label><span>Failure behavior</span><select class="select" name="failure">${['skip','hold','placeholder'].map((value) => `<option value="${value}" ${group?.failure_behavior === value ? 'selected' : ''}>${value}</option>`).join('')}</select></label><label class="checkbox-row"><input type="checkbox" name="enabled" ${group?.enabled === false ? '' : 'checked'} /><span>Group enabled</span></label></div><div class="form-section-title"><div><strong>Cameras</strong><small>Checked order is the sequential rotation order.</small></div></div><div class="camera-check-list">${cameras.map((camera) => `<label><input type="checkbox" name="camera" value="${camera.id}" ${selected.has(camera.id) ? 'checked' : ''} /><span class="camera-avatar">${icon('camera')}</span><span><strong>${escapeHtml(camera.name)}</strong><small>${escapeHtml(camera.location ?? camera.host ?? '')}</small></span></label>`).join('')}</div>`, onSubmit: async (dialog) => {
    const name = dialog.querySelector<HTMLInputElement>('[name="name"]')!.value.trim(); const interval = Number(dialog.querySelector<HTMLInputElement>('[name="interval"]')!.value); const cameraIds = [...dialog.querySelectorAll<HTMLInputElement>('[name="camera"]:checked')].map((input) => input.value);
    if (!name || !cameraIds.length) { toast('Name and at least one camera are required', 'warning'); return false; }
    const payload = { name, interval_seconds: interval, order_mode: dialog.querySelector<HTMLSelectElement>('[name="order"]')!.value, enabled: dialog.querySelector<HTMLInputElement>('[name="enabled"]')!.checked, preconnect: dialog.querySelector<HTMLSelectElement>('[name="preconnect"]')!.value, failure_behavior: dialog.querySelector<HTMLSelectElement>('[name="failure"]')!.value, rotate_together_group: null, start_position: 0, camera_entries: cameraIds.map((camera_id) => ({ camera_id, weight: 1, stream_profile_id: null })) };
    try { await api(group ? `/rotation-groups/${group.id}` : '/rotation-groups', { method: group ? 'PUT' : 'POST', body: JSON.stringify(payload) }); toast('Rotation group saved', 'success'); await refresh(); return true; } catch (error) { toast(errorMessage(error), 'error'); return false; }
  }});
}

export async function displayPage(): Promise<void> {
  cleanEditor(); const root = content(); root.innerHTML = pageHeader('Display', 'Detected HDMI outputs and reusable resolution profiles', `<button class="button button-primary" id="add-display-profile">${icon('plus')} New profile</button>`) + skeleton(4);
  const refresh = async (): Promise<void> => {
    const [outputs, profiles, renderer] = await Promise.all([api<Array<{name:string;status:string;modes:string[];preferred_mode:string|null}>>('/display/outputs'), api<DisplayProfile[]>('/display/profiles'), api<RendererStatus>('/renderer/status')]);
    root.innerHTML = `${pageHeader('Display', 'Detected HDMI outputs and reusable resolution profiles', `<button class="button button-primary" id="add-display-profile">${icon('plus')} New profile</button>`)}<section class="output-strip">${outputs.length ? outputs.map((output) => `<article><span class="display-icon">${icon('display')}</span><div><strong>${escapeHtml(output.name)}</strong><small>${escapeHtml(output.preferred_mode ?? 'No mode reported')} · ${escapeHtml(output.status)}</small></div>${badge(output.status, output.status === 'connected' ? 'good' : 'warn')}</article>`).join('') : `<article><span class="display-icon">${icon('display')}</span><div><strong>${renderer.backend === 'omxplayer' ? 'Legacy HDMI overlay' : renderer.state === 'RUNNING' && !String(renderer.sink ?? '').includes('kms') ? 'Display managed by renderer' : 'No DRM connector detected'}</strong><small>${renderer.backend === 'omxplayer' ? 'OMXPlayer uses VideoCore HDMI overlays; /dev/dri is not required.' : renderer.state === 'RUNNING' && !String(renderer.sink ?? '').includes('kms') ? `Active ${escapeHtml(renderer.sink ?? 'display sink')}; DRM connector detection is not used.` : 'For a KMS sink, check HDMI connection and video/render group access to /dev/dri.'}</small></div>${badge(renderer.state === 'RUNNING' ? 'Active' : 'Unavailable', renderer.state === 'RUNNING' ? 'good' : 'warn')}</article>`}</section><section class="panel table-panel"><div class="panel-header"><div><h2>Display profiles</h2><p>Associate layouts with output dimensions without changing normalized tile geometry.</p></div></div>${profiles.length ? `<table class="data-table"><thead><tr><th>Name</th><th>Output</th><th>Resolution</th><th>Refresh</th><th>Rotation</th><th></th></tr></thead><tbody>${profiles.map((profile) => `<tr><td><strong>${escapeHtml(profile.name)}</strong></td><td>${escapeHtml(profile.output_name ?? 'Any')}</td><td>${profile.width} × ${profile.height}</td><td>${profile.refresh_rate} Hz</td><td>${profile.rotation}°</td><td><button class="icon-button" data-display-delete="${profile.id}">${icon('trash')}</button></td></tr>`).join('')}</tbody></table>` : emptyState('display','No display profiles','Create a profile for the connected HDMI monitor.')}</section>`;
    root.querySelector('#add-display-profile')?.addEventListener('click', () => displayProfileDialog(outputs.map((item) => item.name), refresh));
    root.querySelectorAll<HTMLButtonElement>('[data-display-delete]').forEach((button) => button.addEventListener('click', async () => { if (!confirm('Delete this display profile?')) return; try { await api(`/display/profiles/${button.dataset.displayDelete}`, { method:'DELETE' }); await refresh(); } catch (error) { toast(errorMessage(error),'error'); } }));
  };
  try { await refresh(); } catch (error) { root.innerHTML += emptyState('offline','Unable to load display settings',errorMessage(error)); }
}

function displayProfileDialog(outputs: string[], refresh: () => Promise<void>): void {
  openDialog({ title:'New display profile', body:`<div class="form-grid two"><label><span>Name</span><input class="input" name="name" value="HDMI 1080p" /></label><label><span>Output</span><select class="select" name="output"><option value="">Any output</option>${outputs.map((item)=>`<option>${escapeHtml(item)}</option>`).join('')}</select></label><label><span>Width</span><input class="input" type="number" name="width" value="1920" /></label><label><span>Height</span><input class="input" type="number" name="height" value="1080" /></label><label><span>Refresh rate</span><input class="input" type="number" name="refresh" value="60" /></label><label><span>Rotation</span><select class="select" name="rotation"><option>0</option><option>90</option><option>180</option><option>270</option></select></label><label class="checkbox-row span-two"><input type="checkbox" name="blanking" checked /><span>Prevent display blanking</span></label></div>`, submitLabel:'Create profile', onSubmit:async(dialog)=>{ const get=(name:string)=>(dialog.querySelector<HTMLInputElement|HTMLSelectElement>(`[name="${name}"]`)!).value; try { await api('/display/profiles',{method:'POST',body:JSON.stringify({name:get('name'),output_name:get('output')||null,width:Number(get('width')),height:Number(get('height')),refresh_rate:Number(get('refresh')),rotation:Number(get('rotation')),prevent_blanking:dialog.querySelector<HTMLInputElement>('[name="blanking"]')!.checked})}); toast('Display profile created','success'); await refresh(); return true; } catch(error){toast(errorMessage(error),'error');return false;} } });
}

export async function rendererPage(): Promise<void> {
  cleanEditor(); const root=content(); root.innerHTML=pageHeader('Renderer & performance','Pipeline capabilities, stream recovery, and safe synthetic benchmarking')+skeleton(5);
  try {
    const [status, backends, rendererConfig] = await Promise.all([api<RendererStatus>('/renderer/status'), api<Array<Record<string,unknown>>>('/renderer/backends'), api<RendererConfig>('/renderer/config')]);
    root.innerHTML=`${pageHeader('Renderer & performance','Pipeline capabilities, stream recovery, and safe synthetic benchmarking',`<button class="button button-primary" id="run-benchmark">${icon('gauge')} Run benchmark</button>`)}<div class="renderer-overview"><section class="panel"><div class="panel-header"><div><h2>Active renderer</h2><p>Managed output with independent camera streams.</p></div>${badge(status.state,status.state==='RUNNING'?'good':'bad')}</div><dl class="detail-list"><div><dt>Backend</dt><dd>${escapeHtml(status.backend??'Unavailable')}</dd></div><div><dt>Sink</dt><dd>${escapeHtml(status.sink??'—')}</dd></div><div><dt>Output</dt><dd>${status.output?`${status.output.width} × ${status.output.height}`:'—'}</dd></div><div><dt>Uptime</dt><dd>${formatDuration(status.uptime_seconds??0)}</dd></div><div><dt>Active streams</dt><dd>${Object.keys(status.streams??{}).length}</dd></div></dl></section><section class="panel"><div class="panel-header"><div><h2>Backend availability</h2><p>Players available on this device.</p></div></div><div class="backend-list">${backends.map((backend)=>`<div><span class="backend-icon">${icon('gauge')}</span><span><strong>${escapeHtml(backend.name)}</strong><small>${escapeHtml(backend.reason??(backend.available?'Ready':'Unavailable'))}</small></span>${badge(backend.available?'Available':'Unavailable',backend.available?'good':'neutral')}</div>`).join('')}</div></section></div><section class="panel"><div class="panel-header"><div><h2>Per-stream state</h2><p>Restarts are recovery or manual actions; switches are planned camera changes. Counts reset when the renderer starts.</p></div></div><div class="health-list">${Object.values(status.streams??{}).map((stream)=>`<div class="health-row"><span class="camera-avatar">${icon('camera')}</span><div><strong>${escapeHtml(stream.slot_id)}</strong><small>${escapeHtml(stream.detail??`${stream.decoded_frames} frames decoded`)}</small></div>${badge(stream.state,stream.state==='LIVE'?'good':['CONNECTING','RECONNECTING'].includes(stream.state)?'warn':'bad')}${streamCounts(stream)}<button class="icon-button" data-restart-slot="${stream.slot_id}">${icon('refresh')}</button></div>`).join('')||emptyState('camera','No streams','Apply a layout to create renderer branches.')}</div></section><section class="panel benchmark-panel" id="benchmark-result"><div><h2>Synthetic compositor benchmark</h2><p>Uses local generated video sources. It never contacts or changes cameras.</p></div><div class="benchmark-placeholder">No benchmark run in this session.</div></section>`;
    const backendLabels: Record<string, string> = { auto: 'Automatic', omxplayer: 'OMXPlayer (legacy Pi)', gstreamer: 'GStreamer (modern)' };
    root.querySelector('.renderer-overview')?.insertAdjacentHTML('beforeend', `<section class="panel"><div class="panel-header"><div><h2>Display player</h2><p>Choose the player used for HDMI output.</p></div></div><label class="backend-setting"><span>Selected player</span><select class="select" id="renderer-backend-choice" ${rendererConfig.can_change ? '' : 'disabled'}>${rendererConfig.options.map((option) => `<option value="${escapeHtml(option.name)}" ${option.name === rendererConfig.selected ? 'selected' : ''} ${!option.available ? 'disabled' : ''}>${escapeHtml(backendLabels[option.name] ?? option.name)}${option.available ? '' : ' — unavailable'}</option>`).join('')}</select></label><p class="form-help">Changing the player restarts the display and restores the active layout.</p></section>`);
    root.querySelector<HTMLSelectElement>('#renderer-backend-choice')?.addEventListener('change', async (event) => {
      const select = event.currentTarget as HTMLSelectElement;
      select.disabled = true;
      try {
        const result = await api<RendererConfig>('/renderer/config', { method: 'PUT', body: JSON.stringify({ renderer_backend: select.value }) });
        toast(result.restart_requested ? 'Display player is restarting' : 'Display player setting saved', 'success');
        window.setTimeout(() => void rendererPage(), 12000);
      } catch (error) {
        select.value = rendererConfig.selected;
        toast(errorMessage(error), 'error');
      } finally {
        select.disabled = !rendererConfig.can_change;
      }
    });
    root.querySelector('#run-benchmark')?.addEventListener('click',async()=>{const button=root.querySelector<HTMLButtonElement>('#run-benchmark')!;button.disabled=true;button.innerHTML='<span class="spinner small"></span> Running';try{const result=await api<Record<string,unknown>>('/system/benchmark?streams=6&duration=5',{method:'POST'});root.querySelector('#benchmark-result')!.innerHTML=`<div><h2>Benchmark result</h2><p>${escapeHtml(result.note)}</p></div><dl class="benchmark-metrics"><div><dt>Streams</dt><dd>${escapeHtml(result.streams)}</dd></div><div><dt>Average FPS</dt><dd>${escapeHtml(result.average_output_fps_per_stream)}</dd></div><div><dt>CPU</dt><dd>${escapeHtml(result.process_cpu_percent_average)}%</dd></div><div><dt>Memory delta</dt><dd>${formatBytes(Number(result.memory_delta_bytes))}</dd></div></dl>`;toast('Benchmark completed','success');}catch(error){toast(errorMessage(error),'error');}finally{button.disabled=false;button.innerHTML=`${icon('gauge')} Run benchmark`;}});
    root.querySelectorAll<HTMLButtonElement>('[data-restart-slot]').forEach((button)=>button.addEventListener('click',async()=>{try{await api(`/renderer/streams/${button.dataset.restartSlot}/restart`,{method:'POST'});toast('Stream restarted','success');}catch(error){toast(errorMessage(error),'error');}}));
  } catch(error){root.innerHTML+=emptyState('offline','Renderer data unavailable',errorMessage(error));}
}

export async function systemPage(): Promise<void> {
  cleanEditor(); const root=content(); root.innerHTML=pageHeader('System','Hardware, operating system, diagnostics, and security posture',`<button class="button button-secondary" id="download-support">${icon('download')} Support bundle</button>`)+skeleton(6);
  try { const [doctor,audit,status]=await Promise.all([api<Record<string,any>>('/system/doctor'),api<Record<string,any>>('/system/security-audit'),api<SystemStatus>('/system/status')]); root.innerHTML=`${pageHeader('System','Hardware, operating system, diagnostics, and security posture',`<button class="button button-secondary" id="download-support">${icon('download')} Support bundle</button>`)}<div class="system-grid"><section class="panel"><div class="panel-header"><div><h2>Hardware</h2><p>Detected at runtime</p></div></div><dl class="detail-list"><div><dt>Model</dt><dd>${escapeHtml(doctor.pi_model??doctor.platform)}</dd></div><div><dt>Architecture</dt><dd>${escapeHtml(doctor.architecture)}</dd></div><div><dt>Kernel</dt><dd>${escapeHtml(doctor.kernel)}</dd></div><div><dt>Memory</dt><dd>${formatBytes(doctor.memory?.total_bytes??0)}</dd></div><div><dt>DRM devices</dt><dd>${doctor.drm_devices?.length??0}${status.renderer.backend==='omxplayer'?' · not required by OMXPlayer':''}</dd></div><div><dt>Recommended profile</dt><dd>${escapeHtml(doctor.recommended_profile)}</dd></div></dl></section><section class="panel"><div class="panel-header"><div><h2>Current load</h2><p>Live appliance metrics</p></div></div><div class="meter-stack"><label><span>CPU</span><strong>${status.metrics.cpu_percent.toFixed(0)}%</strong><i><b style="width:${status.metrics.cpu_percent}%"></b></i></label><label><span>Memory</span><strong>${status.metrics.memory.percent.toFixed(0)}%</strong><i><b style="width:${status.metrics.memory.percent}%"></b></i></label></div><dl class="detail-list"><div><dt>Temperature</dt><dd>${status.metrics.cpu_temperature_c!=null?`${status.metrics.cpu_temperature_c.toFixed(1)}°C`:'Unavailable'}</dd></div><div><dt>Load average</dt><dd>${status.metrics.load_average.map((value)=>value.toFixed(2)).join(' · ')}</dd></div><div><dt>Boot time</dt><dd>${new Date(status.metrics.boot_time).toLocaleString()}</dd></div></dl></section><section class="panel security-panel"><div class="panel-header"><div><h2>Security audit</h2><p>Secrets, permissions, and exposure checks</p></div>${badge(audit.passed?(audit.checks.some((check:any)=>!check.passed)?'Advisories':'Passed'):'Attention',audit.passed?'good':'warn')}</div><div class="audit-list">${audit.checks.map((check:any)=>`<div><span>${icon(check.passed?'check':'warning')}</span><span><strong>${escapeHtml(check.name.replaceAll('_',' '))}</strong><small>${escapeHtml(check.detail)}</small></span>${badge(check.passed?'Pass':check.severity==='critical'?'Critical':'Advisory',check.passed?'good':check.severity==='critical'?'bad':'warn')}</div>`).join('')}</div></section><section class="panel"><div class="panel-header"><div><h2>GStreamer</h2><p>Detected sinks and decoders</p></div></div><dl class="detail-list"><div><dt>Recommended sink</dt><dd>${escapeHtml(doctor.recommended_sink??'None')}</dd></div><div><dt>Decoders</dt><dd>${escapeHtml((doctor.gstreamer?.decoders??[]).join(', ')||'None')}</dd></div><div><dt>Sinks</dt><dd>${escapeHtml((doctor.gstreamer?.sinks??[]).join(', ')||'None')}</dd></div><div><dt>Displays</dt><dd>${doctor.displays?.length??0}</dd></div></dl><button class="button button-ghost button-full" id="refresh-doctor">${icon('refresh')} Refresh capabilities</button></section></div>`; root.querySelector('#download-support')?.addEventListener('click',()=>void download('/system/support-bundle','mosaivue-support.zip')); root.querySelector('#refresh-doctor')?.addEventListener('click',async()=>{try{await api('/system/doctor?refresh=true');toast('Capabilities refreshed','success');await systemPage();}catch(error){toast(errorMessage(error),'error');}}); } catch(error){root.innerHTML+=emptyState('offline','Unable to load system data',errorMessage(error));}
}

export async function logsPage(): Promise<void> {
  cleanEditor(); const root=content(); root.innerHTML=pageHeader('Logs','Structured, credential-redacted service logs')+skeleton(8); const load=async():Promise<void>=>{const since=root.querySelector<HTMLSelectElement>('#log-since')?.value??'1h';const renderer=root.querySelector<HTMLInputElement>('#log-renderer')?.checked??false;const result=await api<{entries:Array<{timestamp:string;unit:string;priority:string;message:string}>}>(`/logs?since=${encodeURIComponent(since)}&renderer=${renderer}`);root.innerHTML=`${pageHeader('Logs','Structured, credential-redacted service logs')}<section class="panel log-panel"><div class="log-toolbar"><select class="select" id="log-since"><option value="1h" ${since==='1h'?'selected':''}>Last hour</option><option value="6h" ${since==='6h'?'selected':''}>Last 6 hours</option><option value="1d" ${since==='1d'?'selected':''}>Last day</option></select><label class="checkbox-row"><input type="checkbox" id="log-renderer" ${renderer?'checked':''}/><span>Renderer only</span></label><button class="button button-ghost" id="refresh-logs">${icon('refresh')} Refresh</button></div><div class="log-view">${result.entries.length?result.entries.map((entry)=>`<div><time>${entry.timestamp?new Date(entry.timestamp).toLocaleTimeString():'—'}</time><span class="log-unit">${escapeHtml((entry.unit??'service').replace('.service',''))}</span><code>${escapeHtml(entry.message)}</code></div>`).join(''):emptyState('logs','No log entries','No matching journald entries were returned.')}</div></section>`;root.querySelector('#refresh-logs')?.addEventListener('click',()=>void load());};try{await load();}catch(error){root.innerHTML+=emptyState('offline','Unable to load logs',errorMessage(error));}
}

export async function backupPage(): Promise<void> {
  cleanEditor(); const root=content(); root.innerHTML=`${pageHeader('Backup & restore','Portable configuration exports, encrypted credential backups, and safe imports')}<div class="backup-grid"><section class="panel backup-card"><span class="large-icon">${icon('download')}</span><h2>Sanitized export</h2><p>Download cameras, layouts, schedules, and settings without saved passwords.</p><button class="button button-primary" id="export-config">Download JSON</button></section><section class="panel backup-card"><span class="large-icon">${icon('lock')}</span><h2>Complete encrypted backup</h2><p>Includes camera credentials inside an AES-GCM encrypted archive protected by your passphrase.</p><button class="button button-secondary" id="encrypted-backup">Create encrypted backup</button></section><section class="panel backup-card"><span class="large-icon">${icon('upload')}</span><h2>Restore or merge</h2><p>Validate a Mosaivue backup before importing it. Existing data is preserved in merge mode.</p><button class="button button-ghost" id="restore-backup">Choose backup</button><input type="file" id="restore-file" hidden accept=".zip,.cwbackup" /></section></div>`;
  root.querySelector('#export-config')?.addEventListener('click',()=>void download('/backup/export','mosaivue-export.json'));
  root.querySelector('#encrypted-backup')?.addEventListener('click',()=>{openDialog({title:'Encrypt complete backup',body:'<label><span>Passphrase</span><input class="input" type="password" name="passphrase" minlength="12" autocomplete="new-password" /></label><p class="form-help">Mosaivue cannot recover a lost backup passphrase.</p>',submitLabel:'Create backup',onSubmit:async(dialog)=>{const passphrase=dialog.querySelector<HTMLInputElement>('[name="passphrase"]')!.value;if(passphrase.length<12){toast('Use at least 12 characters','warning');return false;}try{await download('/backup/create','mosaivue-backup.cwbackup',{method:'POST',body:JSON.stringify({include_credentials:true,passphrase})});toast('Encrypted backup created','success');return true;}catch(error){toast(errorMessage(error),'error');return false;}}});});
  const fileInput=root.querySelector<HTMLInputElement>('#restore-file')!;root.querySelector('#restore-backup')?.addEventListener('click',()=>fileInput.click());fileInput.addEventListener('change',()=>{const file=fileInput.files?.[0];if(!file)return;openDialog({title:'Restore configuration',body:`<p>Selected: <strong>${escapeHtml(file.name)}</strong></p><label><span>Passphrase, if encrypted</span><input class="input" type="password" name="passphrase" /></label><label class="checkbox-row"><input type="checkbox" name="merge" checked /><span>Merge with existing configuration</span></label>`,submitLabel:'Validate and restore',onSubmit:async(dialog)=>{const data=new FormData();data.append('file',file);data.append('passphrase',dialog.querySelector<HTMLInputElement>('[name="passphrase"]')!.value);data.append('merge',String(dialog.querySelector<HTMLInputElement>('[name="merge"]')!.checked));try{const result=await api<{imported:Record<string,number>}>('/backup/restore',{method:'POST',body:data});toast(`Restored ${Object.values(result.imported).reduce((a,b)=>a+b,0)} objects`,'success');return true;}catch(error){toast(errorMessage(error),'error');return false;}}});});
}

export async function aboutPage(): Promise<void> {
  cleanEditor(); const root=content(); root.innerHTML=pageHeader('About','Project information, privacy commitments, and updates')+skeleton(3);try{const [status,update]=await Promise.all([api<SystemStatus>('/system/status'),api<Record<string,unknown>>('/update/check')]);root.innerHTML=`${pageHeader('About','Project information, privacy commitments, and updates')}<section class="about-hero"><img class="brand-mark large" src="/brand/mosaivue-icon.png" alt="" /><div><h2>Mosaivue ${escapeHtml(status.version)}</h2><p>The flexibility of displaycameras without the painful configuration.</p></div></section><div class="about-grid"><section class="panel"><h2>Local-first by design</h2><p>Camera feeds, credentials, layouts, health data, and administration stay on this appliance. Mosaivue has no required cloud account, analytics, telemetry, or unrelated external API calls.</p><dl class="detail-list"><div><dt>License</dt><dd>Apache-2.0</dd></div><div><dt>API</dt><dd><a href="/api/docs" target="_blank">OpenAPI documentation</a></dd></div><div><dt>Renderer</dt><dd>${escapeHtml(status.renderer.backend??'Unavailable')}</dd></div></dl></section><section class="panel"><h2>Updates</h2><p>${escapeHtml(update.message??(update.update_available?`Version ${update.latest_version} is available.`:'This installation is current.'))}</p><dl class="detail-list"><div><dt>Current</dt><dd>${escapeHtml(update.current_version)}</dd></div><div><dt>Latest</dt><dd>${escapeHtml(update.latest_version??'Not configured')}</dd></div><div><dt>Automatic checks</dt><dd>${update.enabled?'Enabled':'Disabled'}</dd></div></dl><p class="form-help">Updates run through the privileged CLI helper so the database is backed up and services are restarted safely.</p></section></div>`;}catch(error){root.innerHTML+=emptyState('offline','Unable to load project information',errorMessage(error));}
}

export async function remotePage(): Promise<void> {
  cleanEditor(); const root=content(); root.innerHTML=pageHeader('Display remote','Fast layout and camera controls for a phone or tablet')+skeleton(4);try{const [layouts,cameras,status]=await Promise.all([api<Layout[]>('/layouts'),api<Camera[]>('/cameras'),api<RendererStatus>('/renderer/status')]);root.innerHTML=`<div class="remote-shell"><header><div><img class="brand-mark small" src="/brand/mosaivue-icon.png" alt="" /><span><strong>Mosaivue remote</strong><small>${status.state}</small></span></div><a href="/" data-route class="icon-button">${icon('close')}</a></header><section><h1>Layouts</h1><div class="remote-layouts">${layouts.map((layout)=>`<button data-remote-layout="${layout.id}" class="${layout.active?'is-active':''}"><span class="mini-layout">${(layout.revision?.data.slots??[]).slice(0,8).map((slot)=>`<i style="left:${slot.x*100}%;top:${slot.y*100}%;width:${slot.width*100}%;height:${slot.height*100}%"></i>`).join('')}</span><strong>${escapeHtml(layout.name)}</strong>${layout.active?'<small>On display</small>':'<small>Tap to apply</small>'}</button>`).join('')}</div></section><section><div class="remote-section-head"><h1>Focus camera</h1><button class="button button-ghost" id="restore-layout">Restore layout</button></div><div class="remote-cameras">${cameras.filter((camera)=>camera.enabled).map((camera)=>`<button data-focus-camera="${camera.id}"><span>${icon('camera')}</span><strong>${escapeHtml(camera.name)}</strong><small>${escapeHtml(camera.location??'')}</small></button>`).join('')}</div></section></div>`;root.querySelectorAll<HTMLButtonElement>('[data-remote-layout]').forEach((button)=>button.addEventListener('click',async()=>{try{await api(`/layouts/${button.dataset.remoteLayout}/activate`,{method:'POST'});toast('Layout applied','success');await remotePage();}catch(error){toast(errorMessage(error),'error');}}));root.querySelectorAll<HTMLButtonElement>('[data-focus-camera]').forEach((button)=>button.addEventListener('click',async()=>{try{await api('/renderer/focus',{method:'POST',body:JSON.stringify({camera_id:button.dataset.focusCamera,aspect_mode:'cover'})});toast('Camera focused on display','success');}catch(error){toast(errorMessage(error),'error');}}));root.querySelector('#restore-layout')?.addEventListener('click',async()=>{try{await api('/renderer/restore',{method:'POST'});toast('Layout restored','success');}catch(error){toast(errorMessage(error),'error');}});}catch(error){root.innerHTML+=emptyState('offline','Remote unavailable',errorMessage(error));}
}
