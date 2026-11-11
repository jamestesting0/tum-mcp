// Builds a course project's study app into one HTML document for an iframe `srcdoc`.
//
// The app is the real bundled course app that `tum-mcp study build` installed into the
// project; this module only packs it. Its ES modules become one bundle, fonts and images
// become data URIs, and what the local preview serves (`tum-mcp study`: media indexes,
// media files, comments) is answered in the frame by a small shim.
import { execFile } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdir, readFile, stat } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { promisify } from 'node:util';
import { build } from 'esbuild';
import { previewIndexes } from './python.mjs';

const run = promisify(execFile);

// The page embeds smaller copies of the course's published media; the course keeps its own files.
const COMPACT = {
  '.mp4': ['-vf', 'scale=-2:720', '-c:v', 'libx264', '-preset', 'slow', '-crf', '30', '-c:a', 'aac', '-b:a', '64k', '-ac', '1', '-movflags', '+faststart'],
  '.m4a': ['-vn', '-c:a', 'aac', '-b:a', '64k', '-ac', '1', '-map_chapters', '0'],
};

async function compactMedia(file) {
  const args = COMPACT[path.extname(file)];
  if (!args) return file;
  const bytes = await readFile(file);
  const key = createHash('sha256').update(bytes).update(args.join(' ')).digest('hex').slice(0, 24);
  const target = path.join(tmpdir(), 'tum-mcp-walkthrough-media', `${key}${path.extname(file)}`);
  if (await stat(target).then(() => true, () => false)) return target;
  await mkdir(path.dirname(target), { recursive: true });
  await run('ffmpeg', ['-y', '-loglevel', 'error', '-i', file, ...args, target], { maxBuffer: 16 * 1024 * 1024 });
  return target;
}

const MIME = {
  '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2', '.mp4': 'video/mp4', '.m4a': 'audio/mp4', '.vtt': 'text/vtt',
  '.txt': 'text/plain', '.json': 'application/json',
};
const mime = file => MIME[path.extname(file).toLowerCase()] ?? 'application/octet-stream';

async function dataUri(file) {
  return `data:${mime(file)};base64,${(await readFile(file)).toString('base64')}`;
}

// Inline every `url(...)` that names a local file next to the stylesheet.
async function inlineUrls(css, directory) {
  const references = [...new Set([...css.matchAll(/url\((['"]?)([^'")#][^'")]*)\1\)/g)].map(match => match[2]))]
    .filter(reference => !/^(data:|https?:)/.test(reference));
  for (const reference of references) {
    css = css.replaceAll(reference, await dataUri(path.join(directory, reference)));
  }
  return css;
}

// `data.mjs` names lecture frames and figures by app-relative path; the frame has no files.
function inlineDataImages(app) {
  return {
    name: 'inline-data-images',
    setup(pluginBuild) {
      pluginBuild.onLoad({ filter: /[\\/]data\.mjs$/ }, async ({ path: file }) => {
        let source = await readFile(file, 'utf8');
        const images = new Set([...source.matchAll(/"([\w./-]+\.(?:png|jpe?g|webp|svg))"/g)].map(match => match[1]));
        for (const image of images) source = source.replaceAll(`"${image}"`, JSON.stringify(await dataUri(path.join(app, image))));
        return { contents: source, loader: 'js' };
      });
    },
  };
}

// Media named by the preview indexes, keyed by the path the app requests.
async function mediaFiles(project, indexes) {
  const files = {};
  const visit = value => {
    if (typeof value === 'string' && /^(videos|audio)\/[\w-]+\/[\w.-]+$/.test(value)) files[value] = null;
    else if (value && typeof value === 'object') Object.values(value).forEach(visit);
  };
  visit(indexes);
  for (const name of Object.keys(files)) {
    files[name] = [mime(name), (await readFile(await compactMedia(path.join(project, name)))).toString('base64')];
  }
  return files;
}

