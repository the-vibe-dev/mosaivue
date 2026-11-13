export type TemplateRect = [x: number, y: number, width: number, height: number];

/** Featured camera on the left; remaining cameras fill balanced rows on the right. */
export function templateGeometry(count: number): TemplateRect[] {
  if (!Number.isInteger(count) || count < 2 || count > 10) throw new RangeError('Template size must be 2–10');
  const remainder = count - 1;
  const columns = Math.ceil(Math.sqrt(remainder / 2));
  const rows = Math.ceil(remainder / columns);
  const result: TemplateRect[] = [[0, 0, 0.5, 1]];
  for (let row = 0; row < rows; row++) {
    const items = Math.min(columns, remainder - row * columns);
    for (let column = 0; column < items; column++) {
      result.push([0.5 + column * 0.5 / items, row / rows, 0.5 / items, 1 / rows]);
    }
  }
  return result;
}

/** Equal-sized camera tiles, ordered from left to right and top to bottom. */
export function gridGeometry(size: number): TemplateRect[] {
  if (!Number.isInteger(size) || size < 2 || size > 4) throw new RangeError('Grid size must be 2, 3, or 4');
  return Array.from({ length: size * size }, (_, index) => [
    (index % size) / size, Math.floor(index / size) / size, 1 / size, 1 / size,
  ]);
}
