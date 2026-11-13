import test from 'node:test';
import assert from 'node:assert/strict';

globalThis.sessionStorage = { getItem: () => null };
globalThis.location = { pathname: '/' };
globalThis.history = { state: {} };
const { LayoutEditor } = await import('../dist/assets/editor.js');

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
