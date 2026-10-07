/** Featured camera on the left; remaining cameras fill balanced rows on the right. */
export function templateGeometry(count) {
    if (!Number.isInteger(count) || count < 2 || count > 10)
        throw new RangeError('Template size must be 2–10');
    const remainder = count - 1;
    const columns = Math.ceil(Math.sqrt(remainder / 2));
    const rows = Math.ceil(remainder / columns);
    const result = [[0, 0, 0.5, 1]];
    for (let row = 0; row < rows; row++) {
        const items = Math.min(columns, remainder - row * columns);
        for (let column = 0; column < items; column++) {
            result.push([0.5 + column * 0.5 / items, row / rows, 0.5 / items, 1 / rows]);
        }
    }
    return result;
}
//# sourceMappingURL=templates.js.map