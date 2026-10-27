/** Bundle selected LWQ originals for the native HTML application. No CDN at runtime. */
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';
import fs from 'node:fs';
import { createHash } from 'node:crypto';

const root = fileURLToPath(new URL('../', import.meta.url));
const frontend = path.join(root, 'frontend');
const web = process.env.SOURCECAST_WEB_DIR || (fs.existsSync(path.join(root, 'web/library/index.html')) ? path.join(root, 'web/library') : root);
const shared = process.env.LWQ_DESIGN_ROOT || path.join(root, '..', '设计系统');
const localModules = path.join(frontend, 'node_modules');
const dependencyRoot = fs.existsSync(path.join(localModules, 'vite')) ? frontend : shared;
const dependencyRequire = createRequire(path.join(dependencyRoot, 'package.json'));
const { build } = await import(pathToFileURL(dependencyRequire.resolve('vite')));
const { default: react } = await import(pathToFileURL(dependencyRequire.resolve('@vitejs/plugin-react')));

await build({
  configFile: false,
  root: frontend,
  base: './',
  plugins: [react(), {
    name: 'lwq-local-dependencies',
    resolveId(source) {
      if (source.startsWith('.') || path.isAbsolute(source) || source.startsWith('\0')) return;
      try {
        const resolved = dependencyRequire.resolve(source);
        // Prefer ESM entrypoints, so barrels such as lucide/radix can tree-shake.
        if (/^(@[^/]+\/)?[^/]+$/.test(source)) {
          let directory = path.dirname(resolved);
          while (directory !== path.dirname(directory)) {
            const candidate = path.join(directory, 'package.json');
            if (fs.existsSync(candidate)) {
              const pkg = JSON.parse(fs.readFileSync(candidate, 'utf8'));
              if (pkg.name === source) return pkg.module ? path.resolve(directory, pkg.module) : resolved;
            }
            directory = path.dirname(directory);
          }
        }
        return resolved;
      } catch { return; }
    },
  }],
  define: { 'process.env.NODE_ENV': JSON.stringify('production') },
  build: {
    outDir: path.join(web, 'vendor/lwq'),
    emptyOutDir: false,
    minify: true,
    lib: { entry: path.join(frontend, 'main.tsx'), name: 'SourcecastDesign', formats: ['iife'], fileName: () => 'components.js' },
  },
});

// The long-lived local preview must never keep a previous successful bundle
// after a rebuild. Version every referenced local JS/CSS by its actual bytes.
const htmlPath = path.join(web, 'index.html');
const html = fs.readFileSync(htmlPath, 'utf8');
const versioned = html.replace(/((?:src|href)=["'])([^"'?#]+\.(?:js|css))(?:\?[^"']*)?(["'])/g, (full, prefix, asset, quote) => {
  if (/^[a-z]+:/i.test(asset) || asset.startsWith('//')) return full;
  const file = path.join(web, asset);
  if (!fs.existsSync(file)) return full;
  const hash = createHash('sha256').update(fs.readFileSync(file)).digest('hex').slice(0, 12);
  return `${prefix}${asset}?v=${hash}${quote}`;
});
fs.writeFileSync(htmlPath, versioned);
