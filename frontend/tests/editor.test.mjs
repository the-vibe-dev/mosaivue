import test from 'node:test';
import assert from 'node:assert/strict';

globalThis.sessionStorage = { getItem: () => null };
globalThis.location = { pathname: '/' };
globalThis.history = { state: {} };
const { LayoutEditor } = await import('../dist/assets/editor.js');
const { layoutDisplayState } = await import('../dist/assets/display-state.js');
const { resolveLayoutOutput } = await import('../dist/assets/layout-output.js');

const camera = { id: 'camera-B', name: 'Back', stream_profiles: [{ id: 'profile-B' }] };
function editorFor(slots) {
  const data = { schema_version: 1, slots, background: '#000000', output_width: 1920, output_height: 1080, grid_columns: 12, grid_rows: 12 };
  const editor = new LayoutEditor({}, { id: 'layout', name: 'Main', description: '', display_profile_id: null, current_revision: 1, revision: { id: 'revision-one', data } }, [camera], []);
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
      : url.endsWith('/renderer/status') ? { ...oldStatus, active_revision: failApply ? 1 : 2 } : url.endsWith('/display/profiles') ? [] : savedLayout;
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

test('profile-only edits participate in dirty state, undo and guarded save payloads', async () => {
  const editor = editorFor([{ id: 'tile', x: 0.2, y: 0.3, width: 0.4, height: 0.5 }]);
  const geometry = structuredClone(editor.data.slots);
  editor.updateOutput({ display_profile_id: 'profile', output_width: 1920, output_height: 1080 });
  assert.equal(editor.isDirty(), true);
  editor.undo();
  assert.equal(editor.displayProfileId, null);
  assert.equal(editor.isDirty(), false);
  editor.redo();
  assert.equal(editor.displayProfileId, 'profile');
  assert.deepEqual(editor.data.slots, geometry);
  const original = { fetch: globalThis.fetch, document: globalThis.document };
  globalThis.document = { querySelector: () => null };
  let sent;
  globalThis.fetch = async (url, options) => {
    if (options.method === 'PUT') sent = JSON.parse(options.body);
    return new Response(JSON.stringify(url.endsWith('/renderer/status') ? { state: 'UNAVAILABLE', streams: {} } : url.endsWith('/display/profiles') ? [] : { ...editor.layout, current_revision: 2, display_profile_id: 'profile', revision: { id: 'revision-two', data: editor.data } }), { headers: { 'Content-Type': 'application/json' } });
  };
  try {
    await editor.save(false);
    assert.equal(sent.expected_revision, 1);
    assert.equal(sent.expected_revision_id, 'revision-one');
    assert.equal(sent.display_profile_id, 'profile');
    assert.deepEqual(sent.data.slots, geometry);
    assert.equal(editor.isDirty(), false);
  } finally { Object.assign(globalThis, original); }
});

test('a stale save retains geometry and profile choice and can be recovered as a separate copy', async () => {
  const editor = editorFor([{ id: 'original-tile', x: 0.1, y: 0.2, width: 0.3, height: 0.4 }]);
  editor.data.slots[0].x = 0.6;
  editor.updateOutput({ display_profile_id: 'profile', output_width: 1920, output_height: 1080 });
  const local = structuredClone(editor.data);
  const conflict = { code: 'layout_revision_conflict', message: 'Saved revision changed from 1 to 2', expected_revision: 1, current_revision: 2, expected_revision_id: 'revision-one', current_revision_id: 'revision-two' };
  const original = { fetch: globalThis.fetch, document: globalThis.document };
  globalThis.document = { querySelector: () => null };
  const requests = [];
  globalThis.fetch = async (url, options) => {
    const body = JSON.parse(options.body);
    requests.push({ url, method: options.method, body });
    if (options.method === 'PUT') return new Response(JSON.stringify({ detail: conflict }), { status: 409, headers: { 'Content-Type': 'application/json' } });
    return new Response(JSON.stringify({ id: 'copy', name: body.name, display_profile_id: body.display_profile_id, current_revision: 1, revision: { id: 'copy-revision', data: body.data } }), { headers: { 'Content-Type': 'application/json' } });
  };
  try {
    await editor.save(true);
    assert.deepEqual(editor.data, local);
    assert.equal(editor.displayProfileId, 'profile');
    assert.equal(editor.isDirty(), true);
    assert.match(editor.saveError, /unsaved edits are still open/);
    assert.equal(editor.layout.current_revision, 1);
    await editor.save(true);
    assert.equal(requests.length, 1, 'Blind retry must not overwrite a newer saved layout');
    const copy = await editor.saveCopy('Recovered edits');
    assert.equal(copy.id, 'copy');
    assert.equal(requests[1].url, '/api/v1/layouts');
    assert.equal(requests[1].body.display_profile_id, 'profile');
    assert.equal(requests[1].body.data.slots[0].x, 0.6);
    assert.notEqual(requests[1].body.data.slots[0].id, 'original-tile');
    assert.equal(editor.conflict, null);
    assert.equal(editor.isDirty(), false);
  } finally { Object.assign(globalThis, original); }
});

test('conflict reload requires discard consent and adopts the latest profile only after success', async () => {
  const editor = editorFor([]);
  editor.data.background = '#123456';
  editor.conflict = { code: 'layout_revision_conflict' };
  const original = { fetch: globalThis.fetch, document: globalThis.document, confirm: globalThis.confirm };
  globalThis.document = { querySelector: () => null };
  globalThis.confirm = () => false;
  const urls = [];
  const latest = { ...editor.layout, current_revision: 2, display_profile_id: 'other-profile', revision: { id: 'latest-record', data: { ...editor.data, background: '#abcdef' } } };
  globalThis.fetch = async (url) => {
    urls.push(url);
    const value = url.endsWith('/display/profiles') ? [{ id: 'other-profile', width: 800, height: 600 }] : url.endsWith('/renderer/status') ? { state: 'UNAVAILABLE' } : latest;
    return new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } });
  };
  try {
    await editor.revert();
    assert.equal(urls.length, 0);
    assert.equal(editor.data.background, '#123456');
    globalThis.confirm = () => true;
    await editor.revert();
    assert.equal(editor.data.background, '#abcdef');
    assert.equal(editor.displayProfileId, 'other-profile');
    assert.equal(editor.layout.revision.id, 'latest-record');
    assert.equal(editor.isDirty(), false);
    assert.equal(editor.conflict, null);
  } finally { Object.assign(globalThis, original); }
});

