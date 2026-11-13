import test from 'node:test';
import assert from 'node:assert/strict';

const saved = new Map();
globalThis.sessionStorage = { getItem: (key) => saved.get(key), setItem: (key, value) => saved.set(key, value), removeItem: (key) => saved.delete(key) };
const { api, ApiError, apiErrorMessage, download, setCsrf } = await import('../dist/assets/api.js');

test('validation errors identify fields instead of showing object strings', () => {
  assert.equal(apiErrorMessage({ detail: [{ loc: ['body', 'stream_profiles', 0, 'url'], msg: 'RTSP URL required' }] }, 'Invalid request'), 'stream_profiles → 0 → url: RTSP URL required');
});

test('plain-text errors produce ApiError without reading the response body twice', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => new Response('Renderer unavailable', { status: 503, statusText: 'Service Unavailable' });
  try {
    await assert.rejects(api('/renderer/status'), (error) => error instanceof ApiError && error.status === 503 && error.message === 'Renderer unavailable');
  } finally { globalThis.fetch = original; }
});

test('HTML proxy errors use a concise HTTP status and mutation requests retain CSRF', async () => {
  const original = globalThis.fetch;
  setCsrf('fixture-csrf');
  globalThis.fetch = async (_url, options) => {
    assert.equal(options.headers.get('X-CSRF-Token'), 'fixture-csrf');
    assert.equal(options.credentials, 'same-origin');
    return new Response('<html><body>proxy error</body></html>', { status: 502, statusText: 'Bad Gateway' });
  };
  try { await assert.rejects(api('/layouts', { method: 'POST', body: '{}' }), (error) => error instanceof ApiError && error.message === 'Bad Gateway'); }
  finally { globalThis.fetch = original; setCsrf(''); }
});

async function captureDownload(response, path, filename, options = {}) {
  const original = {
    fetch: globalThis.fetch, document: globalThis.document, window: globalThis.window,
    createObjectURL: URL.createObjectURL, revokeObjectURL: URL.revokeObjectURL,
  };
  let capturedBlob;
  let capturedRequest;
  let cleanup;
  let revoked;
  let clicked = false;
  const anchor = { href: '', download: '', click: () => { clicked = true; } };
  globalThis.fetch = async (_url, request) => { capturedRequest = request; return response; };
  globalThis.document = { createElement: (tag) => { assert.equal(tag, 'a'); return anchor; } };
  globalThis.window = { setTimeout: (callback) => { cleanup = callback; } };
  URL.createObjectURL = (blob) => { assert.ok(blob instanceof Blob); capturedBlob = blob; return 'blob:test-download'; };
  URL.revokeObjectURL = (url) => { revoked = url; };
  try {
    await download(path, filename, options);
    assert.equal(anchor.download, filename);
    assert.equal(anchor.href, 'blob:test-download');
    assert.equal(clicked, true);
    assert.equal(revoked, undefined);
    cleanup();
    assert.equal(revoked, 'blob:test-download');
    return { blob: capturedBlob, request: capturedRequest };
  } finally {
    globalThis.fetch = original.fetch;
    globalThis.document = original.document;
    globalThis.window = original.window;
    URL.createObjectURL = original.createObjectURL;
    URL.revokeObjectURL = original.revokeObjectURL;
  }
}

test('sanitized JSON export downloads a JSON Blob rather than a parsed object', async () => {
  const configuration = { format: 'mosaivue', cameras: [{ name: 'Front door', tags: ['outside'] }] };
  const { blob } = await captureDownload(
    new Response(JSON.stringify(configuration), { headers: { 'Content-Type': 'application/json' } }),
    '/backup/export', 'mosaivue-export.json',
  );
  assert.equal(blob.type, 'application/json');
  assert.deepEqual(JSON.parse(await blob.text()), configuration);
});

test('encrypted backup download preserves binary bytes and authenticated POST options', async () => {
  const bytes = Uint8Array.from([0x4d, 0x56, 0, 0xff, 0x80, 0x22, 0x0a]);
  setCsrf('backup-csrf');
  try {
    const { blob, request } = await captureDownload(
      new Response(bytes, { headers: { 'Content-Type': 'application/octet-stream' } }),
      '/backup/create', 'mosaivue-backup.cwbackup',
      { method: 'POST', body: JSON.stringify({ include_credentials: true, passphrase: 'test-passphrase' }) },
    );
    assert.deepEqual(new Uint8Array(await blob.arrayBuffer()), bytes);
    assert.equal(blob.type, 'application/octet-stream');
    assert.equal(request.method, 'POST');
    assert.equal(request.headers.get('X-CSRF-Token'), 'backup-csrf');
    assert.equal(JSON.parse(request.body).include_credentials, true);
  } finally { setCsrf(''); }
});
