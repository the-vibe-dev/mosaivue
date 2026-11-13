import { api } from './api.js';
import { featureSupport, layoutDisplayState } from './display-state.js';
import { newId } from './ids.js';
import { setGeometry } from './forms.js';
import { setNavigationGuard } from './router.js';
import { gridGeometry, templateGeometry } from './templates.js';
import type { Camera, Layout, LayoutApplyResult, LayoutData, RendererStatus, RotationGroup, Slot } from './types.js';
import { escapeHtml, icon, toast } from './ui.js';

function cloneData<T>(value: T): T {
  return structuredClone(value);
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function percent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function defaultSlot(camera: Camera, x = 0.05, y = 0.05): Slot {
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
  private data: LayoutData;
  private selected = new Set<string>();
  private selectedCameraId: string | null = null;
  private history: LayoutData[] = [];
  private historyIndex = -1;
  private gridEnabled = true;
  private showPreviews = false;
  private previewUrls = new Map<string, string>();
  private clipboard: Slot[] = [];
  private keyHandler = (event: KeyboardEvent) => this.onKeyDown(event);
  private resizeObserver?: ResizeObserver;
  private savedData = '';
  private busy = false;
  private destroyed = false;
  private saveError = '';
  private mobilePane: 'library' | 'inspector' | null = null;
  private beforeUnloadHandler = (event: BeforeUnloadEvent): void => {
    if (!this.isDirty()) return;
    event.preventDefault();
    event.returnValue = '';
  };

  constructor(
    private host: HTMLElement,
    private layout: Layout,
    private cameras: Camera[],
    private groups: RotationGroup[],
    private onSaved?: (layout: Layout) => void,
    private rendererStatus?: RendererStatus | null,
  ) {
    this.data = cloneData(layout.revision?.data ?? {
      schema_version: 1,
      slots: [],
      background: '#05080c',
      output_width: 1920,
      output_height: 1080,
      grid_columns: 12,
      grid_rows: 12,
    });
    this.savedData = JSON.stringify(this.data);
    this.recordHistory();
  }

  mount(): void {
    document.addEventListener('keydown', this.keyHandler);
    window.addEventListener('beforeunload', this.beforeUnloadHandler);
    setNavigationGuard(() => !this.isDirty() || confirm('Discard unsaved layout changes?'));
    this.render();
  }

  destroy(): void {
    this.destroyed = true;
    document.removeEventListener('keydown', this.keyHandler);
    window.removeEventListener('beforeunload', this.beforeUnloadHandler);
    setNavigationGuard(null);
    this.resizeObserver?.disconnect();
    for (const url of this.previewUrls.values()) URL.revokeObjectURL(url);
  }

  private render(): void {
    if (this.destroyed) return;
    const selectedSlots = this.data.slots.filter((slot) => this.selected.has(slot.id));
    const outputWidth = this.data.output_width ?? 1920;
    const outputHeight = this.data.output_height ?? 1080;
    const ratio = `${outputWidth} / ${outputHeight}`;
    const display = layoutDisplayState(this.layout, this.rendererStatus);
    this.host.innerHTML = `
      <section class="editor-shell ${this.mobilePane === 'library' ? 'library-open' : this.mobilePane === 'inspector' ? 'inspector-open' : ''}">
        <header class="editor-toolbar">
          <div class="editor-title-block">
            <a class="icon-button" href="/layouts" data-route aria-label="Back to layouts">${icon('chevron', 'icon-back')}</a>
            <div><strong>${escapeHtml(this.layout.name)}</strong><span>Revision ${this.layout.current_revision}${this.isDirty() ? ' · Unsaved changes' : ' · Saved'}</span></div>
          </div>
          <div class="toolbar-cluster editor-pane-controls">
            <button class="button button-ghost button-small" data-action="toggle-library" aria-expanded="${this.mobilePane === 'library'}" aria-controls="editor-camera-library">${icon('camera')} Cameras</button>
            <button class="button button-ghost button-small" data-action="toggle-inspector" aria-expanded="${this.mobilePane === 'inspector'}" aria-controls="editor-tile-inspector">${icon('edit')} Tile</button>
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
            <button class="button button-primary" data-action="save-apply">${icon('play')} ${this.isDirty() ? 'Save & apply' : display.action}</button>
          </div>
        </header>
        <div class="editor-display-state display-notice display-notice-${display.tone}" role="status" data-display-state="${display.kind}">
          <div><strong>${escapeHtml(display.label)}</strong><p>${escapeHtml(display.detail)} Save draft stores edits without changing the wall.</p>${this.saveError ? `<p class="save-error" role="alert">${escapeHtml(this.saveError)}</p>` : ''}</div>
          <button class="button button-ghost button-small" data-action="refresh-display">${icon('refresh')} Refresh status</button>
        </div>
        <div class="editor-workspace">
          <aside class="editor-library" id="editor-camera-library" aria-label="Camera library">
            <div class="pane-heading"><div><h2>Cameras</h2><p>Click a camera, then click the display</p></div><button class="icon-button editor-pane-close" data-action="close-pane" aria-label="Close camera library">${icon('close')}</button></div>
            <label class="search-field">${icon('search')}<input type="search" placeholder="Filter cameras" data-camera-search /></label>
            <div class="camera-library-list">
              ${this.cameraLibraryHtml(this.cameras)}
            </div>
            <div class="pane-section">
              <div class="pane-heading compact"><div><h2>Templates</h2><p>Featured camera</p></div></div>
              <div class="template-grid">
                ${Array.from({ length: 9 }, (_, index) => {
                  const count = index + 2;
                  const tiles = templateGeometry(count).map(([x, y, width, height]) => `<i style="left:${x * 100}%;top:${y * 100}%;width:${width * 100}%;height:${height * 100}%"></i>`).join('');
                  return `<button data-template="${count}" title="Featured layout for ${count} cameras"><span class="template-preview template-featured">${tiles}</span><small>${count} cameras</small></button>`;
                }).join('')}
              </div>
              <div class="pane-heading compact"><div><h2>Even grids</h2><p>Equal-sized camera tiles</p></div></div>
              <div class="template-grid">
                ${[2, 3, 4].map((size) => {
                  const tiles = gridGeometry(size).map(([x, y, width, height]) => `<i style="left:${x * 100}%;top:${y * 100}%;width:${width * 100}%;height:${height * 100}%"></i>`).join('');
                  return `<button data-template="grid-${size}" title="${size} by ${size} equal grid"><span class="template-preview template-featured">${tiles}</span><small>${size} × ${size} grid</small></button>`;
                }).join('')}
              </div>
            </div>
          </aside>
          <main class="editor-stage">
            <div class="stage-ruler"><span>${outputWidth} × ${outputHeight}</span><span>${this.data.slots.length} slot${this.data.slots.length === 1 ? '' : 's'}</span></div>
            <p class="editor-preview-note">Editing preview. ${featureSupport(this.rendererStatus?.capabilities, 'labels') === true ? 'Use stream health to check playback.' : 'Camera labels are for editing; label playback is unsupported or not reported by the renderer.'} <a href="/renderer" data-route>Renderer capabilities</a></p>
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
          <aside class="editor-inspector" id="editor-tile-inspector" aria-label="Tile inspector">
            <div class="editor-pane-close-row"><button class="button button-ghost button-small" data-action="close-pane">${icon('close')} Close inspector</button></div>
            ${this.inspectorHtml(selectedSlots)}
          </aside>
        </div>
      </section>`;
    this.attachEvents();
  }

  private cameraLibraryHtml(cameras: Camera[]): string {
    if (!cameras.length) return '<div class="library-empty">No enabled cameras yet.</div>';
    return cameras.map((camera) => `
      <button class="camera-library-item ${this.selectedCameraId === camera.id ? 'is-selected' : ''}" draggable="true" data-camera-id="${camera.id}" aria-pressed="${this.selectedCameraId === camera.id}">
        <span class="camera-thumb">${icon('camera')}</span>
        <span class="camera-library-copy"><strong>${escapeHtml(camera.name)}</strong><small>${escapeHtml(camera.location ?? camera.host ?? 'RTSP camera')}</small></span>
        <span class="camera-state ${camera.enabled ? 'is-online' : 'is-disabled'}"></span>
      </button>`).join('');
  }

  private slotHtml(slot: Slot): string {
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
        ${selected && !slot.locked ? ['n','ne','e','se','s','sw','w','nw'].map((edge) => `<span class="resize-handle resize-${edge}" data-resize="${edge}"></span>`).join('') : ''}
      </div>`;
  }

  private inspectorHtml(selected: Slot[]): string {
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
    const slot = selected[0]!;
    return `<div class="pane-heading"><div><h2>Tile inspector</h2><p>${escapeHtml(slot.name)}</p></div><button class="icon-button" data-action="lock" title="${slot.locked ? 'Unlock' : 'Lock'} tile">${icon(slot.locked ? 'unlock' : 'lock')}</button></div>
      <div class="inspector-section">
        <label class="field-label">Tile type</label>
        <select class="select" data-field="type">
          ${['fixed','rotation','manual','empty'].map((type) => `<option value="${type}" ${slot.type === type ? 'selected' : ''}>${type[0]!.toUpperCase() + type.slice(1)}</option>`).join('')}
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
        ${slot.pixel_override ? `<p class="form-help">Fixed pixel placement overrides this canvas on the display. Moving or resizing this tile replaces those fixed pixels with the canvas geometry.</p><button class="button button-ghost button-small" data-action="use-canvas-geometry" ${slot.locked ? 'disabled' : ''}>Use canvas placement</button>` : ''}
      </div>
      <div class="inspector-section">
        <label class="field-label">Aspect behavior</label>
        <select class="select" data-field="aspect_mode">
          ${[['cover','Cover — fill and crop'],['contain','Contain — fit entire image'],['stretch','Stretch — fill without preserving ratio'],['native',featureSupport(this.rendererStatus?.capabilities, 'native_size') === true ? 'Native — original size' : 'Native — unavailable on this renderer']].map(([mode,label]) => `<option value="${mode}" ${slot.aspect_mode === mode ? 'selected' : ''} ${mode === 'native' && featureSupport(this.rendererStatus?.capabilities, 'native_size') !== true ? 'disabled' : ''}>${label}</option>`).join('')}
        </select>
        ${slot.aspect_mode === 'native' && featureSupport(this.rendererStatus?.capabilities, 'native_size') !== true ? '<p class="form-help">This saved native setting is retained for compatibility. Choose a supported aspect mode for predictable playback.</p>' : ''}
        <label class="field-label">Label</label><input class="input" data-field="label" value="${escapeHtml(slot.label ?? '')}" ${featureSupport(this.rendererStatus?.capabilities, 'labels') === true ? '' : 'disabled'} />
        <label class="field-label">Title position</label>
        <select class="select" data-field="title_position" ${featureSupport(this.rendererStatus?.capabilities, 'labels') === true ? '' : 'disabled'}>
          ${['top-left','top-right','bottom-left','bottom-right','none'].map((position) => `<option value="${position}" ${slot.title_position === position ? 'selected' : ''}>${position.replace('-', ' ')}</option>`).join('')}
        </select>
        ${featureSupport(this.rendererStatus?.capabilities, 'labels') === true ? '' : '<p class="form-help">Saved labels are preserved. Label playback is unsupported or not reported by the current renderer.</p>'}
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

  private cameraInspector(slot: Slot): string {
    const camera = this.cameras.find((item) => item.id === (slot.selected_camera_id ?? slot.camera_id));
    return `<div class="inspector-section"><label class="field-label">Camera</label><select class="select" data-field="camera_id">
      <option value="">Select camera…</option>${this.cameras.map((camera) => `<option value="${camera.id}" ${(slot.selected_camera_id ?? slot.camera_id) === camera.id ? 'selected' : ''}>${escapeHtml(camera.name)}</option>`).join('')}
      </select><label class="field-label">Stream selection</label><select class="select" data-field="stream_selection"><option value="automatic" ${slot.stream_selection === 'automatic' ? 'selected' : ''}>Automatic for tile size</option><option value="manual" ${slot.stream_selection === 'manual' ? 'selected' : ''}>Manual profile</option></select>
      ${slot.stream_selection === 'manual' ? `<label class="field-label">Stream profile</label><select class="select" data-field="stream_profile_id" aria-label="Stream profile"><option value="">Select profile…</option>${camera?.stream_profiles.map((profile) => `<option value="${profile.id}" ${slot.stream_profile_id === profile.id ? 'selected' : ''}>${escapeHtml(profile.name)}${profile.width && profile.height ? ` · ${profile.width} × ${profile.height}` : ''}</option>`).join('') ?? ''}</select>` : ''}</div>`;
  }

  private rotationInspector(slot: Slot): string {
    return `<div class="inspector-section"><label class="field-label">Rotation group</label><select class="select" data-field="rotation_group_id"><option value="">Select group…</option>${this.groups.map((group) => `<option value="${group.id}" ${slot.rotation_group_id === group.id ? 'selected' : ''}>${escapeHtml(group.name)} · ${group.interval_seconds}s</option>`).join('')}</select></div>`;
  }

  private numberField(label: string, field: keyof Slot, value: number): string {
    return `<label><span>${label}</span><input type="number" min="0" max="100" step="0.1" value="${value.toFixed(1)}" data-geometry="${field}" /><em>%</em></label>`;
  }

  private attachEvents(): void {
    this.host.querySelectorAll<HTMLButtonElement>('[data-action]').forEach((button) => {
      button.addEventListener('click', () => void this.action(button.dataset.action ?? ''));
    });
    const search = this.host.querySelector<HTMLInputElement>('[data-camera-search]');
    search?.addEventListener('input', () => {
      const value = search.value.trim().toLowerCase();
      const list = this.host.querySelector<HTMLElement>('.camera-library-list');
      if (list) list.innerHTML = this.cameraLibraryHtml(this.cameras.filter((camera) => `${camera.name} ${camera.location ?? ''} ${camera.tags.join(' ')}`.toLowerCase().includes(value)));
      this.attachLibraryDragEvents();
    });
    this.attachLibraryDragEvents();

    const canvas = this.host.querySelector<HTMLElement>('.layout-canvas');
    if (canvas) {
      canvas.addEventListener('dragover', (event) => { event.preventDefault(); if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy'; });
      canvas.addEventListener('drop', (event) => {
        event.preventDefault();
        const id = event.dataTransfer?.getData('application/x-mosaivue-camera');
        if (!id) return;
        const rect = canvas.getBoundingClientRect();
        this.addCamera(id, (event.clientX - rect.left) / rect.width, (event.clientY - rect.top) / rect.height);
      });
      canvas.addEventListener('pointerdown', (event) => this.pointerDown(event));
      canvas.addEventListener('click', (event) => {
        if ((event.target as HTMLElement).closest('.canvas-slot')) return;
        if (this.selectedCameraId) {
          const rect = canvas.getBoundingClientRect();
          const cameraId = this.selectedCameraId;
          this.selectedCameraId = null;
          this.addCamera(cameraId, (event.clientX - rect.left) / rect.width, (event.clientY - rect.top) / rect.height);
        } else {
          this.selected.clear();
          this.render();
        }
      });
    }
    this.host.querySelectorAll<HTMLButtonElement>('[data-template]').forEach((button) => button.addEventListener('click', () => this.applyTemplate(button.dataset.template ?? '')));
    this.host.querySelectorAll<HTMLInputElement | HTMLSelectElement>('[data-field]').forEach((input) => input.addEventListener('change', () => this.updateField(input)));
    this.host.querySelectorAll<HTMLInputElement>('[data-geometry]').forEach((input) => input.addEventListener('change', () => this.updateGeometry(input)));
    const locked = this.data.slots.find((slot) => this.selected.has(slot.id))?.locked;
    if (this.selected.size === 1 && locked) this.host.querySelectorAll<HTMLInputElement | HTMLSelectElement>('[data-field], [data-geometry]').forEach((input) => { input.disabled = true; });
  }

  private attachLibraryDragEvents(): void {
    this.host.querySelectorAll<HTMLButtonElement>('.camera-library-item').forEach((item) => {
      item.addEventListener('dragstart', (event) => {
        event.dataTransfer?.setData('application/x-mosaivue-camera', item.dataset.cameraId ?? '');
        if (event.dataTransfer) event.dataTransfer.effectAllowed = 'copy';
      });
      item.addEventListener('click', () => {
        const id = item.dataset.cameraId ?? '';
        this.selectedCameraId = this.selectedCameraId === id ? null : id;
        this.mobilePane = null;
        this.render();
      });
    });
  }

  private pointerDown(event: PointerEvent): void {
    if (this.busy || event.button !== 0) return;
    const element = (event.target as HTMLElement).closest<HTMLElement>('.canvas-slot');
    if (!element) return;
    const slot = this.data.slots.find((item) => item.id === element.dataset.slotId);
    if (!slot) return;
    if (this.selectedCameraId && !slot.locked && !(event.target as HTMLElement).closest('[data-resize]')) {
      const camera = this.cameras.find((item) => item.id === this.selectedCameraId);
      if (camera) {
        slot.camera_id = camera.id;
        slot.selected_camera_id = null;
        slot.rotation_group_id = null;
        slot.stream_profile_id = null;
        slot.stream_selection = 'automatic';
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
    if (!event.shiftKey && !this.selected.has(slot.id)) this.selected.clear();
    this.selected.add(slot.id);
    if (slot.locked) { this.render(); return; }
    event.preventDefault();
    element.setPointerCapture(event.pointerId);
    const canvas = this.host.querySelector<HTMLElement>('.layout-canvas')!;
    const rect = canvas.getBoundingClientRect();
    const startX = event.clientX;
    const startY = event.clientY;
    const resize = (event.target as HTMLElement).closest<HTMLElement>('[data-resize]')?.dataset.resize ?? '';
    const originals = new Map(this.data.slots.filter((item) => this.selected.has(item.id)).map((item) => [item.id, cloneData(item)]));
    let changed = false;
    const onMove = (move: PointerEvent) => {
      const dx = (move.clientX - startX) / rect.width;
      const dy = (move.clientY - startY) / rect.height;
      changed ||= Math.abs(dx) > 0.001 || Math.abs(dy) > 0.001;
      if (!changed) return;
      for (const current of this.data.slots.filter((item) => this.selected.has(item.id))) {
        if (current.locked) continue;
        const original = originals.get(current.id)!;
        if (resize && current.id === slot.id) {
          let left = original.x;
          let top = original.y;
          let right = original.x + original.width;
          let bottom = original.y + original.height;
          if (resize.includes('w')) left = clamp(this.snapCoordinate(original.x + dx, 'x'), 0, right - 0.03);
          if (resize.includes('e')) right = clamp(this.snapCoordinate(right + dx, 'x'), left + 0.03, 1);
          if (resize.includes('n')) top = clamp(this.snapCoordinate(original.y + dy, 'y'), 0, bottom - 0.03);
          if (resize.includes('s')) bottom = clamp(this.snapCoordinate(bottom + dy, 'y'), top + 0.03, 1);
          current.x = clamp(left, 0, right - 0.03);
          current.y = clamp(top, 0, bottom - 0.03);
          current.width = right - current.x;
          current.height = bottom - current.y;
        } else if (!resize) {
          current.x = this.snapPosition(clamp(original.x + dx, 0, 1 - current.width), current.width, 'x', current.id);
          current.y = this.snapPosition(clamp(original.y + dy, 0, 1 - current.height), current.height, 'y', current.id);
        }
        if (!resize || current.id === slot.id) current.pixel_override = null;
        this.updateSlotStyle(current);
      }
    };
    const onEnd = () => {
      element.removeEventListener('pointermove', onMove);
      element.removeEventListener('pointerup', onEnd);
      element.removeEventListener('pointercancel', onEnd);
      if (changed) this.recordHistory();
      this.render();
    };
    element.addEventListener('pointermove', onMove);
    element.addEventListener('pointerup', onEnd);
    element.addEventListener('pointercancel', onEnd);
    element.classList.add('is-selected');
  }

  private updateSlotStyle(slot: Slot): void {
    const element = this.host.querySelector<HTMLElement>(`[data-slot-id="${slot.id}"]`);
    if (!element) return;
    element.style.left = `${slot.x * 100}%`;
    element.style.top = `${slot.y * 100}%`;
    element.style.width = `${slot.width * 100}%`;
    element.style.height = `${slot.height * 100}%`;
  }

  private snapCoordinate(value: number, axis: 'x' | 'y'): number {
    if (!this.gridEnabled) return value;
    const count = axis === 'x' ? this.data.grid_columns : this.data.grid_rows;
    return Math.round(value * count) / count;
  }

  private snapPosition(value: number, size: number, axis: 'x' | 'y', id: string): number {
    let result = value;
    const threshold = 0.012;
    const count = axis === 'x' ? this.data.grid_columns : this.data.grid_rows;
    if (this.gridEnabled) result = Math.round(result * count) / count;
    const edges = [0, 1 - size];
    for (const slot of this.data.slots) {
      if (slot.id === id || this.selected.has(slot.id)) continue;
      const start = axis === 'x' ? slot.x : slot.y;
      const end = start + (axis === 'x' ? slot.width : slot.height);
      edges.push(start, end, start - size, end - size);
    }
    for (const edge of edges) if (Math.abs(result - edge) < threshold) result = edge;
    return clamp(result, 0, 1 - size);
  }

  private addCamera(cameraId: string, x: number, y: number): void {
    const camera = this.cameras.find((item) => item.id === cameraId);
    if (!camera) return;
    const slot = defaultSlot(camera, x - 0.15, y - 0.15);
    this.data.slots.push(slot);
    this.selected = new Set([slot.id]);
    this.recordHistory();
    this.render();
  }

  private applyTemplate(template: string): void {
    const grid = /^grid-([234])$/.exec(template);
    const size = Number(grid?.[1]);
    const count = grid ? size * size : Number(template);
    if (!grid && (!Number.isInteger(count) || count < 2 || count > 10)) return;
    const existing = this.data.slots;
    if (existing.some((slot) => slot.locked)) { toast('Unlock tiles before applying a template', 'warning'); return; }
    if (existing.length > count && !confirm(`This template has ${count} tiles. Remove ${existing.length - count} extra tiles?`)) return;
    const geometry = grid ? gridGeometry(size) : templateGeometry(count);
    const used = new Set(existing.map((slot) => slot.camera_id).filter(Boolean));
    const available = this.cameras.filter((camera) => camera.enabled && !used.has(camera.id));
    this.data.slots = geometry.map(([x, y, width, height], index) => {
      const prior = existing[index];
      if (prior) return { ...prior, x, y, width, height, pixel_override: null };
      const camera = available.shift();
      if (camera) return { ...defaultSlot(camera, x, y), x, y, width, height };
      return { ...defaultSlot({ id: '', name: `Slot ${index + 1}` } as Camera, x, y), x, y, width, height, type: 'empty' as const, camera_id: null };
    });
    this.selected = new Set([this.data.slots[0]!.id]);
    this.recordHistory();
    this.render();
  }

  private updateField(input: HTMLInputElement | HTMLSelectElement): void {
    const slot = this.data.slots.find((item) => this.selected.has(item.id));
    if (!slot || slot.locked || this.busy) return;
    const field = input.dataset.field as keyof Slot;
    const value = input.value;
    if (['label', 'title_position'].includes(field) && featureSupport(this.rendererStatus?.capabilities, 'labels') !== true) return;
    if (field === 'aspect_mode' && value === 'native' && featureSupport(this.rendererStatus?.capabilities, 'native_size') !== true) return;
    if (field === 'camera_id') {
      slot.camera_id = value || null;
      if (value && slot.type === 'empty') slot.type = 'fixed';
      slot.selected_camera_id = null;
      slot.stream_profile_id = null;
      slot.stream_selection = 'automatic';
      const camera = this.cameras.find((item) => item.id === value);
      if (camera) { slot.name = camera.name; slot.label = camera.name; }
    } else if (field === 'stream_profile_id') {
      slot.stream_profile_id = value || null;
    } else if (field === 'stream_selection') {
      slot.stream_selection = value as Slot['stream_selection'];
      const camera = this.cameras.find((item) => item.id === (slot.selected_camera_id ?? slot.camera_id));
      slot.stream_profile_id = value === 'manual' ? camera?.stream_profiles[0]?.id ?? null : null;
    } else if (field === 'rotation_group_id') {
      slot.rotation_group_id = value || null;
    } else {
      (slot as unknown as Record<string, unknown>)[field] = value;
      if (field === 'type') {
        slot.stream_profile_id = null; slot.stream_selection = 'automatic'; slot.selected_camera_id = null;
        if (value === 'rotation') { slot.camera_id = null; slot.rotation_group_id ||= this.groups[0]?.id ?? null; }
        if (value === 'fixed' || value === 'manual') { slot.rotation_group_id = null; slot.camera_id ||= this.cameras.find((camera) => camera.enabled)?.id ?? null; }
        if (value === 'empty') { slot.camera_id = null; slot.rotation_group_id = null; }
      }
    }
    this.recordHistory();
    this.render();
  }

  private updateGeometry(input: HTMLInputElement): void {
    const slot = this.data.slots.find((item) => this.selected.has(item.id));
    if (!slot || slot.locked || this.busy) return;
    const field = input.dataset.geometry as 'x' | 'y' | 'width' | 'height';
    Object.assign(slot, setGeometry(slot, field, Number.parseFloat(input.value)));
    this.recordHistory();
    this.render();
  }

  private async action(name: string): Promise<void> {
    if (this.busy) return;
    switch (name) {
      case 'undo': this.undo(); break;
      case 'redo': this.redo(); break;
      case 'toggle-library': this.mobilePane = this.mobilePane === 'library' ? null : 'library'; this.render(); break;
      case 'toggle-inspector': this.mobilePane = this.mobilePane === 'inspector' ? null : 'inspector'; this.render(); break;
      case 'close-pane': this.mobilePane = null; this.render(); break;
      case 'toggle-grid': this.gridEnabled = !this.gridEnabled; this.render(); break;
      case 'toggle-previews':
        this.showPreviews = !this.showPreviews;
        if (this.showPreviews) await this.refreshAllPreviews(); else this.clearPreviews();
        this.render();
        break;
      case 'save': await this.save(false); break;
      case 'save-apply': await this.save(true); break;
      case 'refresh-display': await this.refreshDisplayStatus(); this.render(); break;
      case 'use-canvas-geometry':
        for (const slot of this.data.slots.filter((item) => this.selected.has(item.id) && !item.locked)) slot.pixel_override = null;
        this.recordHistory(); this.render(); break;
      case 'revert': await this.revert(); break;
      case 'delete': this.deleteSelected(); break;
      case 'duplicate': this.duplicateSelected(); break;
      case 'lock': this.toggleLock(); break;
      case 'refresh-preview': await this.refreshSelectedPreview(); this.render(); break;
      case 'align-left': this.align('x'); break;
      case 'align-top': this.align('y'); break;
      case 'distribute-h': this.distribute('x'); break;
      case 'distribute-v': this.distribute('y'); break;
    }
  }

  private async save(apply: boolean): Promise<void> {
    if (this.busy) return;
    this.busy = true;
    this.host.inert = true;
    this.saveError = '';
    let saved = !this.isDirty();
    try {
      if (!saved) {
        const updated = await api<Layout>(`/layouts/${this.layout.id}`, {
          method: 'PUT',
          body: JSON.stringify({ data: this.data, status: 'draft' }),
        });
        this.acceptSavedLayout(updated);
        saved = true;
      }
      if (apply) {
        const result = await api<LayoutApplyResult>(`/layouts/${this.layout.id}/activate`, { method: 'POST' });
        this.acceptSavedLayout(result.layout);
        this.rendererStatus = result.renderer;
        toast(`Revision ${this.layout.current_revision} applied; check stream health for playback`, 'success');
      } else {
        await this.refreshDisplayStatus();
        toast('Draft saved. Apply when you want to update the display.', 'success');
      }
      this.onSaved?.(this.layout);
    } catch (error) {
      const detail = error instanceof Error ? error.message : 'Request failed';
      this.saveError = saved && apply
        ? `Revision ${this.layout.current_revision} is saved, but applying it failed: ${detail}. Retry Apply without saving another revision.`
        : `Changes were not saved: ${detail}`;
      if (saved && apply) await this.refreshDisplayStatus();
      toast(this.saveError, 'error');
    } finally {
      this.busy = false;
      this.host.inert = false;
      this.render();
    }
  }

  private acceptSavedLayout(layout: Layout): void {
    this.layout = layout;
    this.data = cloneData(layout.revision!.data);
    this.savedData = JSON.stringify(this.data);
    this.history = [];
    this.historyIndex = -1;
    this.recordHistory();
  }

  private async refreshDisplayStatus(): Promise<void> {
    try { this.rendererStatus = await api<RendererStatus>('/renderer/status'); }
    catch { this.rendererStatus = null; }
  }

  private async revert(): Promise<void> {
    if (this.isDirty() && !confirm('Discard unsaved layout changes and restore the saved revision?')) return;
    try {
      this.layout = await api<Layout>(`/layouts/${this.layout.id}`);
      this.data = cloneData(this.layout.revision!.data);
      this.savedData = JSON.stringify(this.data);
      this.selected.clear();
      this.history = [];
      this.historyIndex = -1;
      this.recordHistory();
      this.render();
      toast('Reverted to the saved revision', 'info');
    } catch (error) { toast(error instanceof Error ? error.message : 'Unable to revert', 'error'); }
  }

  private deleteSelected(): void {
    if (!this.selected.size) return;
    this.data.slots = this.data.slots.filter((slot) => !this.selected.has(slot.id) || slot.locked);
    this.selected.clear();
    this.recordHistory();
    this.render();
  }

  private duplicateSelected(): void {
    const copies = this.data.slots.filter((slot) => this.selected.has(slot.id)).map((slot) => ({
      ...cloneData(slot), id: newId(), name: `${slot.name} copy`, x: clamp(slot.x + 0.02, 0, 1 - slot.width), y: clamp(slot.y + 0.02, 0, 1 - slot.height), locked: false, pixel_override: null,
    }));
    this.data.slots.push(...copies);
    this.selected = new Set(copies.map((slot) => slot.id));
    this.recordHistory();
    this.render();
  }

  private toggleLock(): void {
    for (const slot of this.data.slots.filter((item) => this.selected.has(item.id))) slot.locked = !slot.locked;
    this.recordHistory();
    this.render();
  }

  private align(axis: 'x' | 'y'): void {
    const slots = this.data.slots.filter((slot) => this.selected.has(slot.id) && !slot.locked);
    if (slots.length < 2) return;
    const value = Math.min(...slots.map((slot) => slot[axis]));
    slots.forEach((slot) => { slot[axis] = value; slot.pixel_override = null; });
    this.recordHistory(); this.render();
  }

  private distribute(axis: 'x' | 'y'): void {
    const slots = this.data.slots.filter((slot) => this.selected.has(slot.id) && !slot.locked).sort((a, b) => a[axis] - b[axis]);
    if (slots.length < 3) return;
    const first = slots[0]!;
    const last = slots.at(-1)!;
    const span = last[axis] - first[axis];
    slots.forEach((slot, index) => { slot[axis] = first[axis] + span * (index / (slots.length - 1)); slot.pixel_override = null; });
    this.recordHistory(); this.render();
  }

  private recordHistory(): void {
    const snapshot = cloneData(this.data);
    const previous = this.history[this.historyIndex];
    if (previous && JSON.stringify(previous) === JSON.stringify(snapshot)) return;
    this.history = this.history.slice(0, this.historyIndex + 1);
    this.history.push(snapshot);
    if (this.history.length > 50) this.history.shift();
    this.historyIndex = this.history.length - 1;
  }

  private undo(): void {
    if (this.historyIndex <= 0) return;
    this.historyIndex -= 1;
    this.data = cloneData(this.history[this.historyIndex]!);
    this.selected.clear(); this.render();
  }

  private redo(): void {
    if (this.historyIndex >= this.history.length - 1) return;
    this.historyIndex += 1;
    this.data = cloneData(this.history[this.historyIndex]!);
    this.selected.clear(); this.render();
  }

  private onKeyDown(event: KeyboardEvent): void {
    if (this.busy || document.querySelector('dialog[open]')) return;
    const target = event.target as HTMLElement;
    if (['INPUT','SELECT','TEXTAREA'].includes(target.tagName)) return;
    const meta = event.ctrlKey || event.metaKey;
    if (meta && event.key.toLowerCase() === 'z') { event.preventDefault(); event.shiftKey ? this.redo() : this.undo(); return; }
    if (meta && event.key.toLowerCase() === 'y') { event.preventDefault(); this.redo(); return; }
    if (meta && event.key.toLowerCase() === 'c') { this.clipboard = this.data.slots.filter((slot) => this.selected.has(slot.id)).map(cloneData); return; }
    if (meta && event.key.toLowerCase() === 'v') {
      const copies = this.clipboard.map((slot) => ({ ...cloneData(slot), id: newId(), x: clamp(slot.x + .02, 0, 1 - slot.width), y: clamp(slot.y + .02, 0, 1 - slot.height), locked: false, pixel_override: null }));
      this.data.slots.push(...copies); this.selected = new Set(copies.map((slot) => slot.id)); this.recordHistory(); this.render(); return;
    }
    if (event.key === 'Delete' || event.key === 'Backspace') { event.preventDefault(); this.deleteSelected(); return; }
    if (['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key) && this.selected.size) {
      event.preventDefault();
      const step = event.shiftKey ? .01 : .001;
      for (const slot of this.data.slots.filter((item) => this.selected.has(item.id) && !item.locked)) {
        if (event.key === 'ArrowLeft') slot.x = clamp(slot.x - step, 0, 1 - slot.width);
        if (event.key === 'ArrowRight') slot.x = clamp(slot.x + step, 0, 1 - slot.width);
        if (event.key === 'ArrowUp') slot.y = clamp(slot.y - step, 0, 1 - slot.height);
        if (event.key === 'ArrowDown') slot.y = clamp(slot.y + step, 0, 1 - slot.height);
        slot.pixel_override = null;
      }
      this.recordHistory(); this.render();
    }
  }

  private async refreshSelectedPreview(): Promise<void> {
    const slot = this.data.slots.find((item) => this.selected.has(item.id));
    if (!slot) return;
    const cameraId = slot.selected_camera_id ?? slot.camera_id;
    if (!cameraId) return;
    await this.loadPreview(slot.id, cameraId);
  }

  private async refreshAllPreviews(): Promise<void> {
    await Promise.allSettled(this.data.slots.map(async (slot) => {
      const cameraId = slot.selected_camera_id ?? slot.camera_id;
      if (cameraId) await this.loadPreview(slot.id, cameraId);
    }));
  }

  private async loadPreview(slotId: string, cameraId: string): Promise<void> {
    try {
      const blob = await api<Blob>(`/cameras/${cameraId}/preview?width=640`);
      if (this.destroyed || !this.data.slots.some((slot) => slot.id === slotId && (slot.selected_camera_id ?? slot.camera_id) === cameraId)) return;
      const old = this.previewUrls.get(slotId);
      if (old) URL.revokeObjectURL(old);
      this.previewUrls.set(slotId, URL.createObjectURL(blob));
    } catch (error) {
      toast(error instanceof Error ? error.message : 'Preview unavailable', 'warning');
    }
  }

  private clearPreviews(): void {
    for (const url of this.previewUrls.values()) URL.revokeObjectURL(url);
    this.previewUrls.clear();
  }

  private isDirty(): boolean {
    return JSON.stringify(this.data) !== this.savedData;
  }
}
