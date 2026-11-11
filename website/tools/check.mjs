// Checks the built walkthrough: size, self-containment, shared tokens and story consistency.
import { readFile, stat } from 'node:fs/promises';
import path from 'node:path';
import { paths } from './lib/paths.mjs';

const BUDGET = 6 * 1024 * 1024;
const OUTPUT = path.join(paths.dist, 'tum-mcp-walkthrough.html');
const failures = [];
const fail = message => failures.push(message);

const html = await readFile(OUTPUT, 'utf8').catch(() => fail('dist/tum-mcp-walkthrough.html is missing; run npm run build.'));
if (html) {
  const { size } = await stat(OUTPUT);
  if (size > BUDGET) fail(`The page is ${(size / 1048576).toFixed(2)} MB; the budget is ${BUDGET / 1048576} MB.`);
  const head = html.slice(0, html.indexOf('<body'));
  const loads = [...head.matchAll(/<(?:link|script)[^>]+(?:href|src)="(https?:[^"]+)"/g), ...html.matchAll(/<(?:img|script|iframe|source|video|audio)[^>]+src="(https?:[^"]+)"/g)];
  for (const [, url] of loads) fail(`The page loads ${url}; everything must be inlined.`);
  for (const [, url] of html.matchAll(/url\((["']?)(https?:[^)"']+)\1\)/g)) fail(`A stylesheet loads ${url}.`);
}

const tokens = await readFile(path.join(paths.src, 'styles/tokens.css'), 'utf8');
const appStyles = await readFile(path.join(paths.appSite, 'styles.css'), 'utf8');
const declarations = (css, selector) => {
  const start = css.indexOf(`${selector} {`);
  const block = css.slice(start, css.indexOf('}', start));
  return Object.fromEntries([...block.matchAll(/(--[\w-]+):\s*([^;]+);/g)].map(([, name, value]) => [name, value.trim()]));
};
for (const selector of [':root', ':root[data-theme="dark"]']) {
  const page = declarations(tokens, selector);
  const app = declarations(appStyles, selector);
  for (const [name, value] of Object.entries(page)) {
    if (name in app && app[name] !== value) fail(`${name} in ${selector} is ${value}; the study app uses ${app[name]}.`);
  }
}

const story = JSON.parse(await readFile(path.join(paths.src, 'content/story.json'), 'utf8'));
const chapters = new Set(story.chapters.map(chapter => chapter.key));
// Screens cli.js derives from the recordings, and the series it builds for step-through pickers.
const frames = new Set(['installed', 'clients-picked', 'workflows-picked', 'login-opening', 'login-done']);
const sequences = new Set(['pick-agent', 'pick-workflows', 'login-pick']);
for (const host of story.hosts) {
  const recorded = JSON.parse(await readFile(path.join(paths.src, `content/cli/setup-${host.key}.json`), 'utf8'));
  for (const name of Object.keys(recorded)) frames.add(name);
}
for (const step of story.steps) {
  if (!chapters.has(step.chapter)) fail(`Step ${step.key} names an unknown chapter ${step.chapter}.`);
  for (const block of step.terminal?.blocks ?? []) {
    if (block.frame && !frames.has(block.frame)) fail(`Step ${step.key} shows an unknown terminal frame ${block.frame}.`);
    if (block.sequence && !sequences.has(block.sequence)) fail(`Step ${step.key} plays an unknown terminal sequence ${block.sequence}.`);
  }
  const files = [step.editor, ...(step.chat?.files ?? [])].filter(Boolean);
  for (const file of files) await stat(path.join(paths.course, file)).catch(() => fail(`Step ${step.key} shows ${file}, which the course does not contain.`));
  // Beats are chosen by scroll and play once the step's own part has played (stage.js).
  const opens = 0;
  let previous = opens;
  for (const beat of step.guide ?? []) {
    if (!step.app) fail(`Step ${step.key} has guide beats but no app view.`);
    if (!(beat.at > previous && beat.at < 1)) fail(`Step ${step.key} has a guide beat at ${beat.at}; beats must follow each other after ${opens} and before 1.`);
    const targets = [beat.target].flat();
    if (!targets.every(target => target?.css) || !beat.label || !beat.line) fail(`Step ${step.key} has a guide beat without a target, label or line.`);
    previous = beat.at;
  }
}
for (const chapter of story.chapters) if (!story.steps.some(step => step.chapter === chapter.key)) fail(`Chapter ${chapter.key} has no steps.`);

if (failures.length) {
  console.error(failures.map(message => `✗ ${message}`).join('\n'));
  process.exit(1);
}
console.log('✓ Size, self-containment, shared tokens and story consistency');
