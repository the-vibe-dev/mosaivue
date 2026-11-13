import test from 'node:test';
import assert from 'node:assert/strict';
import { credentialEdit, filterCameras, mergeProfileEdit, rotationEntries, setGeometry } from '../dist/assets/forms.js';

test('renaming a stream preserves its identity, priority, and probe metadata', () => {
  const profile = { id: 'profile-main', name: 'Main', url: 'rtsp://camera/main', codec: 'h264', fps: 15, bitrate: 2000000, width: 1920, height: 1080, priority: 3 };
  assert.deepEqual(mergeProfileEdit(profile, { name: 'Daylight' }), { ...profile, name: 'Daylight' });
  assert.equal(profile.name, 'Main');
});

test('blank credentials preserve a saved or embedded password without trimming real secrets', () => {
  assert.deepEqual(credentialEdit('', false), {});
  assert.deepEqual(credentialEdit('  exact secret  ', false), { password: '  exact secret  ' });
  assert.deepEqual(credentialEdit('ignored', true), { clear_credentials: true });
});

test('camera filtering supports all query words, hosts, vendors, and disabled state', () => {
  const cameras = [
    { id: 'one', name: 'Front', host: '10.0.0.2', vendor: 'Acme', tags: ['outside'], enabled: true },
    { id: 'two', name: 'Garage', host: '10.0.0.3', vendor: 'Acme', tags: ['inside'], enabled: false },
  ];
  assert.deepEqual(filterCameras(cameras, ' ACME  outside ').map((item) => item.id), ['one']);
  assert.deepEqual(filterCameras(cameras, '10.0.0.3', 'disabled').map((item) => item.id), ['two']);
  assert.deepEqual(filterCameras(cameras, 'garage', 'enabled'), []);
});

test('rotation preserves visual order, weights, and manual profiles', () => {
  assert.deepEqual(rotationEntries([
    { cameraId: 'B', selected: true, weight: 7, profileId: 'sub-B' },
    { cameraId: 'A', selected: false, weight: 1, profileId: '' },
    { cameraId: 'C', selected: true, weight: 2, profileId: '' },
  ]), [
    { camera_id: 'B', weight: 7, stream_profile_id: 'sub-B' },
    { camera_id: 'C', weight: 2, stream_profile_id: null },
  ]);
});

test('geometry at the right/bottom edges keeps positive size and remains on canvas', () => {
  const slot = { x: 0.2, y: 0.1, width: 0.4, height: 0.3, locked: false };
  const moved = setGeometry(setGeometry(slot, 'x', 100), 'y', 100);
  assert.equal(moved.x, 0.6);
  assert.equal(moved.y, 0.7);
  assert.equal(moved.width, 0.4);
  assert.equal(moved.height, 0.3);
  assert.equal(setGeometry(moved, 'width', 0).width, 0.01);
  assert.deepEqual(setGeometry(slot, 'width', NaN), slot);
});

test('locked geometry cannot be changed by numeric fields', () => {
  const slot = { x: 0, y: 0, width: 0.5, height: 0.5, locked: true };
  assert.equal(setGeometry(slot, 'x', 40), slot);
});
