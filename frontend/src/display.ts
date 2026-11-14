import { api } from './api.js';
import { featureSupport } from './display-state.js';
import { parseRenderDimension } from './layout-output.js';
import type { DisplayProfile, Layout, RendererCapabilities, RendererStatus } from './types.js';
import { badge, emptyState, escapeHtml, icon, openDialog, pageHeader, skeleton, toast } from './ui.js';

type DisplayOutput = { name: string; status: string; preferred_mode: string | null };
const errorMessage = (error: unknown): string => error instanceof Error ? error.message : String(error);

export function displayProfileForm(outputs: string[], capabilities?: RendererCapabilities, profile?: DisplayProfile): string {
  const available = (feature: 'output_selection' | 'refresh_rate' | 'portrait' | 'prevent_blanking'): string => featureSupport(capabilities, feature) === true ? '' : 'disabled';
  const choices = [...new Set([...outputs, ...(profile?.output_name ? [profile.output_name] : [])])];
  return `<div class="form-grid two">
    <label><span>Name</span><input class="input" name="name" value="${escapeHtml(profile?.name ?? 'HDMI 1080p')}" required maxlength="255" /></label>
    <label><span>Output connector</span><select class="select" name="output" ${available('output_selection')}><option value="">Default output</option>${choices.map((item) => `<option value="${escapeHtml(item)}" ${item === profile?.output_name ? 'selected' : ''}>${escapeHtml(item)}</option>`).join('')}</select></label>
    <label><span>Width</span><input class="input" type="number" name="width" min="320" max="16384" step="1" value="${profile?.width ?? 1920}" required /></label>
    <label><span>Height</span><input class="input" type="number" name="height" min="240" max="16384" step="1" value="${profile?.height ?? 1080}" required /></label>
    <label><span>Refresh rate</span><input class="input" type="number" name="refresh" min="0.000001" max="240" step="any" value="${profile?.refresh_rate ?? 60}" ${available('refresh_rate')} /></label>
    <label><span>Rotation</span><select class="select" name="rotation" ${available('portrait')}>${[0, 90, 180, 270].map((rotation) => `<option ${rotation === (profile?.rotation ?? 0) ? 'selected' : ''}>${rotation}</option>`).join('')}</select></label>
    <label class="checkbox-row span-two"><input type="checkbox" name="blanking" ${profile?.prevent_blanking === false ? '' : 'checked'} ${available('prevent_blanking')} /><span>Prevent display blanking</span></label>
    <p class="form-help span-two">Width and height set the render area for layouts using this profile. Disabled settings are unsupported or not reported by the current renderer; saved values are preserved as metadata. <a href="/renderer" data-route>View renderer capabilities</a>.</p>
  </div>`;
}

type ProfileValues = { name: string; width: string; height: string; output: string; refresh: string; rotation: string; blanking: boolean };
export function displayProfilePayload(values: ProfileValues, profile?: DisplayProfile, capabilities?: RendererCapabilities): Record<string, unknown> {
  const name = values.name.trim();
  if (!name) throw new Error('Profile name is required');
  const refresh = featureSupport(capabilities, 'refresh_rate') === true ? Number(values.refresh) : profile?.refresh_rate ?? 60;
  const rotation = featureSupport(capabilities, 'portrait') === true ? Number(values.rotation) : profile?.rotation ?? 0;
  if (!Number.isFinite(refresh) || refresh <= 0 || refresh > 240) throw new Error('Refresh rate must be greater than 0 and at most 240');
  if (![0, 90, 180, 270].includes(rotation)) throw new Error('Rotation must be 0, 90, 180, or 270');
  return {
    name, width: parseRenderDimension(values.width, 'width', false), height: parseRenderDimension(values.height, 'height', false),
    output_name: featureSupport(capabilities, 'output_selection') === true ? values.output || null : profile?.output_name ?? null,
    refresh_rate: refresh, rotation,
    prevent_blanking: featureSupport(capabilities, 'prevent_blanking') === true ? values.blanking : profile?.prevent_blanking ?? true,
  };
}

