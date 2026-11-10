#!/usr/bin/env node
/**
 * Load the zh-Hant translation layer on every built page. Fork-only.
 *
 * site/i18n.js translates a page by English source string, but only pages
 * that include it get translated: upstream's hand-written pages mostly don't,
 * and none of the generated ones (hubs, interviews, cheat sheets, practice,
 * manuals) do. Editing upstream's templates and generators would conflict on
 * every sync, so this runs as a post-build step instead and adds, before the
 * closing </body> of each page that lacks them:
 *
 *   i18n.zh-Hant.js                  the shared dictionary
 *   i18n-pages/<page>.zh-Hant.js     that page's own strings, when the file exists
 *   i18n.js                          the translator and the language toggle
 *
 * The src prefix is copied from the page's own header.js tag, so a page that
 * loads "header.js", "../header.js" or "/header.js" loads these the same way.
 * Pages without header.js (redirect stubs, fragments) are left alone. Running
 * it twice changes nothing.
 *
 * Run after the site build: node scripts/pages_i18n.mjs [outDir]   # default: site/
 */

import { createHash } from 'node:crypto';
import { existsSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');

export const DICT = 'i18n.zh-Hant.js';
export const RUNTIME = 'i18n.js';
export const PAGE_DIR = 'i18n-pages';

const STUB_MARK = '<title>Redirecting…</title>';
const HEADER = /<script\b[^>]*\bsrc="([^"]*?)header\.js(?:\?[^"]*)?"/i;
const HAS_DICT = /<script\b[^>]*\bsrc="[^"]*i18n\.zh-Hant\.js(?:\?[^"]*)?"/i;
const RUNTIME_TAG = /<script\b[^>]*\bsrc="[^"]*\bi18n\.js(?:\?[^"]*)?"[^>]*><\/script>/i;

function htmlFiles(dir) {
  const out = [];
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) {
      if (e.name !== 'node_modules' && e.name !== PAGE_DIR) out.push(...htmlFiles(p));
    } else if (e.name.endsWith('.html')) out.push(p);
  }
  return out;
}

function stamp(...files) {
  const h = createHash('sha256');
  for (const f of files) if (existsSync(f)) h.update(readFileSync(f));
  return h.digest('hex').slice(0, 12);
}

/** The page dictionary key: its path under outDir without ".html". */
export function pageKey(outDir, file) {
  return relative(outDir, file).split(sep).join('/').replace(/\.html$/, '');
}

/**
 * Returns the new HTML, or null when the page is left as it is.
 * `pageDict` is the page dictionary's path relative to the site root, or null.
 */
export function inject(html, { pageDict = null, version = '' } = {}) {
  if (html.includes(STUB_MARK)) return null;
  const header = HEADER.exec(html);
  if (!header) return null;
  const prefix = header[1];
  const v = version ? `?v=${version}` : '';
  const tag = (src) => `<script src="${prefix}${src}${v}"></script>`;
  const pageTag = pageDict && !html.includes(pageDict) ? tag(pageDict) : '';

  if (HAS_DICT.test(html)) {
    if (!pageTag) return null;
    const rt = RUNTIME_TAG.exec(html);
    if (!rt) return null;
    return html.slice(0, rt.index) + pageTag + '\n' + html.slice(rt.index);
  }

  const block = [tag(DICT), pageTag, tag(RUNTIME)].filter(Boolean).join('\n') + '\n';
  const at = html.toLowerCase().lastIndexOf('</body>');
  return at === -1 ? html + '\n' + block : html.slice(0, at) + block + html.slice(at);
}

export function run(outDir) {
  const counts = { pages: 0, injected: 0, pageDicts: 0, skipped: 0 };
  for (const file of htmlFiles(outDir)) {
    counts.pages++;
    const key = pageKey(outDir, file);
    const pageRel = `${PAGE_DIR}/${key}.zh-Hant.js`;
    const pagePath = join(outDir, pageRel);
    const pageDict = existsSync(pagePath) ? pageRel : null;
    const version = stamp(join(outDir, DICT), join(outDir, RUNTIME), pageDict ? pagePath : '');
    const html = readFileSync(file, 'utf8');
    const next = inject(html, { pageDict, version });
    if (next === null || next === html) { counts.skipped++; continue; }
    writeFileSync(file, next);
    counts.injected++;
    if (pageDict) counts.pageDicts++;
  }
  return counts;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const out = resolve(process.argv[2] ?? join(ROOT, 'site'));
  for (const f of [DICT, RUNTIME]) {
    if (!existsSync(join(out, f))) {
      console.error(`pages_i18n: ${f} missing from ${out}`);
      process.exit(1);
    }
  }
  const c = run(out);
  console.log(`pages_i18n: ${c.injected} of ${c.pages} pages now load the zh-Hant layer ` +
    `(${c.pageDicts} with a page dictionary); ${c.skipped} already had it or have no header.js`);
}
