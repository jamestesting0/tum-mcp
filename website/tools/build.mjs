// Builds dist/tum-mcp-walkthrough.html: the page, its styles and scripts, the brand assets and
// the live study app of the synthetic course, all inlined into one file.
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { build as bundle, transform } from 'esbuild';
import { appDocument } from './lib/app-document.mjs';
import { chapterParts, commandList, credits, hostTabs, paletteCss } from './lib/page-parts.mjs';
import { paths } from './lib/paths.mjs';

const read = (...parts) => readFile(path.join(...parts), 'utf8');
const base64 = async file => (await readFile(file)).toString('base64');
const OUTPUT = path.join(paths.dist, 'tum-mcp-walkthrough.html');
const STYLES = ['tokens.css', 'page.css', 'hosts/signin.css', 'stage.css', 'hosts/workbench.css', 'hosts/chat.css', 'hosts/terminal.css', 'phone.css'];

async function codiconMap() {
  const css = await read(paths.website, 'node_modules/@vscode/codicons/dist/codicon.css');
  const map = {};
  for (const [, name, code] of css.matchAll(/\.codicon-([a-z0-9-]+):before\s*\{\s*content:\s*"\\([0-9a-f]+)"/g)) map[name] = String.fromCodePoint(Number.parseInt(code, 16));
  return map;
}

async function courseFiles(story) {
  const wanted = new Set(story.steps.flatMap(step => [step.editor, ...(step.chat?.messages ?? []).filter(item => item.kind === 'edit').map(item => item.name)]).filter(Boolean));
  const files = {};
  for (const file of wanted) {
    const text = await read(paths.course, file);
    const lines = text.replace(/\n$/, '').split('\n');
    files[file] = { text: lines.slice(0, 48).join('\n'), lines: lines.length };
  }
  return files;
}

async function marks() {
  const hosts = path.join(paths.src, 'assets/hosts');
  const [codexLight, codexDark, claude, cursor, antigravity] = await Promise.all(
    ['codex-light.svg', 'codex-dark.svg', 'claude.svg', 'cursor.svg', 'antigravity.svg'].map(file => read(hosts, file)));
  return { codexLight, codexDark, claude, cursor, antigravity, letterpress: {} };
}

function virtualModules(modules) {
  return {
    name: 'virtual-modules',
    setup(build) {
      build.onResolve({ filter: /^virtual:/ }, args => ({ path: args.path, namespace: 'virtual' }));
      build.onLoad({ filter: /.*/, namespace: 'virtual' }, args => ({ contents: JSON.stringify(modules[args.path]), loader: 'json' }));
    },
  };
}

const scriptSafe = text => text.replaceAll('</script', '<\\/script');
const jsonSafe = text => text.replaceAll('</', '<\\/').replaceAll('<!--', '<\\u0021--');

export async function buildPage() {
  const story = JSON.parse(await read(paths.src, 'content/story.json'));
  const references = JSON.parse(await read(paths.references, 'editor-themes.json'));
  const [icons, files, brand, app] = await Promise.all([codiconMap(), courseFiles(story), marks(), appDocument({ project: paths.course, repo: paths.repo })]);

  const script = await bundle({
    entryPoints: [path.join(paths.src, 'scripts/main.js')], bundle: true, write: false, format: 'iife', minify: true, target: 'es2022', legalComments: 'none', logLevel: 'silent',
    plugins: [virtualModules({ 'virtual:codicons': icons, 'virtual:course-files': files, 'virtual:marks': brand })],
  });

  const fonts = [
    `@font-face { font-family: 'Atkinson Hyperlegible Next'; font-weight: 200 800; font-display: swap; src: url(data:font/woff2;base64,${await base64(path.join(paths.appSite, 'assets/fonts/font-sans-latin.woff2'))}) format('woff2'); unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215; }`,
    `@font-face { font-family: 'Atkinson Hyperlegible Next'; font-weight: 200 800; font-display: swap; src: url(data:font/woff2;base64,${await base64(path.join(paths.appSite, 'assets/fonts/font-sans-latin-ext.woff2'))}) format('woff2'); unicode-range: U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+1E00-1E9F, U+2020, U+20A0-20AB, U+20AD-20C4, U+2C60-2C7F, U+A720-A7FF; }`,
    `@font-face { font-family: codicon; font-display: block; src: url(data:font/ttf;base64,${await base64(path.join(paths.website, 'node_modules/@vscode/codicons/dist/codicon.ttf'))}) format('truetype'); }`,
  ];
  const css = [...fonts, ...(await Promise.all(STYLES.map(file => read(paths.src, 'styles', file)))), paletteCss(references)].join('\n');
  const styles = (await transform(css, { loader: 'css', minify: true, logLevel: 'silent' })).code;

  const brandDir = path.join(paths.src, 'assets/brand');
  const parts = chapterParts(story);
  const fills = {
    favicon: `data:image/svg+xml;base64,${await base64(path.join(brandDir, 'favicon.svg'))}`,
    appleIcon: `data:image/png;base64,${await base64(path.join(brandDir, 'app-icon-180.png'))}`,
    themeBoot: "(()=>{let t;try{t=localStorage.getItem('tum-mcp-walkthrough:theme')}catch{}document.documentElement.dataset.theme=t||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light')})()",
    styles,
    markInline: (await read(brandDir, 'mark.svg')).replace('<svg ', '<svg aria-hidden="true" ').replace(' role="img" aria-label="TUM MCP"', ''),
    title: story.title,
    hostTabs: hostTabs(story),
    chapterAnchors: parts.anchors,
    chapterLinks: parts.links,
    commands: commandList(story),
    credits,
    appDocument: jsonSafe(JSON.stringify(app.html)),
    script: scriptSafe(script.outputFiles[0].text),
  };
  const template = await read(paths.src, 'index.html');
  const html = template.replace(/\{\{(\w+)\}\}/g, (match, key) => {
    if (!(key in fills)) throw new Error(`index.html names an unknown part: ${key}`);
    return fills[key];
  });
  return { html, sizes: { total: html.length, app: app.sizes, script: fills.script.length, styles: styles.length } };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const { html, sizes } = await buildPage();
  await mkdir(paths.dist, { recursive: true });
  await writeFile(OUTPUT, html);
  const mb = bytes => `${(bytes / 1024 / 1024).toFixed(2)} MB`;
  console.log(`${path.relative(paths.website, OUTPUT)}  ${mb(sizes.total)} (app ${mb(sizes.app.total)}, script ${mb(sizes.script)}, styles ${mb(sizes.styles)})`);
}