export async function renderDisplay(root: HTMLElement): Promise<void> {
  const header = (): string => pageHeader('Display', 'Detected outputs and reusable render dimensions', `<button class="button button-primary" id="add-display-profile">${icon('plus')} New profile</button>`);
  root.innerHTML = header() + skeleton(4);
  const refresh = async (): Promise<void> => {
    const [outputs, profiles, renderer, layouts] = await Promise.all([
      api<DisplayOutput[]>('/display/outputs'), api<DisplayProfile[]>('/display/profiles'),
      api<RendererStatus>('/renderer/status').catch(() => null),
      api<Layout[]>('/layouts').catch(() => null),
    ]);
    const outputCards = outputs.map((output) => `<article><span class="display-icon">${icon('display')}</span><div><strong>${escapeHtml(output.name)}</strong><small>${escapeHtml(output.preferred_mode ?? 'No mode reported')} · ${escapeHtml(output.status)}</small></div>${badge(output.status, output.status === 'connected' ? 'good' : 'warn')}</article>`).join('');
    const fallback = renderer?.backend === 'omxplayer'
      ? 'OMXPlayer uses legacy HDMI overlays; DRM connector detection is not required.'
      : renderer?.state === 'RUNNING' ? `The renderer is using ${renderer.sink ?? 'its configured display sink'}.` : 'Check the HDMI connection and renderer status.';
    root.innerHTML = `${header()}
      <section class="output-strip">${outputCards || `<article><span class="display-icon">${icon('display')}</span><div><strong>No DRM connector reported</strong><small>${escapeHtml(fallback)}</small></div></article>`}</section>
      <p class="display-notice">Assign a profile in a layout's <strong>Layout settings</strong>. Saving shared profile dimensions does not resize a running wall; apply or reapply each affected layout. Detected connectors are diagnostic information. <a href="/renderer" data-route>View renderer capabilities</a>.</p>
      <section class="panel table-panel"><div class="panel-header"><div><h2>Display profiles</h2><p>Stored profile values. Unsupported connector, refresh, rotation and blanking settings do not change the display.</p></div></div>
        ${profiles.length ? `<div class="data-table-wrap"><table class="data-table"><thead><tr><th>Name / used by</th><th>Stored output</th><th>Dimensions</th><th>Stored refresh</th><th>Stored rotation</th><th></th></tr></thead><tbody>${profiles.map((profile) => {
          const assigned = layouts?.filter((layout) => layout.display_profile_id === profile.id);
          return `<tr data-display-profile="${profile.id}"><td><strong>${escapeHtml(profile.name)}</strong><div class="profile-layout-links">${assigned?.length ? assigned.map((layout) => `<a href="/layouts/${layout.id}/edit" data-route>${escapeHtml(layout.name)}</a>`).join(', ') : assigned ? 'Not assigned' : 'Layout usage unavailable'}</div></td><td>${escapeHtml(profile.output_name ?? 'Default')}</td><td>${profile.width} × ${profile.height}</td><td>${profile.refresh_rate} Hz</td><td>${profile.rotation}°</td><td><div class="row-actions"><button class="icon-button" data-display-edit="${profile.id}" aria-label="Edit ${escapeHtml(profile.name)}">${icon('edit')}</button><button class="icon-button" data-display-delete="${profile.id}" aria-label="Delete ${escapeHtml(profile.name)}" ${!assigned || assigned.length ? 'disabled title="Remove layout assignments before deleting this profile"' : ''}>${icon('trash')}</button></div></td></tr>`;
        }).join('')}</tbody></table></div>` : emptyState('display', 'No display profiles', 'Create a profile with render dimensions for a layout.')}
      </section>`;
    const openProfile = (profile?: DisplayProfile): void => {
      const assigned = layouts?.filter((layout) => layout.display_profile_id === profile?.id) ?? [];
      openDialog({ title: profile ? `Edit ${profile.name}` : 'New display profile', body: displayProfileForm(outputs.map((item) => item.name), renderer?.capabilities, profile) + (assigned.length ? `<p class="display-notice">Used by ${assigned.map((layout) => escapeHtml(layout.name)).join(', ')}. Reapply those layouts after changing dimensions.</p>` : ''), submitLabel: profile ? 'Save profile' : 'Create profile', onSubmit: async (dialog) => {
        const get = (name: string): string => dialog.querySelector<HTMLInputElement | HTMLSelectElement>(`[name="${name}"]`)!.value;
        const payload = displayProfilePayload({ name: get('name'), width: get('width'), height: get('height'), output: get('output'), refresh: get('refresh'), rotation: get('rotation'), blanking: dialog.querySelector<HTMLInputElement>('[name="blanking"]')!.checked }, profile, renderer?.capabilities);
        await api(profile ? `/display/profiles/${profile.id}` : '/display/profiles', { method: profile ? 'PUT' : 'POST', body: JSON.stringify(payload) });
        toast(profile ? 'Display profile saved. Reapply associated layouts to use its dimensions.' : 'Display profile created', 'success'); await refresh(); return true;
      } });
    };
    root.querySelector('#add-display-profile')?.addEventListener('click', () => openProfile());
    root.querySelectorAll<HTMLButtonElement>('[data-display-edit]').forEach((button) => button.addEventListener('click', () => openProfile(profiles.find((profile) => profile.id === button.dataset.displayEdit))));
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
