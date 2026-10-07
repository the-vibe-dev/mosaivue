import { copyFileSync, mkdirSync } from 'node:fs';
const root = new URL('../', import.meta.url);
const dist = new URL('../dist/', import.meta.url);
mkdirSync(new URL('assets/', dist), { recursive: true });
mkdirSync(new URL('brand/', dist), { recursive: true });
copyFileSync(new URL('index.html', root), new URL('index.html', dist));
copyFileSync(new URL('src/styles.css', root), new URL('assets/styles.css', dist));
copyFileSync(new URL('src/manifest.webmanifest', root), new URL('manifest.webmanifest', dist));
for (const name of ['mosaivue-logo.png', 'mosaivue-icon.png', 'mosaivue-stacked.png']) {
  copyFileSync(new URL(`src/brand/${name}`, root), new URL(`brand/${name}`, dist));
}
