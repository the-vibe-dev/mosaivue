import test from 'node:test';
import assert from 'node:assert/strict';

globalThis.sessionStorage = { getItem: () => null };
globalThis.location = { pathname: '/' };
globalThis.history = { state: {} };
const { LayoutEditor } = await import('../dist/assets/editor.js');
const { layoutDisplayState } = await import('../dist/assets/display-state.js');

const camera = { id: 'camera-B', name: 'Back', stream_profiles: [{ id: 'profile-B' }] };
function editorFor(slots) {
  const data = { schema_version: 1, slots, background: '#000000', output_width: 1920, output_height: 1080, grid_columns: 12, grid_rows: 12 };
  const editor = new LayoutEditor({}, { id: 'layout', current_revision: 1, revision: { data } }, [camera], []);
  editor.render = () => {};
  return editor;
}

test('deleting a mixed selection preserves locked tiles and dirty undo state', () => {
  const editor = editorFor([{ id: 'locked', locked: true }, { id: 'editable', locked: false }]);
  editor.selected = new Set(['locked', 'editable']);
  editor.deleteSelected();
  assert.deepEqual(editor.data.slots.map((slot) => slot.id), ['locked']);
  assert.equal(editor.isDirty(), true);
  editor.undo();
  assert.equal(editor.data.slots.length, 2);
  assert.equal(editor.isDirty(), false);
});

test('changing cameras clears stale selected profile and manual-camera overrides', () => {
  const editor = editorFor([{ id: 'slot', locked: false, camera_id: 'camera-A', selected_camera_id: 'camera-C', stream_profile_id: 'profile-A', stream_selection: 'manual' }]);
  editor.selected = new Set(['slot']);
  editor.updateField({ dataset: { field: 'camera_id' }, value: camera.id });
  assert.equal(editor.data.slots[0].camera_id, camera.id);
  assert.equal(editor.data.slots[0].selected_camera_id, null);
  assert.equal(editor.data.slots[0].stream_profile_id, null);
  assert.equal(editor.data.slots[0].stream_selection, 'automatic');
});

test('manual stream selection selects a real profile belonging to the camera', () => {
  const editor = editorFor([{ id: 'slot', locked: false, camera_id: camera.id, stream_selection: 'automatic' }]);
  editor.selected = new Set(['slot']);
  editor.updateField({ dataset: { field: 'stream_selection' }, value: 'manual' });
  assert.equal(editor.data.slots[0].stream_profile_id, 'profile-B');
  editor.updateField({ dataset: { field: 'stream_selection' }, value: 'automatic' });
  assert.equal(editor.data.slots[0].stream_profile_id, null);
});

test('locked tiles reject property changes and remain fixed during batch alignment', () => {
  const editor = editorFor([{ id: 'locked', locked: true, x: 0.8, name: 'Locked' }, { id: 'A', locked: false, x: 0.3 }, { id: 'B', locked: false, x: 0.5 }]);
  editor.selected = new Set(['locked']);
  editor.updateField({ dataset: { field: 'label' }, value: 'changed' });
  assert.equal(editor.data.slots[0].label, undefined);
  editor.selected = new Set(['locked', 'A', 'B']);
  editor.align('x');
  assert.equal(editor.data.slots[0].x, 0.8);
  assert.equal(editor.data.slots[1].x, 0.3);
  assert.equal(editor.data.slots[2].x, 0.3);
});

test('unsupported native mode and label edits do not replace saved compatibility values', () => {
  const editor = editorFor([{ id: 'slot', locked: false, label: 'Saved label', aspect_mode: 'cover' }]);
  editor.rendererStatus = { capabilities: { feature_support: { labels: false, native_size: false } } };
  editor.selected = new Set(['slot']);
  editor.updateField({ dataset: { field: 'label' }, value: 'Ignored edit' });
  editor.updateField({ dataset: { field: 'aspect_mode' }, value: 'native' });
  assert.equal(editor.data.slots[0].label, 'Saved label');
  assert.equal(editor.data.slots[0].aspect_mode, 'cover');
  assert.equal(editor.isDirty(), false);
  editor.rendererStatus.capabilities.feature_support.labels = true;
  editor.updateField({ dataset: { field: 'label' }, value: 'Supported edit' });
  assert.equal(editor.data.slots[0].label, 'Supported edit');
});

