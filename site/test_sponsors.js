const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const read = name => fs.readFileSync(path.join(root, name), 'utf8');
const sponsorUrl = 'https://serpapi.com/ai-engineering-from-scratch';
const description = 'Web Search API for your AI apps. Available in Markdown and JSON for any integration.';
const tierLabel = /\b(?:Backer|Bronze|Silver|Gold|Platinum|Diamond|Title Partner)\b/i;

function between(text, start, end, file) {
  const section = text.split(start)[1];
  assert.ok(section, `${file} is missing ${start.trim()}`);
  const placement = section.split(end)[0];
  assert.notEqual(placement, section, `${file} is missing ${end.trim()}`);
  return placement;
}

test('sponsor placement uses approved artwork and destination without a tier label', () => {
  const placements = [
    ['README.md', '### Sponsors\n', '### Use every lesson the same way'],
    ['SPONSORS.md', '## Sponsor\n', '## How to sponsor'],
    ['BACKERS.md', '## Sponsors\n', '## Infrastructure support'],
  ];
  for (const [file, start, end] of placements) {
    const text = read(file);
    const placement = between(text, start, end, file);
    assert.ok(placement.includes(description), file);
    assert.doesNotMatch(placement, tierLabel, file);
    assert.doesNotMatch(text, /serpapi\.com\/\?utm_/);
  }
  const sponsors = read('SPONSORS.md');
  assert.ok(sponsors.includes(`href="${sponsorUrl}"`));
  assert.match(sponsors, /media="\(prefers-color-scheme: dark\)" srcset="https:\/\/serpapi\.com\/assets\/media_kit\/logo-with-wordmark-white\.svg"/);
  assert.match(sponsors, /<img src="https:\/\/serpapi\.com\/assets\/media_kit\/logo-with-wordmark\.svg" alt="SerpApi" width="180">/);
  const readme = read('README.md');
  const placement = between(readme, '### Sponsors\n', '### Use every lesson the same way', 'README.md');
  const banner = `<a href="${sponsorUrl}">\n  <img align="left" src="assets/sponsors/serpapi-banner.png" alt="SerpApi. ${description}" width="600">\n</a>`;
  assert.ok(placement.includes(banner));
  assert.ok(placement.includes('Thank you to our sponsors.'));
  assert.ok(placement.includes('href="#supporters"'));
  assert.ok(placement.includes('href="SPONSORS.md"'));
  assert.ok(placement.includes('<br clear="all">'));
  assert.ok(readme.includes('\n## Sponsor the work\n'));
  const image = fs.readFileSync(path.join(root, 'assets/sponsors/serpapi-banner.png'));
  assert.equal(image.subarray(1, 4).toString(), 'PNG');
  assert.equal(image.readUInt32BE(16), 2172);
  assert.equal(image.readUInt32BE(20), 724);
  assert.doesNotMatch(readme, /### Current sponsors|\| Tier \|/);
  assert.match(readme, /<p align="center"><sub><b>[\d,]+<\/b> readers/);
});

test('backer listings are reachable and preserve existing supporters', () => {
  for (const file of ['README.md', 'SPONSORS.md']) {
    assert.match(read(file), /\[[^\]]+\]\(BACKERS\.md\)/, file);
  }
  const backers = read('BACKERS.md');
  assert.match(backers, /^# Backers\n/);
  assert.ok(backers.includes(`[SerpApi](${sponsorUrl})`));
  assert.ok(backers.includes('[SPONSORS.md](SPONSORS.md)'));
  for (const name of ['CodeRabbit', 'iii', 'Vercel Open Source Program']) {
    assert.ok(backers.includes(`[${name}](https://`), name);
  }
  for (const [, destination] of backers.matchAll(/\]\(([^)]+)\)/g)) {
    if (destination.startsWith('https://')) {
      assert.equal(new URL(destination).protocol, 'https:', destination);
    } else {
      assert.ok(fs.statSync(path.join(root, destination)).isFile(), destination);
    }
  }
});

test('supporter navigation survives translated README headings', () => {
  const translations = fs.readdirSync(path.join(root, 'i18n'), { withFileTypes: true })
    .filter(entry => entry.isDirectory())
    .map(entry => path.join('i18n', entry.name, 'README.md'));
  assert.ok(translations.length > 0);
  for (const file of ['README.md', ...translations]) {
    const text = read(file);
    assert.ok(text.includes('href="#supporters"'), file);
    assert.ok(text.includes('<a id="supporters"></a>'), file);
    const sponsorLink = text.match(/href="([^"]*SPONSORS\.md)">Become a sponsor/);
    assert.ok(sponsorLink, file);
    assert.equal(path.resolve(root, path.dirname(file), sponsorLink[1]), path.join(root, 'SPONSORS.md'), file);
    assert.equal((text.match(/>Become a sponsor<\/a>/g) || []).length, 1, file);
    if (file !== 'README.md') {
      assert.doesNotMatch(
        text,
        /### Sponsors|Thank you to our sponsors\.|Your support keeps every lesson free and open source\.|See all supporters|SerpApi\. Web Search API|## Sponsor the work|Free, MIT-licensed, 523 lessons\.|See all sponsors and backers|Want to support the work\?/
      );
    }
  }
});

test('sponsor changes are reserved for maintainers', () => {
  for (const file of ['CONTRIBUTING.md', 'SPONSORS.md']) {
    const text = read(file).replace(/\s+/g, ' ');
    assert.ok(text.includes('Sponsorship changes are not accepted through contributor pull requests.'), file);
    assert.ok(text.includes('names, logos, links, and tier assignments are managed by the maintainer.'), file);
  }
});
