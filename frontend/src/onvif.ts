import { api } from './api.js';
import type { Camera } from './types.js';
import { escapeHtml, openDialog, toast } from './ui.js';

type OnvifProfile = { token: string; name: string; codec: string | null; width: number | null; height: number | null; fps: number | null; bitrate: number | null };

export function onvifDialog(refresh: () => Promise<void>): void {
  let inspectedCredentials = '';
  const dialog = openDialog({
    title: 'Import an ONVIF camera', wide: true, submitLabel: 'Inspect profiles',
    body: `<div class="form-grid two">
      <label class="span-two"><span>Device service URL</span><input class="input mono" type="url" name="device_url" required placeholder="http://192.168.1.20/onvif/device_service" /></label>
      <label><span>Camera name</span><input class="input" name="name" maxlength="255" required placeholder="Front door" /></label>
      <label><span>ONVIF username</span><input class="input" name="username" autocomplete="off" /></label>
      <label class="span-two"><span>ONVIF password</span><input class="input" name="password" type="password" autocomplete="new-password" /></label>
    </div><p class="form-help">Enter the camera's ONVIF device address. Media1 profile inspection imports its RTSP streams; enable ONVIF on the camera first. Some cameras use a separate ONVIF account.</p><div id="onvif-profiles" aria-live="polite"></div>`,
    onSubmit: async (modal) => {
      const value = (name: string): string => modal.querySelector<HTMLInputElement>(`[name="${name}"]`)!.value;
      const credentials = { device_url: value('device_url').trim(), username: value('username').trim(), password: value('password') };
      const fingerprint = JSON.stringify(credentials);
      const results = modal.querySelector<HTMLElement>('#onvif-profiles')!;
      const submit = modal.querySelector<HTMLButtonElement>('button[type="submit"]')!;
      try {
        if (fingerprint !== inspectedCredentials) {
          results.innerHTML = '<p class="form-help">Inspecting camera profiles…</p>';
          const response = await api<{ profiles: OnvifProfile[]; warnings: string[] }>('/onvif/profiles', { method: 'POST', body: JSON.stringify(credentials) });
          if (!modal.isConnected) return false;
          results.innerHTML = `${response.warnings.map((warning) => `<p class="form-help">${escapeHtml(warning)}</p>`).join('')}<fieldset><legend>Profiles to import</legend><div class="camera-check-list">${response.profiles.map((profile) => `<label><input type="checkbox" name="onvif_profile" value="${escapeHtml(profile.token)}" checked /><span><strong>${escapeHtml(profile.name)}</strong><small>${escapeHtml(profile.codec ?? 'Unknown codec')} · ${profile.width && profile.height ? `${profile.width} × ${profile.height}` : 'Resolution not reported'}${profile.fps ? ` · ${profile.fps} fps` : ''}</small></span></label>`).join('')}</div></fieldset>`;
          if (!response.profiles.length) { results.innerHTML += '<p>No supported RTSP profiles were returned. Add the stream URL manually if this camera only supports Media2.</p>'; return false; }
          inspectedCredentials = fingerprint;
          submit.textContent = 'Import selected profiles';
          return false;
        }
        const tokens = [...modal.querySelectorAll<HTMLInputElement>('[name="onvif_profile"]:checked')].map((input) => input.value);
        if (!tokens.length) { toast('Select at least one profile', 'warning'); return false; }
        await api<Camera>('/onvif/import', { method: 'POST', body: JSON.stringify({ ...credentials, name: value('name').trim(), profile_tokens: tokens }) });
        toast('ONVIF camera imported', 'success');
        await refresh();
        return true;
      } catch (error) {
        toast(error instanceof Error ? error.message : 'ONVIF request failed', 'error');
        if (fingerprint !== inspectedCredentials) results.textContent = 'Inspection did not complete. Check the device address, credentials, and ONVIF setting.';
        return false;
      }
    },
  });
  dialog.querySelector<HTMLInputElement>('[name="device_url"]')?.focus();
}
