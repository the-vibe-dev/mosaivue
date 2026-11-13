import { api } from './api.js';
import { featureSupport } from './display-state.js';
import type { DisplayProfile, RendererCapabilities, RendererStatus } from './types.js';
import { badge, emptyState, escapeHtml, icon, openDialog, pageHeader, skeleton, toast } from './ui.js';

type DisplayOutput = { name: string; status: string; preferred_mode: string | null };
const errorMessage = (error: unknown): string => error instanceof Error ? error.message : String(error);

export function displayProfileForm(outputs: string[], capabilities?: RendererCapabilities): string {
  const available = (feature: 'output_selection' | 'refresh_rate' | 'portrait' | 'prevent_blanking'): string => featureSupport(capabilities, feature) === true ? '' : 'disabled';
  return `<div class="form-grid two">
    <label><span>Name</span><input class="input" name="name" value="HDMI 1080p" required maxlength="255" /></label>
    <label><span>Output connector</span><select class="select" name="output" ${available('output_selection')}><option value="">Default output</option>${outputs.map((item) => `<option>${escapeHtml(item)}</option>`).join('')}</select></label>
    <label><span>Width</span><input class="input" type="number" name="width" min="320" max="16384" value="1920" required /></label>
    <label><span>Height</span><input class="input" type="number" name="height" min="240" max="16384" value="1080" required /></label>
    <label><span>Refresh rate</span><input class="input" type="number" name="refresh" min="1" max="240" value="60" ${available('refresh_rate')} /></label>
    <label><span>Rotation</span><select class="select" name="rotation" ${available('portrait')}><option>0</option><option>90</option><option>180</option><option>270</option></select></label>
    <label class="checkbox-row span-two"><input type="checkbox" name="blanking" checked ${available('prevent_blanking')} /><span>Prevent display blanking</span></label>
    <p class="form-help span-two">Width and height set the render area for layouts using this profile. Disabled settings are unsupported or not reported by the current renderer; their defaults are stored as metadata. <a href="/renderer" data-route>View renderer capabilities</a>.</p>
  </div>`;
}

export async function renderDisplay(root: HTMLElement): Promise<void> {
  const header = (): string => pageHeader('Display', 'Detected outputs and reusable render dimensions', `<button class="button button-primary" id="add-display-profile">${icon('plus')} New profile</button>`);
  root.innerHTML = header() + skeleton(4);
  const refresh = async (): Promise<void> => {
    const [outputs, profiles, renderer] = await Promise.all([
      api<DisplayOutput[]>('/display/outputs'), api<DisplayProfile[]>('/display/profiles'),
      api<RendererStatus>('/renderer/status').catch(() => null),
    ]);
    const outputCards = outputs.map((output) => `<article><span class="display-icon">${icon('display')}</span><div><strong>${escapeHtml(output.name)}</strong><small>${escapeHtml(output.preferred_mode ?? 'No mode reported')} · ${escapeHtml(output.status)}</small></div>${badge(output.status, output.status === 'connected' ? 'good' : 'warn')}</article>`).join('');
    const fallback = renderer?.backend === 'omxplayer'
      ? 'OMXPlayer uses legacy HDMI overlays; DRM connector detection is not required.'
      : renderer?.state === 'RUNNING' ? `The renderer is using ${renderer.sink ?? 'its configured display sink'}.` : 'Check the HDMI connection and renderer status.';
    root.innerHTML = `${header()}
      <section class="output-strip">${outputCards || `<article><span class="display-icon">${icon('display')}</span><div><strong>No DRM connector reported</strong><small>${escapeHtml(fallback)}</small></div></article>`}</section>
      <p class="display-notice">Detected connectors are diagnostic information. Supported output controls depend on the player. <a href="/renderer" data-route>View renderer capabilities</a>.</p>
      <section class="panel table-panel"><div class="panel-header"><div><h2>Display profiles</h2><p>Stored profile values. Unsupported connector, refresh, rotation and blanking settings do not change the display.</p></div></div>
        ${profiles.length ? `<div class="data-table-wrap"><table class="data-table"><thead><tr><th>Name</th><th>Stored output</th><th>Dimensions</th><th>Stored refresh</th><th>Stored rotation</th><th></th></tr></thead><tbody>${profiles.map((profile) => `<tr><td><strong>${escapeHtml(profile.name)}</strong></td><td>${escapeHtml(profile.output_name ?? 'Default')}</td><td>${profile.width} × ${profile.height}</td><td>${profile.refresh_rate} Hz</td><td>${profile.rotation}°</td><td><button class="icon-button" data-display-delete="${profile.id}" aria-label="Delete ${escapeHtml(profile.name)}">${icon('trash')}</button></td></tr>`).join('')}</tbody></table></div>` : emptyState('display', 'No display profiles', 'Create a profile with render dimensions for a layout.')}
      </section>`;
    root.querySelector('#add-display-profile')?.addEventListener('click', () => {
      openDialog({ title: 'New display profile', body: displayProfileForm(outputs.map((item) => item.name), renderer?.capabilities), submitLabel: 'Create profile', onSubmit: async (dialog) => {
        const get = (name: string): string => dialog.querySelector<HTMLInputElement | HTMLSelectElement>(`[name="${name}"]`)!.value;
        await api('/display/profiles', { method: 'POST', body: JSON.stringify({
          name: get('name').trim(), output_name: get('output') || null, width: Number(get('width')), height: Number(get('height')),
          refresh_rate: Number(get('refresh')), rotation: Number(get('rotation')), prevent_blanking: dialog.querySelector<HTMLInputElement>('[name="blanking"]')!.checked,
        }) });
        toast('Display profile created', 'success'); await refresh(); return true;
      } });
    });
    root.querySelectorAll<HTMLButtonElement>('[data-display-delete]').forEach((button) => button.addEventListener('click', async () => {
      if (!confirm('Delete this display profile?')) return;
      button.disabled = true;
      try { await api(`/display/profiles/${button.dataset.displayDelete}`, { method: 'DELETE' }); await refresh(); }
      catch (error) { button.disabled = false; toast(errorMessage(error), 'error'); }
    }));
  };
  try { await refresh(); }
  catch (error) { root.innerHTML = header() + emptyState('offline', 'Unable to load display settings', errorMessage(error)); }
}
