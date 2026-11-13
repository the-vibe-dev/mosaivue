/** Keep saved profile identity and metadata when editing only the visible fields. */
export function mergeProfileEdit(original, changes) {
    return { ...original, ...changes };
}
/** Blank password means preserve/use embedded credentials; whitespace is a valid secret. */
export function credentialEdit(password, clear) {
    if (clear)
        return { clear_credentials: true };
    return password !== '' ? { password } : {};
}
export function filterCameras(cameras, query, status = 'all') {
    const words = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
    return cameras.filter((camera) => {
        if (status === 'enabled' && !camera.enabled || status === 'disabled' && camera.enabled)
            return false;
        const haystack = [camera.name, camera.location, camera.host, camera.vendor, camera.model, camera.description, ...camera.tags].join(' ').toLocaleLowerCase();
        return words.every((word) => haystack.includes(word));
    });
}
/** Keep order and per-entry choices from the editor, never reconstruct in camera-name order. */
export function rotationEntries(rows) {
    return rows.filter((row) => row.selected).map((row) => ({ camera_id: row.cameraId, weight: row.weight, stream_profile_id: row.profileId || null }));
}
export function setGeometry(slot, field, percent) {
    if (!Number.isFinite(percent) || slot.locked)
        return slot;
    const next = { ...slot };
    const value = Math.max(0, Math.min(1, percent / 100));
    if (field === 'x')
        next.x = Math.min(value, 1 - next.width);
    if (field === 'y')
        next.y = Math.min(value, 1 - next.height);
    if (field === 'width')
        next.width = Math.max(0.01, Math.min(value, 1 - next.x));
    if (field === 'height')
        next.height = Math.max(0.01, Math.min(value, 1 - next.y));
    return next;
}
//# sourceMappingURL=forms.js.map