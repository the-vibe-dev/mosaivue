import test from 'node:test';
import assert from 'node:assert/strict';
import { escapeHtml, formatBytes, formatDuration } from '../dist/assets/ui.js';
import { gridGeometry, templateGeometry } from '../dist/assets/templates.js';

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

test('uniform 2×2, 3×3, and 4×4 grids cover the canvas without overlap', () => {
  for (const size of [2, 3, 4]) {
    const rectangles = gridGeometry(size);
    assert.equal(rectangles.length, size * size);
    assert.deepEqual(rectangles[0], [0, 0, 1 / size, 1 / size]);
    let area = 0;
    for (const [index, [x, y, width, height]] of rectangles.entries()) {
      assert.ok(x >= 0 && y >= 0 && width > 0 && height > 0);
      assert.ok(x + width <= 1 + 1e-12 && y + height <= 1 + 1e-12);
      area += width * height;
      for (const [otherX, otherY, otherWidth, otherHeight] of rectangles.slice(index + 1)) {
        const overlapWidth = Math.min(x + width, otherX + otherWidth) - Math.max(x, otherX);
        const overlapHeight = Math.min(y + height, otherY + otherHeight) - Math.max(y, otherY);
        assert.ok(overlapWidth <= 1e-12 || overlapHeight <= 1e-12);
      }
    }
    assert.ok(Math.abs(area - 1) < 1e-12);
  }
});

test('uniform grids reject unsupported dimensions', () => {
  for (const size of [0, 1, 2.5, 5, NaN, Infinity]) assert.throws(() => gridGeometry(size), RangeError);
});
