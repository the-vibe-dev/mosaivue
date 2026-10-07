import test from 'node:test';
import assert from 'node:assert/strict';
import { escapeHtml, formatBytes, formatDuration } from '../dist/assets/ui.js';
import { templateGeometry } from '../dist/assets/templates.js';

test('escapeHtml prevents markup injection', () => {
  assert.equal(escapeHtml('<img src=x onerror=1>'), '&lt;img src=x onerror=1&gt;');
});

test('formatters produce compact appliance labels', () => {
  assert.equal(formatBytes(1024 * 1024), '1.0 MB');
  assert.equal(formatDuration(90061), '1d 1h 1m');
});

test('featured templates cover the canvas for every size from 2 to 10', () => {
  for (let count = 2; count <= 10; count++) {
    const rectangles = templateGeometry(count);
    assert.equal(rectangles.length, count);
    assert.deepEqual(rectangles[0], [0, 0, 0.5, 1]);
    for (const [x, y, width, height] of rectangles) {
      assert.ok(x >= 0 && y >= 0 && x + width <= 1 && y + height <= 1);
      assert.ok(width > 0 && height > 0);
    }
    const area = rectangles.reduce((sum, [, , width, height]) => sum + width * height, 0);
    assert.ok(Math.abs(area - 1) < 1e-9);
  }
});
