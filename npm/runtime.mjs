import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';
import { chmod, mkdir, mkdtemp, rename, rm, writeFile } from 'node:fs/promises';
import { homedir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { download } from './download.mjs';

const packageRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const pins = JSON.parse(readFileSync(join(packageRoot, 'npm/uv-artifacts.json'), 'utf8'));

export function dataRoot() {
  if (process.env.TUM_MCP_DATA_DIR) return process.env.TUM_MCP_DATA_DIR;
  if (process.platform === 'darwin') return join(homedir(), 'Library/Application Support/TUMMCP');
  if (process.platform === 'win32') return join(process.env.LOCALAPPDATA || join(homedir(), 'AppData/Local'), 'TUMMCP');
  return join(process.env.XDG_DATA_HOME || join(homedir(), '.local/share'), 'TUMMCP');
}

function run(executable, args) {
  const env = { ...process.env };
  delete env.VIRTUAL_ENV; delete env.PYTHONPATH; delete env.PYTHONHOME;
  const result = spawnSync(executable, args, { env, stdio: ['ignore', 'inherit', 'inherit'], shell: false, timeout: 600000 });
  if (result.error) throw new Error(`Managed runtime subprocess could not start (${result.error.code || 'unknown'}); check executable permissions and mount options.`);
  if (result.status !== 0) throw new Error('Managed runtime setup failed; inspect the diagnostics above.');
}

export function currentPython() {
  try {
    const current = JSON.parse(readFileSync(join(dataRoot(), 'runtime.json'), 'utf8'));
    if (!/^[a-f0-9]{64}$/.test(current.identity)) return null;
    const manifest = JSON.parse(readFileSync(join(packageRoot, 'npm/backend/manifest.json'), 'utf8'));
    if (current.identity !== manifest.wheelSha256) return null;
    const runtime = join(dataRoot(), 'runtimes', current.identity);
    const expected = join(runtime, process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
    if (current.python !== expected || !existsSync(expected)) return null;
    if (readFileSync(join(runtime, '.tum-mcp-ready'), 'utf8') !== current.identity) return null;
    return expected;
  } catch { return null; }
}

function matchingUv(executable) {
  const found = spawnSync(executable, ['--version'], { encoding: 'utf8', shell: false, timeout: 10000 });
  return found.status === 0 && found.stdout.trim().split(' ')[1] === pins.version;
}

export async function ensureRuntime() {
  const backend = join(packageRoot, 'npm/backend');
  const manifest = JSON.parse(readFileSync(join(backend, 'manifest.json'), 'utf8'));
  if (!/^[a-zA-Z0-9_.-]+\.whl$/.test(manifest.wheel)) throw new Error('Invalid backend manifest.');
  for (const [name, expected] of [[manifest.wheel, manifest.wheelSha256], ['requirements.txt', manifest.requirementsSha256]]) {
    if (createHash('sha256').update(readFileSync(join(backend, name))).digest('hex') !== expected) throw new Error('Backend integrity check failed.');
  }
  const identity = manifest.wheelSha256;
  const runtime = join(dataRoot(), 'runtimes', identity);
  const python = join(runtime, process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  await mkdir(dataRoot(), { recursive: true, mode: 0o700 });
  // A per-runtime directory lock prevents concurrent setup from corrupting a venv.
  const lock = join(dataRoot(), 'setup.lock');
  try { await mkdir(lock, { mode: 0o700 }); }
  catch (error) { if (error.code === 'EEXIST') throw new Error('Another setup is running; retry when it finishes.'); throw error; }
  try {
    const ready = join(runtime, '.tum-mcp-ready');
    if (!existsSync(python) || !existsSync(ready) || readFileSync(ready, 'utf8') !== identity) {
      const cachedUv = join(dataRoot(), process.platform === 'win32' ? 'uv.exe' : 'uv');
      let uv = matchingUv('uv') ? 'uv' : matchingUv(cachedUv) ? cachedUv : null;
      if (!uv) {
        const systems = { darwin: 'apple-darwin', linux: 'unknown-linux-gnu', win32: 'pc-windows-msvc' };
        const arches = { arm64: 'aarch64', x64: 'x86_64' };
        const target = `${arches[process.arch]}-${systems[process.platform]}`;
        const artifact = pins.artifacts[target];
        if (!artifact) throw new Error('Unsupported platform/architecture; use a documented manual installation.');
        const temporary = await mkdtemp(join(dataRoot(), 'bootstrap-'));
        try {
          const archive = join(temporary, process.platform === 'win32' ? 'uv.zip' : 'uv.tar.gz');
          await download(artifact.url, archive, artifact.sha256);
          run('tar', ['-xf', archive, '-C', temporary]);
          const extracted = process.platform === 'win32' ? join(temporary, 'uv.exe') : join(temporary, `uv-${target}`, 'uv');
          uv = join(dataRoot(), process.platform === 'win32' ? 'uv.exe' : 'uv');
          await rename(extracted, uv); if (process.platform !== 'win32') await chmod(uv, 0o700);
        } finally { await rm(temporary, { recursive: true, force: true }); }
      }
      await mkdir(dirname(runtime), { recursive: true, mode: 0o700 });
      if (existsSync(runtime)) await rm(runtime, { recursive: true, force: true });
      run(uv, ['venv', '--managed-python', '--python', pins.python, runtime]);
      run(uv, ['pip', 'sync', '--python', python, '--require-hashes', '--only-binary', ':all:', join(backend, 'requirements.txt')]);
      run(uv, ['pip', 'install', '--python', python, '--no-deps', '--no-index', join(backend, manifest.wheel)]);
    }
    try { run(python, ['-I', '-m', 'tum_mcp', 'version']); }
    catch (error) { await rm(ready, { force: true }); throw error; }
    await writeFile(ready, identity, { mode: 0o600 });
    await writeFile(join(dataRoot(), 'runtime.pending.json'), JSON.stringify({ identity, python }), { mode: 0o600 });
    await rename(join(dataRoot(), 'runtime.pending.json'), join(dataRoot(), 'runtime.json'));
    return python;
  } finally { await rm(lock, { recursive: true, force: true }); }
}