test('apply pins the loaded revision and retains a newer returned draft as pending', async () => {
  const editor = editorFor([]);
  const original = { fetch: globalThis.fetch, document: globalThis.document };
  globalThis.document = { querySelector: () => null };
  let body;
  globalThis.fetch = async (url, options) => {
    if (url.endsWith('/display/profiles')) return new Response('[]', { headers: { 'Content-Type': 'application/json' } });
    if (url.endsWith('/renderer/status')) return new Response(JSON.stringify({ state: 'RUNNING', active_layout_id: 'layout', active_revision: 1, active_revision_id: 'revision-one', streams: {} }), { headers: { 'Content-Type': 'application/json' } });
    body = JSON.parse(options.body);
    return new Response(JSON.stringify({ layout: { ...editor.layout, current_revision: 2, revision: { id: 'revision-two', data: editor.data } }, renderer: { state: 'RUNNING', active_layout_id: 'layout', active_revision: 1, active_revision_id: 'revision-one', streams: {} } }), { headers: { 'Content-Type': 'application/json' } });
  };
  try {
    await editor.save(true);
    assert.deepEqual(body, { expected_revision: 1, expected_revision_id: 'revision-one' });
    assert.equal(editor.layout.current_revision, 2);
    assert.equal(editor.rendererStatus.active_revision, 1);
    assert.equal(layoutDisplayState(editor.layout, editor.rendererStatus).kind, 'pending');
  } finally { Object.assign(globalThis, original); }
});

