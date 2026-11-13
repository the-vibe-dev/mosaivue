import type { Camera, RotationEntry, Slot, StreamProfile } from './types.js';

/** Keep saved profile identity and metadata when editing only the visible fields. */
export function mergeProfileEdit(original: Partial<StreamProfile> | undefined, changes: Partial<StreamProfile>): Partial<StreamProfile> {
  return { ...original, ...changes };
}

/** Blank password means preserve/use embedded credentials; whitespace is a valid secret. */
export function credentialEdit(password: string, clear: boolean): Record<string, unknown> {
  if (clear) return { clear_credentials: true };
  return password !== '' ? { password } : {};
}

export function filterCameras(cameras: Camera[], query: string, status = 'all'): Camera[] {
  const words = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  return cameras.filter((camera) => {
    if (status === 'enabled' && !camera.enabled || status === 'disabled' && camera.enabled) return false;
    const haystack = [camera.name, camera.location, camera.host, camera.vendor, camera.model, camera.description, ...camera.tags].join(' ').toLocaleLowerCase();
    return words.every((word) => haystack.includes(word));
  });
}

/** Keep order and per-entry choices from the editor, never reconstruct in camera-name order. */
export function rotationEntries(rows: Array<{ cameraId: string; selected: boolean; weight: number; profileId: string }>): RotationEntry[] {
  return rows.filter((row) => row.selected).map((row) => ({ camera_id: row.cameraId, weight: row.weight, stream_profile_id: row.profileId || null }));
}

export function setGeometry(slot: Slot, field: 'x' | 'y' | 'width' | 'height', percent: number): Slot {
  if (!Number.isFinite(percent) || slot.locked) return slot;
  const next = { ...slot };
  const value = Math.max(0, Math.min(1, percent / 100));
  if (field === 'x') next.x = Math.min(value, 1 - next.width);
  if (field === 'y') next.y = Math.min(value, 1 - next.height);
  if (field === 'width') next.width = Math.max(0.01, Math.min(value, 1 - next.x));
  if (field === 'height') next.height = Math.max(0.01, Math.min(value, 1 - next.y));
  return next;
}