// Runs before the app: answers the local preview's requests from memory.
const SHIM = `(() => {
  // The tour's app keeps progress for this visit only. A local file shares storage with every
  // other local page, where a stale or unreadable value makes the app warn that progress cannot
  // be saved, and earlier answers would change what the tour shows. Items stay own enumerable
  // properties, as on a real Storage, so Object.keys(localStorage) still lists them.
  const storage = Object.create({
    get length() { return Object.keys(this).length; },
    key(index) { return Object.keys(this)[index] ?? null; },
    getItem(key) { return Object.hasOwn(this, key) ? this[key] : null; },
    setItem(key, value) { this[String(key)] = String(value); },
    removeItem(key) { delete this[String(key)]; },
    clear() { for (const key of Object.keys(this)) delete this[key]; },
  });
  Object.defineProperty(window, 'localStorage', { configurable: true, get: () => storage });
  const read = id => JSON.parse(document.getElementById(id).textContent);
  const files = read('app-files'), indexes = read('app-indexes'), identity = read('app-identity');
  const urls = new Map();
  const url = name => {
    if (!urls.has(name)) {
      const [type, base64] = files[name];
      const bytes = Uint8Array.from(atob(base64), character => character.charCodeAt(0));
      urls.set(name, URL.createObjectURL(new Blob([bytes], { type })));
    }
    return urls.get(name);
  };
  const local = value => JSON.parse(JSON.stringify(value), (key, item) => typeof item === 'string' && item in files ? url(item) : item);
  const json = (value, status = 200) => Promise.resolve(new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } }));
  const comments = { course_identity: identity, comments: [], revision: 'walkthrough' };
  const preview = fetch.bind(window);
  window.fetch = (input, init = {}) => {
    const route = new URL(typeof input === 'string' ? input : input.url, 'https://app.invalid/').pathname;
    if (route === '/videos/index.json') return json(local(indexes.videos));
    if (route === '/audio/index.json') return json(local(indexes.audio));
    if (route === '/_study/comments') {
      return (init.method || 'GET') === 'GET' ? json(comments) : json({ error: 'Comments are saved in your local app.' }, 503);
    }
    return preview(input, init);
  };
})();`;

const script = value => JSON.stringify(value).replaceAll('</', '<\\/');

/** Returns the complete app document and its size details. */
export async function appDocument({ project, repo }) {
  const app = path.join(project, 'app');
  const [bundle, katexCss, appCss, katexJs, template, indexes] = await Promise.all([
    build({
      entryPoints: [path.join(app, 'runtime/shell/start.mjs')], bundle: true, format: 'esm', write: false,
      minify: true, target: 'es2022', legalComments: 'none', plugins: [inlineDataImages(app)], logLevel: 'silent',
    }),
    readFile(path.join(app, 'assets/katex/katex.min.css'), 'utf8'),
    readFile(path.join(app, 'styles.css'), 'utf8'),
    readFile(path.join(app, 'assets/katex/katex.min.js'), 'utf8'),
    readFile(path.join(app, 'index.html'), 'utf8'),
    previewIndexes({ project, repo }),
  ]);
  const css = (await inlineUrls(katexCss, path.join(app, 'assets/katex'))) + (await inlineUrls(appCss, app));
  const files = await mediaFiles(project, indexes);
  const identity = JSON.parse((await readFile(path.join(app, 'data.mjs'), 'utf8')).match(/"identity":("[^"]+")/)[1]);
  const body = template.slice(template.indexOf('<body>') + 6, template.indexOf('</body>'));
  const js = bundle.outputFiles[0].text;
  // A srcdoc page otherwise inherits the tour page's base URL: its '#' links would load the tour
  // into the frame and history.replaceState('#...') would throw.
  const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><base href="about:srcdoc">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="color-scheme" content="light dark">
<title>Course</title><style>${css}</style>
<script type="application/json" id="app-files">${script(files)}</script>
<script type="application/json" id="app-indexes">${script(indexes)}</script>
<script type="application/json" id="app-identity">${script(identity)}</script>
<script>${SHIM}</script><script>${katexJs.replaceAll('</script', '<\\/script')}</script>
<script type="module">${js.replaceAll('</script', '<\\/script')}</script>
</head><body>${body}</body></html>`;
  return { html, sizes: { total: html.length, script: js.length, css: css.length, media: JSON.stringify(files).length } };
}
