import { escapeHtml } from './ui.js';
/** Match the controller: profile dimensions override layout dimensions, then current renderer size. */
export function resolveLayoutOutput(data, profileId, profiles, renderer) {
    const profile = profiles.find((item) => item.id === profileId);
    if (profile)
        return { width: profile.width, height: profile.height, source: `Profile: ${profile.name}`, warning: null };
    const width = data?.output_width ?? renderer?.output?.width ?? 1920;
    const height = data?.output_height ?? renderer?.output?.height ?? 1080;
    const inherited = data?.output_width == null || data?.output_height == null;
    const warning = profileId ? 'The assigned display profile is unavailable. Choose another profile or layout dimensions before saving.'
        : inherited && !renderer?.output ? 'Renderer size is unavailable. Unspecified dimensions use a preview fallback; actual application uses the renderer size.' : null;
    return { width, height, source: inherited ? 'Layout / current renderer dimensions' : 'Layout dimensions', warning };
}
export function parseRenderDimension(value, axis, allowBlank = true) {
    if (!value.trim() && allowBlank)
        return null;
    const number = Number(value);
    const minimum = axis === 'width' ? 320 : 240;
    if (!Number.isInteger(number) || number < minimum || number > 16384)
        throw new Error(`${axis === 'width' ? 'Width' : 'Height'} must be a whole number from ${minimum} to 16384`);
    return number;
}
export function layoutOutputEdit(data, profileId, width, height, profiles) {
    if (profileId && !profiles.some((profile) => profile.id === profileId))
        throw new Error('The selected display profile is unavailable. Choose another profile or layout dimensions.');
    return {
        display_profile_id: profileId || null,
        // Preserve the layout's fallback dimensions while a profile owns sizing.
        output_width: profileId ? data.output_width ?? null : parseRenderDimension(width, 'width'),
        output_height: profileId ? data.output_height ?? null : parseRenderDimension(height, 'height'),
    };
}
export function layoutOutputFields(data, profileId, profiles) {
    const missing = profileId && !profiles.some((profile) => profile.id === profileId);
    return `<fieldset class="layout-output-fields"><legend>Render dimensions</legend><div class="form-grid two">
    <label class="span-two"><span>Display profile</span><select class="select" name="layout_display_profile"><option value="">Use layout dimensions</option>${missing ? `<option value="${escapeHtml(profileId)}" selected>Unavailable saved profile</option>` : ''}${profiles.map((profile) => `<option value="${escapeHtml(profile.id)}" ${profileId === profile.id ? 'selected' : ''}>${escapeHtml(profile.name)} · ${profile.width} × ${profile.height}</option>`).join('')}</select></label>
    <label><span>Layout width</span><input class="input" type="number" name="layout_output_width" min="320" max="16384" step="1" value="${data.output_width ?? ''}" placeholder="Current renderer width" /></label>
    <label><span>Layout height</span><input class="input" type="number" name="layout_output_height" min="240" max="16384" step="1" value="${data.output_height ?? ''}" placeholder="Current renderer height" /></label>
    <p class="form-help span-two" data-layout-output-preview role="status"></p>
    <p class="form-help span-two">A profile overrides layout dimensions. With no profile, blank dimensions inherit the renderer's current size. Normalized tiles keep their proportions. This sets the rendered canvas; it does not select a physical connector, rotate the monitor, or change its refresh mode. <a href="/display" data-route>Manage profiles</a>.</p>
  </div></fieldset>`;
}
export function bindLayoutOutputFields(dialog, data, profiles, renderer) {
    const select = dialog.querySelector('[name="layout_display_profile"]');
    const width = dialog.querySelector('[name="layout_output_width"]');
    const height = dialog.querySelector('[name="layout_output_height"]');
    const preview = dialog.querySelector('[data-layout-output-preview]');
    const read = () => layoutOutputEdit(data, select.value, width.value, height.value, profiles);
    const update = () => {
        width.disabled = height.disabled = Boolean(select.value);
        try {
            const edit = read();
            const output = resolveLayoutOutput(edit, edit.display_profile_id, profiles, renderer);
            preview.textContent = `Render preview: ${output.width} × ${output.height} · ${output.source}.${output.warning ? ` ${output.warning}` : ''}`;
        }
        catch (error) {
            preview.textContent = error instanceof Error ? error.message : 'Invalid dimensions';
        }
    };
    select.addEventListener('change', update);
    width.addEventListener('input', update);
    height.addEventListener('input', update);
    update();
    return read;
}
export function pixelPlacementWarning(data, output) {
    const count = data.slots.filter((slot) => {
        const pixel = slot.pixel_override;
        return pixel && (pixel.x + pixel.width > output.width || pixel.y + pixel.height > output.height);
    }).length;
    return count ? `${count} fixed-pixel tile${count === 1 ? '' : 's'} extend beyond this render size and will be bounded to fit. Saved pixel values are preserved; use canvas placement to convert them.` : null;
}
export function validateLayoutOutputPlacement(data, edit) {
    if (edit.display_profile_id)
        return;
    const outside = data.slots.some((slot) => {
        const pixel = slot.pixel_override;
        return pixel && (edit.output_width !== null && pixel.x + pixel.width > edit.output_width || edit.output_height !== null && pixel.y + pixel.height > edit.output_height);
    });
    if (outside)
        throw new Error('These layout dimensions would exclude saved fixed-pixel tiles. Use canvas placement for those tiles first, or choose larger dimensions.');
}
//# sourceMappingURL=layout-output.js.map