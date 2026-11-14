import test from 'node:test';
import assert from 'node:assert/strict';
import { layoutOutputEdit, layoutOutputFields, parseRenderDimension, pixelPlacementWarning, resolveLayoutOutput, validateLayoutOutputPlacement } from '../dist/assets/layout-output.js';

globalThis.sessionStorage = { getItem: () => null };
const { displayProfileForm, displayProfilePayload } = await import('../dist/assets/display.js');
const profile = { id: 'profile', name: 'Lobby <monitor>', width: 1280, height: 720, rotation: 90, output_name: 'HDMI-B-9', refresh_rate: 59.94, prevent_blanking: false };
const data = { output_width: 1920, output_height: 1080, slots: [] };

test('profile dimensions control preview without treating stored rotation as physical rotation', () => {
  assert.deepEqual(resolveLayoutOutput(data, profile.id, [profile]), { width: 1280, height: 720, source: 'Profile: Lobby <monitor>', warning: null });
  const fallback = resolveLayoutOutput(data, null, [profile]);
  assert.equal(fallback.width, 1920);
  assert.equal(fallback.height, 1080);
});

test('unspecified layout dimensions inherit current renderer size and identify an unknown fallback', () => {
  assert.deepEqual(resolveLayoutOutput({ output_width: 800, output_height: null }, null, [], { output: { width: 2560, height: 1440 } }), { width: 800, height: 1440, source: 'Layout / current renderer dimensions', warning: null });
  const missing = resolveLayoutOutput({}, null, []);
  assert.equal(missing.width, 1920);
  assert.equal(missing.height, 1080);
  assert.match(missing.warning, /Renderer size is unavailable/);
  assert.match(resolveLayoutOutput(data, 'deleted-profile', []).warning, /assigned display profile is unavailable/);
});

test('dimension validation rejects fractions, nonnumbers, blank required values and schema boundaries', () => {
  assert.equal(parseRenderDimension('', 'width'), null);
  assert.equal(parseRenderDimension('320', 'width'), 320);
  assert.equal(parseRenderDimension('240', 'height'), 240);
  assert.equal(parseRenderDimension('16384', 'width'), 16384);
  for (const value of ['', '0', '319', '1920.5', 'NaN', 'Infinity', '16385']) assert.throws(() => parseRenderDimension(value, 'width', false), /Width must be a whole number/);
  assert.throws(() => parseRenderDimension('239', 'height'), /Height must be a whole number/);
});

test('profile selection retains stored fallback dimensions and rejects unavailable choices', () => {
  const before = structuredClone(data);
  assert.deepEqual(layoutOutputEdit(data, profile.id, 'bad disabled field', '0', [profile]), { display_profile_id: profile.id, output_width: 1920, output_height: 1080 });
  assert.deepEqual(layoutOutputEdit(data, '', '800', '', [profile]), { display_profile_id: null, output_width: 800, output_height: null });
  assert.throws(() => layoutOutputEdit(data, 'missing', '800', '600', [profile]), /unavailable/);
  assert.deepEqual(data, before);
});

test('layout output form preserves a missing assignment visibly and escapes profile names', () => {
  assert.match(layoutOutputFields(data, profile.id, [profile]), /Lobby &lt;monitor&gt;/);
  assert.match(layoutOutputFields(data, 'missing', []), /value="missing" selected>Unavailable saved profile/);
});

test('explicit smaller layout dimensions cannot silently invalidate fixed-pixel tiles', () => {
  const fixed = { ...data, slots: [{ pixel_override: { x: 700, y: 500, width: 400, height: 300 } }] };
  assert.throws(() => validateLayoutOutputPlacement(fixed, { display_profile_id: null, output_width: 800, output_height: 600 }), /fixed-pixel tiles/);
  assert.doesNotThrow(() => validateLayoutOutputPlacement(fixed, { display_profile_id: profile.id, output_width: 1920, output_height: 1080 }));
  assert.match(pixelPlacementWarning(fixed, { width: 800, height: 600 }), /1 fixed-pixel tile/);
  assert.equal(pixelPlacementWarning(fixed, { width: 1920, height: 1080 }), null);
});

test('editing a profile preserves unsupported stored metadata while changing working dimensions', () => {
  const values = { name: ' New name ', width: '800', height: '600', output: 'changed', refresh: '60', rotation: '0', blanking: true };
  const payload = displayProfilePayload(values, profile, { feature_support: { output_selection: false, refresh_rate: false, portrait: false, prevent_blanking: false } });
  assert.deepEqual(payload, { name: 'New name', width: 800, height: 600, output_name: 'HDMI-B-9', refresh_rate: 59.94, rotation: 90, prevent_blanking: false });
  const html = displayProfileForm([], undefined, profile);
  assert.match(html, /value="HDMI-B-9" selected/);
  assert.match(html, /<option selected>90<\/option>/);
  assert.doesNotMatch(html.match(/<input[^>]+name="blanking"[^>]*>/)[0], /checked/);
});

test('profile creation validates dimensions and uses neutral unsupported defaults', () => {
  const values = { name: 'Profile', width: '1280', height: '720', output: '', refresh: 'bad', rotation: '99', blanking: false };
  assert.deepEqual(displayProfilePayload(values), { name: 'Profile', width: 1280, height: 720, output_name: null, refresh_rate: 60, rotation: 0, prevent_blanking: true });
  assert.throws(() => displayProfilePayload({ ...values, width: '1280.5' }), /Width must be a whole number/);
  assert.throws(() => displayProfilePayload({ ...values, name: '  ' }), /name is required/);
});
