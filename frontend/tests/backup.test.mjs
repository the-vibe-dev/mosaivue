import test from 'node:test';
import assert from 'node:assert/strict';

globalThis.sessionStorage = { getItem: () => null };
const { buildRestoreRequest, restoreWarning, MAX_JSON_IMPORT_BYTES } = await import('../dist/assets/backup.js');

test('JSON configuration import preserves content and merge choice without sending a passphrase', async () => {
  const document = { format: 'mosaivue', cameras: [{ name: 'Front door' }], layouts: [] };
  const file = new File([JSON.stringify(document)], 'mosaivue-export.JSON', { type: 'application/json' });
  const request = await buildRestoreRequest(file, true, 'unused-passphrase');
  assert.equal(request.path, '/backup/import');
  assert.equal(request.options.method, 'POST');
  assert.deepEqual(JSON.parse(request.options.body), { document, merge: true });
  assert.equal(JSON.parse((await buildRestoreRequest(file, false, '')).options.body).merge, false);
});

test('encrypted archive restore sends exact binary bytes and passphrase in multipart data', async () => {
  const bytes = Uint8Array.from([0x4d, 0x56, 0, 0xff, 0x80]);
  const file = new File([bytes], 'wall.cwbackup');
  const request = await buildRestoreRequest(file, false, ' secret with spaces ');
  assert.equal(request.path, '/backup/restore');
  assert.ok(request.options.body instanceof FormData);
  assert.equal(request.options.body.get('passphrase'), ' secret with spaces ');
  assert.equal(request.options.body.get('merge'), 'false');
  assert.deepEqual(new Uint8Array(await request.options.body.get('file').arrayBuffer()), bytes);
});

test('invalid and oversized JSON is rejected before any request or large file read', async () => {
  await assert.rejects(buildRestoreRequest(new File(['bad JSON'], 'bad.json'), true, ''), /Unable to read/);
  for (const value of ['null', '[]', '"text"']) await assert.rejects(buildRestoreRequest(new File([value], 'bad.json'), true, ''), /must be an object/);
  await assert.rejects(buildRestoreRequest({ name: 'large.json', size: MAX_JSON_IMPORT_BYTES + 1, text: () => { throw new Error('Must not read'); } }, true, ''), /32 MiB limit/);
  await assert.rejects(buildRestoreRequest(new File(['data'], 'wrong.txt'), true, ''), /Choose a .json/);
});

test('restore success retains renderer warnings and does not confuse saved configuration with applied playback', () => {
  assert.equal(restoreWarning({ imported: { cameras: 1 }, renderer_applied: false, renderer_warning: 'Renderer offline' }), 'Renderer offline');
  assert.match(restoreWarning({ imported: {}, renderer_applied: false }), /display has not applied/);
  assert.equal(restoreWarning({ imported: {}, renderer_applied: true }), null);
});
