import test from 'node:test';
import assert from 'node:assert/strict';
import { featureDescription, featureSupport, layoutDisplayState } from '../dist/assets/display-state.js';

globalThis.sessionStorage = { getItem: () => null };
const { displayProfileForm } = await import('../dist/assets/display.js');
const layout = { id: 'wall', current_revision: 3, active: true };
const status = { state: 'RUNNING', active_layout_id: 'wall', active_revision: 3, streams: {} };

test('newer saved revision is pending even when database layout is active', () => {
  const result = layoutDisplayState(layout, { ...status, active_revision: 2 });
  assert.equal(result.kind, 'pending');
  assert.equal(result.action, 'Apply saved changes');
  assert.match(result.detail, /Saved revision 3; renderer revision 2/);
});

test('matching applied revision remains reapplicable and does not claim verified playback', () => {
  const result = layoutDisplayState(layout, status);
  assert.equal(result.kind, 'applied');
  assert.equal(result.action, 'Reapply');
  assert.match(result.detail, /Stream health reports playback separately/);
});

test('camera focus is distinct from an applied wall and from a pending saved revision', () => {
  const focused = layoutDisplayState(layout, { ...status, focused: true });
  assert.equal(focused.kind, 'focused');
  assert.match(focused.action, /Restore/);
  const pending = layoutDisplayState(layout, { ...status, focused: true, active_revision: 2 });
  assert.equal(pending.kind, 'pending');
  assert.match(pending.detail, /Applying ends focus/);
});

test('unavailable and unreported state never imply a saved layout is displayed', () => {
  for (const renderer of [null, undefined, { state: 'UNAVAILABLE' }, { state: 'RUNNING' }, { ...status, active_revision: null }]) {
    assert.equal(layoutDisplayState(layout, renderer).kind, 'unknown');
  }
  assert.equal(layoutDisplayState(layout, { ...status, active_layout_id: 'other' }).kind, 'inactive');
  assert.equal(layoutDisplayState(layout, { ...status, active_revision: 4 }).label, 'Saved view out of date');
});

test('missing feature data remains unknown even if a player is available', () => {
  const capabilities = { name: 'fixture', available: true, feature_support: { labels: true, audio: false } };
  assert.equal(featureSupport(capabilities, 'labels'), true);
  assert.equal(featureDescription(capabilities, 'audio'), 'Not supported');
  assert.equal(featureDescription(capabilities, 'portrait'), 'Not reported');
  assert.equal(featureSupport(undefined, 'labels'), undefined);
});

test('profile creation gates unsupported controls but leaves working dimensions editable', () => {
  const html = displayProfileForm(['HDMI-A-1'], { name: 'fixture', available: true, feature_support: { output_selection: false, portrait: false, refresh_rate: false, prevent_blanking: false } });
  for (const name of ['output', 'refresh', 'rotation', 'blanking']) assert.match(html, new RegExp(`<[^>]+name="${name}"[^>]+disabled`));
  for (const name of ['width', 'height']) assert.doesNotMatch(html.match(new RegExp(`<input[^>]+name="${name}"[^>]*>`))[0], /disabled/);
  assert.match(displayProfileForm([]), /name="rotation" disabled/);
  const supported = displayProfileForm([], { name: 'fixture', available: true, feature_support: { portrait: true } });
  assert.doesNotMatch(supported.match(/<select[^>]+name="rotation"[^>]*>/)[0], /disabled/);
});
