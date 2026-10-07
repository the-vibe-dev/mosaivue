import { api } from './api.js';
import { newId } from './ids.js';
import { templateGeometry } from './templates.js';
import { escapeHtml, icon, toast } from './ui.js';
function cloneData(value) {
    return structuredClone(value);
}
function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
}
function percent(value) {
    return `${(value * 100).toFixed(1)}%`;
}
function defaultSlot(camera, x = 0.05, y = 0.05) {
    return {
        id: newId(),
        name: camera.name,
        type: 'fixed',
        x: clamp(x, 0, 0.7),
        y: clamp(y, 0, 0.7),
        width: 0.3,
        height: 0.3,
        z_index: 0,
        enabled: true,
        camera_id: camera.id,
        rotation_group_id: null,
        selected_camera_id: null,
        stream_profile_id: null,
        stream_selection: 'automatic',
        aspect_mode: 'cover',
        crop: { top: 0, right: 0, bottom: 0, left: 0 },
        background: '#090d12',
        border: '#27313c',
        border_width: 0,
        label: camera.name,
        title_position: 'bottom-left',
        muted: true,
        locked: false,
        opacity: 1,
        pixel_override: null,
    };
}
export class LayoutEditor {
    host;
    layout;
    cameras;
    groups;
    onSaved;
    data;
    selected = new Set();
    selectedCameraId = null;
    history = [];
    historyIndex = -1;
    gridEnabled = true;
    showPreviews = false;
    previewUrls = new Map();
    clipboard = [];
    keyHandler = (event) => this.onKeyDown(event);
    resizeObserver;
    constructor(host, layout, cameras, groups, onSaved) {
        this.host = host;
        this.layout = layout;
        this.cameras = cameras;
        this.groups = groups;
        this.onSaved = onSaved;
        this.data = cloneData(layout.revision?.data ?? {
            schema_version: 1,
            slots: [],
            background: '#05080c',
            output_width: 1920,
            output_height: 1080,
            grid_columns: 12,
            grid_rows: 12,
        });
        this.recordHistory();
    }
    mount() {
        document.addEventListener('keydown', this.keyHandler);
        this.render();
    }
    destroy() {
        document.removeEventListener('keydown', this.keyHandler);
        this.resizeObserver?.disconnect();
        for (const url of this.previewUrls.values())
            URL.revokeObjectURL(url);
    }
    render() {
        const selectedSlots = this.data.slots.filter((slot) => this.selected.has(slot.id));
        const outputWidth = this.data.output_width ?? 1920;
        const outputHeight = this.data.output_height ?? 1080;
        const ratio = `${outputWidth} / ${outputHeight}`;
        this.host.innerHTML = `
      <section class="editor-shell">
        <header class="editor-toolbar">
          <div class="editor-title-block">
            <a class="icon-button" href="/layouts" data-route aria-label="Back to layouts">${icon('chevron', 'icon-back')}</a>
            <div><strong>${escapeHtml(this.layout.name)}</strong><span>Revision ${this.layout.current_revision}${this.layout.active ? ' · active' : ''}</span></div>
          </div>
          <div class="toolbar-cluster">
            <button class="icon-button" data-action="undo" title="Undo (Ctrl+Z)" ${this.historyIndex <= 0 ? 'disabled' : ''}>${icon('undo')}</button>
            <button class="icon-button" data-action="redo" title="Redo (Ctrl+Y)" ${this.historyIndex >= this.history.length - 1 ? 'disabled' : ''}>${icon('redo')}</button>
            <span class="toolbar-divider"></span>
            <button class="toolbar-button ${this.gridEnabled ? 'is-active' : ''}" data-action="toggle-grid">${icon('grid')} Grid</button>
            <button class="toolbar-button ${this.showPreviews ? 'is-active' : ''}" data-action="toggle-previews">${icon('camera')} Preview</button>
          </div>
          <div class="toolbar-cluster toolbar-actions">
            <button class="button button-ghost" data-action="revert">Revert</button>
            <button class="button button-secondary" data-action="save">${icon('save')} Save draft</button>
            <button class="button button-primary" data-action="save-apply">${icon('play')} Save & apply</button>
          </div>
        </header>
        <div class="editor-workspace">
          <aside class="editor-library">
            <div class="pane-heading"><div><h2>Cameras</h2><p>Click a camera, then click the display</p></div></div>
            <label class="search-field">${icon('search')}<input type="search" placeholder="Filter cameras" data-camera-search /></label>
            <div class="camera-library-list">
              ${this.cameraLibraryHtml(this.cameras)}
            </div>
            <div class="pane-section">
              <div class="pane-heading compact"><div><h2>Templates</h2></div></div>
              <div class="template-grid">
                ${Array.from({ length: 9 }, (_, index) => {
            const count = index + 2;
            const tiles = templateGeometry(count).map(([x, y, width, height]) => `<i style="left:${x * 100}%;top:${y * 100}%;width:${width * 100}%;height:${height * 100}%"></i>`).join('');
            return `<button data-template="${count}" title="Featured layout for ${count} cameras"><span class="template-preview template-featured">${tiles}</span><small>${count} cameras</small></button>`;
        }).join('')}
              </div>
            </div>
          </aside>
          <main class="editor-stage">
            <div class="stage-ruler"><span>${outputWidth} × ${outputHeight}</span><span>${this.data.slots.length} slot${this.data.slots.length === 1 ? '' : 's'}</span></div>
            <div class="display-frame" style="aspect-ratio:${ratio}; --grid-cols:${this.data.grid_columns}; --grid-rows:${this.data.grid_rows}; background:${escapeHtml(this.data.background)}">
              <div class="layout-canvas ${this.gridEnabled ? 'show-grid' : ''}" tabindex="0" aria-label="Layout canvas">
                ${this.data.slots.map((slot) => this.slotHtml(slot)).join('')}
                ${this.data.slots.length === 0 ? '<div class="canvas-empty"><div>' + icon('layout') + '</div><strong>Build your camera wall</strong><span>Click a camera, then click here; or choose a template.</span></div>' : ''}
              </div>
            </div>
            <div class="canvas-statusbar">
              <span>${this.selectedCameraId ? 'Click a tile to replace its camera, or an empty area to place a tile.' : 'Select a tile and drag its handles to expand or contract.'}</span>
              <span>${selectedSlots.length ? `${selectedSlots.length} selected` : 'Nothing selected'}</span>
            </div>
          </main>
          <aside class="editor-inspector">
            ${this.inspectorHtml(selectedSlots)}
          </aside>
        </div>
      </section>`;
        this.attachEvents();
    }
    cameraLibraryHtml(cameras) {
        if (!cameras.length)
            return '<div class="library-empty">No enabled cameras yet.</div>';
        return cameras.map((camera) => `
      <button class="camera-library-item ${this.selectedCameraId === camera.id ? 'is-selected' : ''}" draggable="true" data-camera-id="${camera.id}" aria-pressed="${this.selectedCameraId === camera.id}">
        <span class="camera-thumb">${icon('camera')}</span>
        <span class="camera-library-copy"><strong>${escapeHtml(camera.name)}</strong><small>${escapeHtml(camera.location ?? camera.host ?? 'RTSP camera')}</small></span>
        <span class="camera-state ${camera.enabled ? 'is-online' : 'is-disabled'}"></span>
      </button>`).join('');
    }
    slotHtml(slot) {
        const camera = this.cameras.find((item) => item.id === (slot.selected_camera_id ?? slot.camera_id));
        const group = this.groups.find((item) => item.id === slot.rotation_group_id);
        const selected = this.selected.has(slot.id);
        const preview = this.previewUrls.get(slot.id);
        const title = slot.label || camera?.name || group?.name || slot.name;
        const sourceText = slot.type === 'rotation' ? `${group?.camera_entries.length ?? 0} camera rotation` : camera?.location ?? camera?.host ?? 'Camera slot';
        return `
      <div class="canvas-slot slot-aspect-${slot.aspect_mode} ${selected ? 'is-selected' : ''} ${slot.locked ? 'is-locked' : ''}" data-slot-id="${slot.id}"
        style="left:${slot.x * 100}%;top:${slot.y * 100}%;width:${slot.width * 100}%;height:${slot.height * 100}%;z-index:${slot.z_index};opacity:${slot.opacity};border-width:${slot.border_width}px;border-color:${escapeHtml(slot.border)};background:${escapeHtml(slot.background)}">
        ${preview ? `<img src="${preview}" alt="" draggable="false" />` : '<div class="slot-texture"></div>'}
        <div class="slot-type">${slot.type === 'rotation' ? icon('rotate') : icon('camera')}</div>
        <div class="slot-label slot-label-${slot.title_position}"><strong>${escapeHtml(title)}</strong><span>${escapeHtml(sourceText)}</span></div>
        ${slot.locked ? `<span class="slot-lock">${icon('lock')}</span>` : ''}
        ${selected && !slot.locked ? ['n', 'ne', 'e', 'se', 's', 'sw', 'w', 'nw'].map((edge) => `<span class="resize-handle resize-${edge}" data-resize="${edge}"></span>`).join('') : ''}
      </div>`;
    }
    inspectorHtml(selected) {
        if (!selected.length) {
            return `<div class="pane-heading"><div><h2>Inspector</h2><p>Select a tile to edit it</p></div></div>
        <div class="inspector-empty">${icon('layout')}<p>Tile geometry, camera source, crop mode, labels, and rotation settings appear here.</p></div>`;
        }
        if (selected.length > 1) {
            return `<div class="pane-heading"><div><h2>${selected.length} tiles selected</h2><p>Batch alignment and distribution</p></div></div>
        <div class="inspector-section"><label>Alignment</label><div class="button-grid two">
          <button class="button button-ghost" data-action="align-left">Align left</button><button class="button button-ghost" data-action="align-top">Align top</button>
          <button class="button button-ghost" data-action="distribute-h">Distribute H</button><button class="button button-ghost" data-action="distribute-v">Distribute V</button>
        </div></div>
        <div class="inspector-section"><div class="button-grid two"><button class="button button-ghost" data-action="duplicate">${icon('copy')} Duplicate</button><button class="button button-danger-subtle" data-action="delete">${icon('trash')} Delete</button></div></div>`;
        }
        const slot = selected[0];
        return `<div class="pane-heading"><div><h2>Tile inspector</h2><p>${escapeHtml(slot.name)}</p></div><button class="icon-button" data-action="lock" title="${slot.locked ? 'Unlock' : 'Lock'} tile">${icon(slot.locked ? 'unlock' : 'lock')}</button></div>
      <div class="inspector-section">
        <label class="field-label">Tile type</label>
        <select class="select" data-field="type">
          ${['fixed', 'rotation', 'manual', 'empty'].map((type) => `<option value="${type}" ${slot.type === type ? 'selected' : ''}>${type[0].toUpperCase() + type.slice(1)}</option>`).join('')}
        </select>
      </div>
      ${slot.type === 'rotation' ? this.rotationInspector(slot) : this.cameraInspector(slot)}
      <div class="inspector-section">
        <div class="section-label">Geometry</div>
        <div class="geometry-grid">
          ${this.numberField('X', 'x', slot.x * 100)}${this.numberField('Y', 'y', slot.y * 100)}
          ${this.numberField('W', 'width', slot.width * 100)}${this.numberField('H', 'height', slot.height * 100)}
        </div>
        <div class="coordinate-readout">${percent(slot.x)}, ${percent(slot.y)} · ${percent(slot.width)} × ${percent(slot.height)}</div>
      </div>
      <div class="inspector-section">
        <label class="field-label">Aspect behavior</label>
        <select class="select" data-field="aspect_mode">
          ${[['cover', 'Cover — fill and crop'], ['contain', 'Contain — fit entire image'], ['stretch', 'Stretch — fill without preserving ratio'], ['native', 'Native — original size where supported']].map(([mode, label]) => `<option value="${mode}" ${slot.aspect_mode === mode ? 'selected' : ''}>${label}</option>`).join('')}
        </select>
        <label class="field-label">Label</label><input class="input" data-field="label" value="${escapeHtml(slot.label ?? '')}" />
        <label class="field-label">Title position</label>
        <select class="select" data-field="title_position">
          ${['top-left', 'top-right', 'bottom-left', 'bottom-right', 'none'].map((position) => `<option value="${position}" ${slot.title_position === position ? 'selected' : ''}>${position.replace('-', ' ')}</option>`).join('')}
        </select>
      </div>
      <div class="inspector-section">
        <div class="button-grid two">
          <button class="button button-ghost" data-action="refresh-preview">${icon('refresh')} Preview</button>
          <button class="button button-ghost" data-action="duplicate">${icon('copy')} Duplicate</button>
          <button class="button button-ghost" data-action="lock">${icon(slot.locked ? 'unlock' : 'lock')} ${slot.locked ? 'Unlock' : 'Lock'}</button>
          <button class="button button-danger-subtle" data-action="delete">${icon('trash')} Delete</button>
        </div>
      </div>`;
    }
    cameraInspector(slot) {
        return `<div class="inspector-section"><label class="field-label">Camera</label><select class="select" data-field="camera_id">
      <option value="">Select camera…</option>${this.cameras.map((camera) => `<option value="${camera.id}" ${(slot.selected_camera_id ?? slot.camera_id) === camera.id ? 'selected' : ''}>${escapeHtml(camera.name)}</option>`).join('')}
      </select><label class="field-label">Stream selection</label><select class="select" data-field="stream_selection"><option value="automatic" ${slot.stream_selection === 'automatic' ? 'selected' : ''}>Automatic for tile size</option><option value="manual" ${slot.stream_selection === 'manual' ? 'selected' : ''}>Manual profile</option></select></div>`;
    }
    rotationInspector(slot) {
        return `<div class="inspector-section"><label class="field-label">Rotation group</label><select class="select" data-field="rotation_group_id"><option value="">Select group…</option>${this.groups.map((group) => `<option value="${group.id}" ${slot.rotation_group_id === group.id ? 'selected' : ''}>${escapeHtml(group.name)} · ${group.interval_seconds}s</option>`).join('')}</select></div>`;
    }
    numberField(label, field, value) {
        return `<label><span>${label}</span><input type="number" min="0" max="100" step="0.1" value="${value.toFixed(1)}" data-geometry="${field}" /><em>%</em></label>`;
    }
    attachEvents() {
        this.host.querySelectorAll('[data-action]').forEach((button) => {
            button.addEventListener('click', () => void this.action(button.dataset.action ?? ''));
        });
        const search = this.host.querySelector('[data-camera-search]');
        search?.addEventListener('input', () => {
            const value = search.value.trim().toLowerCase();
            const list = this.host.querySelector('.camera-library-list');
            if (list)
                list.innerHTML = this.cameraLibraryHtml(this.cameras.filter((camera) => `${camera.name} ${camera.location ?? ''} ${camera.tags.join(' ')}`.toLowerCase().includes(value)));
            this.attachLibraryDragEvents();
        });
        this.attachLibraryDragEvents();
        const canvas = this.host.querySelector('.layout-canvas');
        if (canvas) {
            canvas.addEventListener('dragover', (event) => { event.preventDefault(); if (event.dataTransfer)
                event.dataTransfer.dropEffect = 'copy'; });
            canvas.addEventListener('drop', (event) => {
                event.preventDefault();
                const id = event.dataTransfer?.getData('application/x-mosaivue-camera');
                if (!id)
                    return;
                const rect = canvas.getBoundingClientRect();
                this.addCamera(id, (event.clientX - rect.left) / rect.width, (event.clientY - rect.top) / rect.height);
            });
            canvas.addEventListener('pointerdown', (event) => this.pointerDown(event));
            canvas.addEventListener('click', (event) => {
                if (event.target.closest('.canvas-slot'))
                    return;
                if (this.selectedCameraId) {
                    const rect = canvas.getBoundingClientRect();
                    const cameraId = this.selectedCameraId;
                    this.selectedCameraId = null;
                    this.addCamera(cameraId, (event.clientX - rect.left) / rect.width, (event.clientY - rect.top) / rect.height);
                }
                else {
                    this.selected.clear();
                    this.render();
                }
            });
        }
        this.host.querySelectorAll('[data-template]').forEach((button) => button.addEventListener('click', () => this.applyTemplate(button.dataset.template ?? '')));
        this.host.querySelectorAll('[data-field]').forEach((input) => input.addEventListener('change', () => this.updateField(input)));
        this.host.querySelectorAll('[data-geometry]').forEach((input) => input.addEventListener('change', () => this.updateGeometry(input)));
    }
    attachLibraryDragEvents() {
        this.host.querySelectorAll('.camera-library-item').forEach((item) => {
            item.addEventListener('dragstart', (event) => {
                event.dataTransfer?.setData('application/x-mosaivue-camera', item.dataset.cameraId ?? '');
                if (event.dataTransfer)
                    event.dataTransfer.effectAllowed = 'copy';
            });
            item.addEventListener('click', () => {
                const id = item.dataset.cameraId ?? '';
                this.selectedCameraId = this.selectedCameraId === id ? null : id;
                this.render();
            });
        });
    }
    pointerDown(event) {
        const element = event.target.closest('.canvas-slot');
        if (!element)
            return;
        const slot = this.data.slots.find((item) => item.id === element.dataset.slotId);
        if (!slot)
            return;
        if (this.selectedCameraId && !event.target.closest('[data-resize]')) {
            const camera = this.cameras.find((item) => item.id === this.selectedCameraId);
            if (camera) {
                slot.camera_id = camera.id;
                slot.selected_camera_id = null;
                slot.rotation_group_id = null;
                slot.type = 'fixed';
                slot.name = camera.name;
                slot.label = camera.name;
                this.selectedCameraId = null;
                this.selected = new Set([slot.id]);
                this.recordHistory();
                this.render();
            }
            return;
        }
        if (!event.shiftKey && !this.selected.has(slot.id))
            this.selected.clear();
        this.selected.add(slot.id);
        if (slot.locked) {
            this.render();
            return;
        }
        event.preventDefault();
        element.setPointerCapture(event.pointerId);
        const canvas = this.host.querySelector('.layout-canvas');
        const rect = canvas.getBoundingClientRect();
        const startX = event.clientX;
        const startY = event.clientY;
        const resize = event.target.closest('[data-resize]')?.dataset.resize ?? '';
        const originals = new Map(this.data.slots.filter((item) => this.selected.has(item.id)).map((item) => [item.id, cloneData(item)]));
        let changed = false;
        const onMove = (move) => {
            const dx = (move.clientX - startX) / rect.width;
            const dy = (move.clientY - startY) / rect.height;
            changed ||= Math.abs(dx) > 0.001 || Math.abs(dy) > 0.001;
            for (const current of this.data.slots.filter((item) => this.selected.has(item.id))) {
                const original = originals.get(current.id);
                if (resize && current.id === slot.id) {
                    let left = original.x;
                    let top = original.y;
                    let right = original.x + original.width;
                    let bottom = original.y + original.height;
                    if (resize.includes('w'))
                        left = clamp(this.snapCoordinate(original.x + dx, 'x'), 0, right - 0.03);
                    if (resize.includes('e'))
                        right = clamp(this.snapCoordinate(right + dx, 'x'), left + 0.03, 1);
                    if (resize.includes('n'))
                        top = clamp(this.snapCoordinate(original.y + dy, 'y'), 0, bottom - 0.03);
                    if (resize.includes('s'))
                        bottom = clamp(this.snapCoordinate(bottom + dy, 'y'), top + 0.03, 1);
                    current.x = clamp(left, 0, right - 0.03);
                    current.y = clamp(top, 0, bottom - 0.03);
                    current.width = right - current.x;
                    current.height = bottom - current.y;
                }
                else if (!resize) {
                    current.x = this.snapPosition(clamp(original.x + dx, 0, 1 - current.width), current.width, 'x', current.id);
                    current.y = this.snapPosition(clamp(original.y + dy, 0, 1 - current.height), current.height, 'y', current.id);
                }
                this.updateSlotStyle(current);
            }
        };
        const onEnd = () => {
            element.removeEventListener('pointermove', onMove);
            element.removeEventListener('pointerup', onEnd);
            element.removeEventListener('pointercancel', onEnd);
            if (changed)
                this.recordHistory();
            this.render();
        };
        element.addEventListener('pointermove', onMove);
        element.addEventListener('pointerup', onEnd);
        element.addEventListener('pointercancel', onEnd);
        element.classList.add('is-selected');
    }
    updateSlotStyle(slot) {
        const element = this.host.querySelector(`[data-slot-id="${slot.id}"]`);
        if (!element)
            return;
        element.style.left = `${slot.x * 100}%`;
        element.style.top = `${slot.y * 100}%`;
        element.style.width = `${slot.width * 100}%`;
        element.style.height = `${slot.height * 100}%`;
    }
    snapCoordinate(value, axis) {
        if (!this.gridEnabled)
            return value;
        const count = axis === 'x' ? this.data.grid_columns : this.data.grid_rows;
        return Math.round(value * count) / count;
    }
    snapPosition(value, size, axis, id) {
        let result = value;
        const threshold = 0.012;
        const count = axis === 'x' ? this.data.grid_columns : this.data.grid_rows;
        if (this.gridEnabled)
            result = Math.round(result * count) / count;
        const edges = [0, 1 - size];
        for (const slot of this.data.slots) {
            if (slot.id === id || this.selected.has(slot.id))
                continue;
            const start = axis === 'x' ? slot.x : slot.y;
            const end = start + (axis === 'x' ? slot.width : slot.height);
            edges.push(start, end, start - size, end - size);
        }
        for (const edge of edges)
            if (Math.abs(result - edge) < threshold)
                result = edge;
        return clamp(result, 0, 1 - size);
    }
    addCamera(cameraId, x, y) {
        const camera = this.cameras.find((item) => item.id === cameraId);
        if (!camera)
            return;
        const slot = defaultSlot(camera, x - 0.15, y - 0.15);
        this.data.slots.push(slot);
        this.selected = new Set([slot.id]);
        this.recordHistory();
        this.render();
    }
    applyTemplate(template) {
        const count = Number(template);
        if (!Number.isInteger(count) || count < 2 || count > 10)
            return;
        if (this.data.slots.length > count && !confirm(`This template has ${count} tiles. Remove ${this.data.slots.length - count} extra tiles?`))
            return;
        const geometry = templateGeometry(count);
        const existing = this.data.slots;
        const used = new Set(existing.map((slot) => slot.camera_id).filter(Boolean));
        const available = this.cameras.filter((camera) => camera.enabled && !used.has(camera.id));
        this.data.slots = geometry.map(([x, y, width, height], index) => {
            const prior = existing[index];
            if (prior)
                return { ...prior, x, y, width, height };
            const camera = available.shift();
            if (camera)
                return { ...defaultSlot(camera, x, y), x, y, width, height };
            return { ...defaultSlot({ id: '', name: `Slot ${index + 1}` }, x, y), x, y, width, height, type: 'empty', camera_id: null };
        });
        this.selected = new Set([this.data.slots[0].id]);
        this.recordHistory();
        this.render();
    }
    updateField(input) {
        const slot = this.data.slots.find((item) => this.selected.has(item.id));
        if (!slot)
            return;
        const field = input.dataset.field;
        const value = input.value;
        if (field === 'camera_id') {
            slot.camera_id = value || null;
            slot.selected_camera_id = null;
            const camera = this.cameras.find((item) => item.id === value);
            if (camera) {
                slot.name = camera.name;
                slot.label = camera.name;
            }
        }
        else if (field === 'rotation_group_id') {
            slot.rotation_group_id = value || null;
        }
        else {
            slot[field] = value;
            if (field === 'type') {
                if (value === 'rotation') {
                    slot.camera_id = null;
                    slot.rotation_group_id ||= this.groups[0]?.id ?? null;
                }
                if (value === 'fixed') {
                    slot.rotation_group_id = null;
                    slot.camera_id ||= this.cameras[0]?.id ?? null;
                }
            }
        }
        this.recordHistory();
        this.render();
    }
    updateGeometry(input) {
        const slot = this.data.slots.find((item) => this.selected.has(item.id));
        if (!slot)
            return;
        const field = input.dataset.geometry;
        const value = clamp(Number.parseFloat(input.value) / 100, 0, 1);
        slot[field] = value;
        slot.width = clamp(slot.width, 0.01, 1 - slot.x);
        slot.height = clamp(slot.height, 0.01, 1 - slot.y);
        this.recordHistory();
        this.render();
    }
    async action(name) {
        switch (name) {
            case 'undo':
                this.undo();
                break;
            case 'redo':
                this.redo();
                break;
            case 'toggle-grid':
                this.gridEnabled = !this.gridEnabled;
                this.render();
                break;
            case 'toggle-previews':
                this.showPreviews = !this.showPreviews;
                if (this.showPreviews)
                    await this.refreshAllPreviews();
                else
                    this.clearPreviews();
                this.render();
                break;
            case 'save':
                await this.save(false);
                break;
            case 'save-apply':
                await this.save(true);
                break;
            case 'revert':
                await this.revert();
                break;
            case 'delete':
                this.deleteSelected();
                break;
            case 'duplicate':
                this.duplicateSelected();
                break;
            case 'lock':
                this.toggleLock();
                break;
            case 'refresh-preview':
                await this.refreshSelectedPreview();
                this.render();
                break;
            case 'align-left':
                this.align('x');
                break;
            case 'align-top':
                this.align('y');
                break;
            case 'distribute-h':
                this.distribute('x');
                break;
            case 'distribute-v':
                this.distribute('y');
                break;
        }
    }
    async save(apply) {
        try {
            const updated = await api(`/layouts/${this.layout.id}`, {
                method: 'PUT',
                body: JSON.stringify({ data: this.data, status: 'draft' }),
            });
            this.layout = updated;
            this.data = cloneData(updated.revision.data);
            this.history = [];
            this.historyIndex = -1;
            this.recordHistory();
            if (apply) {
                await api(`/layouts/${this.layout.id}/activate`, { method: 'POST' });
                this.layout.active = true;
                toast('Layout saved and applied to the display', 'success');
            }
            else {
                toast('Draft saved', 'success');
            }
            this.onSaved?.(this.layout);
            this.render();
        }
        catch (error) {
            toast(error instanceof Error ? error.message : 'Unable to save layout', 'error');
        }
    }
    async revert() {
        try {
            this.layout = await api(`/layouts/${this.layout.id}`);
            this.data = cloneData(this.layout.revision.data);
            this.selected.clear();
            this.history = [];
            this.historyIndex = -1;
            this.recordHistory();
            this.render();
            toast('Reverted to the saved revision', 'info');
        }
        catch (error) {
            toast(error instanceof Error ? error.message : 'Unable to revert', 'error');
        }
    }
    deleteSelected() {
        if (!this.selected.size)
            return;
        this.data.slots = this.data.slots.filter((slot) => !this.selected.has(slot.id));
        this.selected.clear();
        this.recordHistory();
        this.render();
    }
    duplicateSelected() {
        const copies = this.data.slots.filter((slot) => this.selected.has(slot.id)).map((slot) => ({
            ...cloneData(slot), id: newId(), name: `${slot.name} copy`, x: clamp(slot.x + 0.02, 0, 1 - slot.width), y: clamp(slot.y + 0.02, 0, 1 - slot.height), locked: false,
        }));
        this.data.slots.push(...copies);
        this.selected = new Set(copies.map((slot) => slot.id));
        this.recordHistory();
        this.render();
    }
    toggleLock() {
        for (const slot of this.data.slots.filter((item) => this.selected.has(item.id)))
            slot.locked = !slot.locked;
        this.recordHistory();
        this.render();
    }
    align(axis) {
        const slots = this.data.slots.filter((slot) => this.selected.has(slot.id));
        if (slots.length < 2)
            return;
        const value = Math.min(...slots.map((slot) => slot[axis]));
        slots.forEach((slot) => { slot[axis] = value; });
        this.recordHistory();
        this.render();
    }
    distribute(axis) {
        const slots = this.data.slots.filter((slot) => this.selected.has(slot.id)).sort((a, b) => a[axis] - b[axis]);
        if (slots.length < 3)
            return;
        const first = slots[0];
        const last = slots.at(-1);
        const span = last[axis] - first[axis];
        slots.forEach((slot, index) => { slot[axis] = first[axis] + span * (index / (slots.length - 1)); });
        this.recordHistory();
        this.render();
    }
    recordHistory() {
        const snapshot = cloneData(this.data);
        const previous = this.history[this.historyIndex];
        if (previous && JSON.stringify(previous) === JSON.stringify(snapshot))
            return;
        this.history = this.history.slice(0, this.historyIndex + 1);
        this.history.push(snapshot);
        if (this.history.length > 50)
            this.history.shift();
        this.historyIndex = this.history.length - 1;
    }
    undo() {
        if (this.historyIndex <= 0)
            return;
        this.historyIndex -= 1;
        this.data = cloneData(this.history[this.historyIndex]);
        this.selected.clear();
        this.render();
    }
    redo() {
        if (this.historyIndex >= this.history.length - 1)
            return;
        this.historyIndex += 1;
        this.data = cloneData(this.history[this.historyIndex]);
        this.selected.clear();
        this.render();
    }
    onKeyDown(event) {
        const target = event.target;
        if (['INPUT', 'SELECT', 'TEXTAREA'].includes(target.tagName))
            return;
        const meta = event.ctrlKey || event.metaKey;
        if (meta && event.key.toLowerCase() === 'z') {
            event.preventDefault();
            event.shiftKey ? this.redo() : this.undo();
            return;
        }
        if (meta && event.key.toLowerCase() === 'y') {
            event.preventDefault();
            this.redo();
            return;
        }
        if (meta && event.key.toLowerCase() === 'c') {
            this.clipboard = this.data.slots.filter((slot) => this.selected.has(slot.id)).map(cloneData);
            return;
        }
        if (meta && event.key.toLowerCase() === 'v') {
            const copies = this.clipboard.map((slot) => ({ ...cloneData(slot), id: newId(), x: clamp(slot.x + .02, 0, 1 - slot.width), y: clamp(slot.y + .02, 0, 1 - slot.height) }));
            this.data.slots.push(...copies);
            this.selected = new Set(copies.map((slot) => slot.id));
            this.recordHistory();
            this.render();
            return;
        }
        if (event.key === 'Delete' || event.key === 'Backspace') {
            event.preventDefault();
            this.deleteSelected();
            return;
        }
        if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key) && this.selected.size) {
            event.preventDefault();
            const step = event.shiftKey ? .01 : .001;
            for (const slot of this.data.slots.filter((item) => this.selected.has(item.id) && !item.locked)) {
                if (event.key === 'ArrowLeft')
                    slot.x = clamp(slot.x - step, 0, 1 - slot.width);
                if (event.key === 'ArrowRight')
                    slot.x = clamp(slot.x + step, 0, 1 - slot.width);
                if (event.key === 'ArrowUp')
                    slot.y = clamp(slot.y - step, 0, 1 - slot.height);
                if (event.key === 'ArrowDown')
                    slot.y = clamp(slot.y + step, 0, 1 - slot.height);
            }
            this.recordHistory();
            this.render();
        }
    }
    async refreshSelectedPreview() {
        const slot = this.data.slots.find((item) => this.selected.has(item.id));
        if (!slot)
            return;
        const cameraId = slot.selected_camera_id ?? slot.camera_id;
        if (!cameraId)
            return;
        await this.loadPreview(slot.id, cameraId);
    }
    async refreshAllPreviews() {
        await Promise.allSettled(this.data.slots.map(async (slot) => {
            const cameraId = slot.selected_camera_id ?? slot.camera_id;
            if (cameraId)
                await this.loadPreview(slot.id, cameraId);
        }));
    }
    async loadPreview(slotId, cameraId) {
        try {
            const blob = await api(`/cameras/${cameraId}/preview?width=640`);
            const old = this.previewUrls.get(slotId);
            if (old)
                URL.revokeObjectURL(old);
            this.previewUrls.set(slotId, URL.createObjectURL(blob));
        }
        catch (error) {
            toast(error instanceof Error ? error.message : 'Preview unavailable', 'warning');
        }
    }
    clearPreviews() {
        for (const url of this.previewUrls.values())
            URL.revokeObjectURL(url);
        this.previewUrls.clear();
    }
}
//# sourceMappingURL=editor.js.map