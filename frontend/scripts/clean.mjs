import { rmSync, mkdirSync } from 'node:fs';
rmSync(new URL('../dist', import.meta.url), { recursive: true, force: true });
mkdirSync(new URL('../dist/assets', import.meta.url), { recursive: true });