test('geometry edits and templates replace fixed pixels, while undo restores the override', () => {
  const override = { x: 20, y: 30, width: 300, height: 200 };
  const editor = editorFor([{ id: 'slot', locked: false, x: 0, y: 0, width: 0.5, height: 0.5, pixel_override: override }]);
  editor.selected = new Set(['slot']);
  editor.updateGeometry({ dataset: { geometry: 'x' }, value: '20' });
  assert.equal(editor.data.slots[0].pixel_override, null);
  assert.equal(editor.data.slots[0].x, 0.2);
  editor.undo();
  assert.deepEqual(editor.data.slots[0].pixel_override, override);
  editor.applyTemplate('grid-2');
  assert.equal(editor.data.slots.length, 4);
  assert.equal(editor.data.slots[0].pixel_override, null);
  editor.undo();
  assert.deepEqual(editor.data.slots[0].pixel_override, override);
});

test('save success followed by apply failure preserves the saved revision and retry only applies', async () => {
  const editor = editorFor([]);
  editor.data.background = '#123456';
  const savedLayout = { id: 'layout', active: true, current_revision: 2, revision: { data: structuredClone(editor.data) } };
  const oldStatus = { state: 'RUNNING', active_layout_id: 'layout', active_revision: 1, streams: {} };
  const calls = [];
  const original = { fetch: globalThis.fetch, document: globalThis.document };
  globalThis.document = { querySelector: () => null };
  let failApply = true;
  globalThis.fetch = async (url, options) => {
    calls.push([url, options.method ?? 'GET']);
    if (url.endsWith('/activate') && failApply) return new Response('Decoder unavailable', { status: 503 });
    const value = url.endsWith('/activate') ? { layout: savedLayout, renderer: { ...oldStatus, active_revision: 2 } }
      : url.endsWith('/renderer/status') ? oldStatus : savedLayout;
    return new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } });
  };
  try {
    await editor.save(true);
    assert.equal(editor.layout.current_revision, 2);
    assert.equal(editor.isDirty(), false);
    assert.match(editor.saveError, /Revision 2 is saved, but applying it failed: Decoder unavailable/);
    assert.equal(layoutDisplayState(editor.layout, editor.rendererStatus).kind, 'pending');
    assert.equal(editor.host.inert, false);
    failApply = false;
    await editor.save(true);
    assert.equal(calls.filter(([, method]) => method === 'PUT').length, 1);
    assert.equal(calls.filter(([url]) => url.endsWith('/activate')).length, 2);
    assert.equal(editor.saveError, '');
    assert.equal(layoutDisplayState(editor.layout, editor.rendererStatus).kind, 'applied');
  } finally { Object.assign(globalThis, original); }
});

test('failed save preserves dirty work and never sends an apply request', async () => {
  const editor = editorFor([]);
  editor.data.background = '#123456';
  const original = { fetch: globalThis.fetch, document: globalThis.document };
  const urls = [];
  globalThis.document = { querySelector: () => null };
  globalThis.fetch = async (url) => { urls.push(url); return new Response('Validation rejected', { status: 422 }); };
  try {
    await editor.save(true);
    assert.equal(editor.isDirty(), true);
    assert.equal(editor.data.background, '#123456');
    assert.equal(editor.layout.current_revision, 1);
    assert.deepEqual(urls, ['/api/v1/layouts/layout']);
    assert.match(editor.saveError, /Changes were not saved: Validation rejected/);
  } finally { Object.assign(globalThis, original); }
});