test('a conflict detected after renderer acceptance reports both outcomes without discarding the local version', async () => {
  const editor = editorFor([]);
  const original = { fetch: globalThis.fetch, document: globalThis.document };
  globalThis.document = { querySelector: () => null };
  const conflict = { code: 'layout_changed_during_apply', message: 'Configuration history was deleted during application', renderer_applied: true };
  globalThis.fetch = async (url) => url.endsWith('/renderer/status')
    ? new Response(JSON.stringify({ state: 'RUNNING', active_layout_id: 'layout', active_revision: 1, active_revision_id: 'revision-one', streams: {} }), { headers: { 'Content-Type': 'application/json' } })
    : new Response(JSON.stringify({ detail: conflict }), { status: 409, headers: { 'Content-Type': 'application/json' } });
  try {
    await editor.save(true);
    assert.equal(editor.layout.revision.id, 'revision-one');
    assert.match(editor.saveError, /renderer accepted the requested version before the configuration changed/);
    assert.match(editor.saveError, /local version is still open/);
    assert.equal(editor.conflict.renderer_applied, true);
    assert.equal(editor.conflict.code, 'layout_changed_during_apply');
    assert.doesNotMatch(editor.saveError, /Retry Apply|applying it failed/);
  } finally { Object.assign(globalThis, original); }
});

test('refreshing status loads shared profile edits without replacing unsaved layout choices or geometry', async () => {
  const editor = editorFor([{ id: 'tile', x: 0.1, y: 0, width: 0.5, height: 0.5 }]);
  editor.displayProfiles = [{ id: 'shared', name: 'Shared', width: 1920, height: 1080 }];
  editor.updateOutput({ display_profile_id: 'shared', output_width: 1600, output_height: 900 });
  editor.data.slots[0].x = 0.4;
  const local = structuredClone(editor.data);
  const original = globalThis.fetch;
  globalThis.fetch = async (url) => new Response(JSON.stringify(url.endsWith('/display/profiles') ? [{ id: 'shared', name: 'Shared', width: 1280, height: 720 }] : { state: 'RUNNING', active_layout_id: 'layout', active_revision: 1, output: { width: 1280, height: 720 }, streams: {} }), { headers: { 'Content-Type': 'application/json' } });
  try {
    await editor.refreshDisplayStatus();
    assert.equal(editor.displayProfileId, 'shared');
    assert.deepEqual(editor.data, local);
    assert.equal(editor.isDirty(), true);
    assert.equal(resolveLayoutOutput(editor.data, editor.displayProfileId, editor.displayProfiles, editor.rendererStatus).width, 1280);
  } finally { globalThis.fetch = original; }
});

test('successful apply refreshes shared profile size instead of showing endless reapply', async () => {
  const editor = editorFor([]);
  editor.layout.display_profile_id = editor.displayProfileId = 'shared';
  editor.savedData = editor.draftSignature();
  editor.displayProfiles = [{ id: 'shared', name: 'Shared', width: 1920, height: 1080 }];
  const renderer = { state: 'RUNNING', active_layout_id: 'layout', active_revision: 1, active_revision_id: 'revision-one', output: { width: 1280, height: 720 }, streams: {} };
  const original = { fetch: globalThis.fetch, document: globalThis.document };
  globalThis.document = { querySelector: () => null };
  globalThis.fetch = async (url) => new Response(JSON.stringify(url.endsWith('/display/profiles') ? [{ id: 'shared', name: 'Shared', width: 1280, height: 720 }] : url.endsWith('/renderer/status') ? renderer : { layout: editor.layout, renderer }), { headers: { 'Content-Type': 'application/json' } });
  try {
    await editor.save(true);
    const output = resolveLayoutOutput(editor.data, editor.displayProfileId, editor.displayProfiles, editor.rendererStatus);
    assert.equal(output.width, 1280);
    assert.equal(layoutDisplayState(editor.layout, editor.rendererStatus, output).kind, 'applied');
    assert.equal(editor.isDirty(), false);
  } finally { Object.assign(globalThis, original); }
});
