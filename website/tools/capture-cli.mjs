// Records the real `tum-mcp setup` screens for every coding app and stores them as styled
// transcripts in src/content/cli/. Each run uses a throwaway HOME; nothing touches the real
// profile, and the workflow step is cancelled before anything installs.
import { execFile } from 'node:child_process';
import { chmod, mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { promisify } from 'node:util';
import { paths } from './lib/paths.mjs';

const run = promisify(execFile);
const binary = path.join(paths.repo, '.venv/bin/tum-mcp');
const script = path.join(paths.website, 'tools/capture/setup_screens.py');
const loginScript = path.join(paths.website, 'tools/capture/login_screens.py');
const python = path.join(paths.repo, '.venv/bin/python');
const hosts = ['codex', 'claude', 'cursor', 'antigravity'];
const STYLE = { cyan: 'accent', green: 'ready', blue: 'configured', brown: 'attention', yellow: 'attention', red: 'failed', brightblack: 'muted' };

// pyte keeps each screen as cells; a line becomes runs of [text, style].
function spans(row) {
  const runs = [];
  for (const [text, colour, bold] of row) {
    const style = STYLE[colour] ?? (bold ? 'bold' : '');
    const last = runs.at(-1);
    if (last && last[1] === style) last[0] += text;
    else runs.push([text, style]);
  }
  const trimmed = runs.map(([text, style]) => [text, style]);
  while (trimmed.length && !trimmed.at(-1)[0].trim()) trimmed.pop();
  if (trimmed.length) trimmed[trimmed.length - 1][0] = trimmed.at(-1)[0].trimEnd();
  return trimmed;
}

// pyte answers no cursor-position requests, so prompt_toolkit prints a warning a real
// terminal never shows; it is dropped along with trailing blank lines.
function lines(screen) {
  const result = screen.map(spans).filter(line => !line.map(([text]) => text).join('').startsWith('WARNING: your terminal'));
  while (result.length && !result.at(-1).length) result.pop();
  return result;
}

async function capture(host, row) {
  const home = await mkdtemp(path.join(tmpdir(), `tum-mcp-capture-${host}-`));
  try {
    await mkdir(path.join(home, 'bin'));
    // Setup only offers installed apps; a stub stands in for an app missing on this machine.
    for (const name of hosts.filter(name => name !== 'codex')) {
      const stub = path.join(home, 'bin', name);
      await writeFile(stub, '#!/bin/sh\nexit 0\n');
      await chmod(stub, 0o755);
    }
    const out = path.join(home, 'screens.json');
    await run('uv', ['run', '--no-project', '--quiet', '--with', 'pyte', 'python', script, binary, out, String(row), home], { timeout: 180000 });
    const screens = JSON.parse(await readFile(out, 'utf8'));
    return Object.fromEntries(Object.entries(screens).map(([name, screen]) => [name, lines(screen)]));
  } finally {
    await rm(home, { recursive: true, force: true });
  }
}

// The login pickers, cancelled at the browser list: no browser opens and no account is used.
async function captureLogin() {
  const home = await mkdtemp(path.join(tmpdir(), 'tum-mcp-capture-login-'));
  try {
    const out = path.join(home, 'screens.json');
    await run('uv', ['run', '--no-project', '--quiet', '--with', 'pyte', 'python', loginScript, binary, python, out, home], { timeout: 180000 });
    const screens = JSON.parse(await readFile(out, 'utf8'));
    if (!lines(screens.cancelled).some(line => line.map(([text]) => text).join('').includes('No browser was opened'))) {
      throw new Error('The login capture did not end at the browser list.');
    }
    return Object.fromEntries(['services', 'services-selected', 'browser'].map(name => [name, lines(screens[name])]));
  } finally {
    await rm(home, { recursive: true, force: true });
  }
}

const target = path.join(paths.src, 'content/cli');
await mkdir(target, { recursive: true });
const login = await captureLogin();
await writeFile(path.join(target, 'login.json'), `${JSON.stringify({ source: 'Recorded by tools/capture-cli.mjs from `tum-mcp login` in a throwaway HOME with Lecture on; cancelled at the browser list, so no browser opened.', screens: login }, null, 1)}\n`);
console.log('login.json', Object.keys(login).join(', '));
// `--login` re-records only the login screens and leaves the setup transcripts as they are.
if (!process.argv.includes('--login')) {
  const results = await Promise.all(hosts.map((host, row) => capture(host, row)));
  for (const [index, host] of hosts.entries()) {
    await writeFile(path.join(target, `setup-${host}.json`), `${JSON.stringify(results[index], null, 1)}\n`);
    console.log(`setup-${host}.json`, Object.keys(results[index]).join(', '));
  }
}
