/**
 * scripts/pages_i18n.mjs adds the zh-Hant layer to every built page. A bad
 * prefix 404s the dictionary silently (the page just stays English), and a
 * double injection runs i18n.js twice, so both are pinned here.
 *
 * Run: node --test scripts/test_pages_i18n.mjs
 */

import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import { inject, pageKey, run } from './pages_i18n.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const SITE = join(ROOT, 'site');

const page = (headerSrc, extra = '') =>
  `<!doctype html><html><head><title>T</title></head><body><p>Hi</p>${extra}` +
  (headerSrc ? `<script src="${headerSrc}" defer></script>` : '') + `</body></html>`;

const srcs = (html) => [...html.matchAll(/<script src="([^"]+)"/g)].map((m) => m[1]);

test('adds the dictionary, then the runtime, before </body>', () => {
  const out = inject(page('header.js?v=1'));
  const s = srcs(out);
  assert.deepEqual(s.slice(1), ['i18n.zh-Hant.js', 'i18n.js']);
  assert.ok(out.indexOf('i18n.js"') < out.indexOf('</body>'));
});

test('copies the prefix from the header.js tag', () => {
  assert.deepEqual(srcs(inject(page('/header.js?v=abc'))).slice(1), ['/i18n.zh-Hant.js', '/i18n.js']);
  assert.deepEqual(srcs(inject(page('../header.js'))).slice(1), ['../i18n.zh-Hant.js', '../i18n.js']);
});

test('loads the page dictionary between the two', () => {
  const s = srcs(inject(page('header.js'), { pageDict: 'i18n-pages/learning-paths.zh-Hant.js' }));
  assert.deepEqual(s.slice(1), ['i18n.zh-Hant.js', 'i18n-pages/learning-paths.zh-Hant.js', 'i18n.js']);
});

test('stamps a version so a dictionary update is not served stale', () => {
  assert.deepEqual(srcs(inject(page('header.js'), { version: 'f00' })).slice(1),
    ['i18n.zh-Hant.js?v=f00', 'i18n.js?v=f00']);
});

test('leaves a page that already loads the layer alone', () => {
  const html = page('header.js', '<script src="i18n.zh-Hant.js?v=1"></script><script src="i18n.js?v=1"></script>');
  assert.equal(inject(html), null);
});

test('adds only the page dictionary to a page that already loads the layer', () => {
  const html = page('header.js', '<script src="i18n.zh-Hant.js?v=1"></script><script src="i18n.js?v=1"></script>');
  const s = srcs(inject(html, { pageDict: 'i18n-pages/index.zh-Hant.js' }));
  assert.deepEqual(s, ['i18n.zh-Hant.js?v=1', 'i18n-pages/index.zh-Hant.js', 'i18n.js?v=1', 'header.js']);
});

test('skips redirect stubs and pages without header.js', () => {
  assert.equal(inject('<!doctype html><title>Redirecting…</title><script src="header.js"></script>'), null);
  assert.equal(inject(page(null)), null);
});

test('is idempotent over a built tree, and resolves page dictionaries by path', () => {
  const dir = mkdtempSync(join(tmpdir(), 'pages-i18n-'));
  mkdirSync(join(dir, 'hubs', 'glossary'), { recursive: true });
  mkdirSync(join(dir, 'i18n-pages'));
  writeFileSync(join(dir, 'i18n.zh-Hant.js'), 'window.I18N_ZH_HANT = {};');
  writeFileSync(join(dir, 'i18n.js'), '');
  writeFileSync(join(dir, 'i18n-pages', 'learning-paths.zh-Hant.js'), '');
  writeFileSync(join(dir, 'learning-paths.html'), page('header.js'));
  writeFileSync(join(dir, 'hubs', 'glossary', 'rag.html'), page('/header.js'));
  writeFileSync(join(dir, 'stub.html'), '<title>Redirecting…</title>');

  const first = run(dir);
  assert.deepEqual(first, { pages: 3, injected: 2, pageDicts: 1, skipped: 1 });
  const lp = srcs(readFileSync(join(dir, 'learning-paths.html'), 'utf8'));
  assert.match(lp[2], /^i18n-pages\/learning-paths\.zh-Hant\.js\?v=[0-9a-f]{12}$/);
  assert.match(srcs(readFileSync(join(dir, 'hubs', 'glossary', 'rag.html'), 'utf8'))[1], /^\/i18n\.zh-Hant\.js\?v=/);
  assert.equal(pageKey(dir, join(dir, 'hubs', 'glossary', 'rag.html')), 'hubs/glossary/rag');

  assert.equal(run(dir).injected, 0);
  assert.equal(execFileSync('node', [join(ROOT, 'scripts', 'pages_i18n.mjs'), dir], { encoding: 'utf8' })
    .includes('0 of 3'), true);
});

test('every page dictionary in site/ extends the shared one and names a real page', () => {
  let files = [];
  try { files = readdirSync(join(SITE, 'i18n-pages'), { recursive: true }).filter((f) => f.endsWith('.zh-Hant.js')); } catch {}
  for (const f of files) {
    const src = readFileSync(join(SITE, 'i18n-pages', f), 'utf8');
    assert.match(src, /Object\.assign\(window\.I18N_ZH_HANT,/, `${f} must merge into window.I18N_ZH_HANT`);
    const key = f.replace(/\.zh-Hant\.js$/, '');
    assert.doesNotThrow(() => readFileSync(join(SITE, `${key}.html`)), `${f} has no site/${key}.html`);
  }
});
