import { spawnSync } from 'node:child_process';
import { createHash, randomUUID } from 'node:crypto';
import { existsSync, lstatSync, readFileSync, readdirSync, realpathSync } from 'node:fs';
import { chmod, mkdir, mkdtemp, rename, rm, rmdir, writeFile } from 'node:fs/promises';
import { homedir, hostname } from 'node:os';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { download } from './download.mjs';

const packageRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const pins = JSON.parse(readFileSync(join(packageRoot, 'npm/uv-artifacts.json'), 'utf8'));
const packageVersion = JSON.parse(readFileSync(join(packageRoot, 'package.json'), 'utf8')).version;

export function dataRoot() {
  let path = process.env.TUM_MCP_DATA_DIR;
  if (!path) {
    if (process.platform === 'darwin') path = join(homedir(), 'Library/Application Support/TUMMCP');
    else if (process.platform === 'win32') path = join(process.env.LOCALAPPDATA || join(homedir(), 'AppData/Local'), 'TUMMCP');
    else path = join(process.env.XDG_DATA_HOME || join(homedir(), '.local/share'), 'TUMMCP');
  }
  path = resolve(path.replace(/^~(?=$|[/\\])/, homedir()));
  const tail = [];
  while (!existsSync(path)) { tail.unshift(basename(path)); path = dirname(path); }
  return join(realpathSync(path), ...tail);
}

function manifest() {
  const value = JSON.parse(readFileSync(join(packageRoot, 'npm/backend/manifest.json'), 'utf8'));
  if (!/^[a-zA-Z0-9_.-]+\.whl$/.test(value.wheel) ||
      !/^[a-f0-9]{64}$/.test(value.wheelSha256) || !/^[a-f0-9]{64}$/.test(value.requirementsSha256)) {
    throw new Error('Invalid backend manifest; reinstall the npm package.');
  }
  return value;
}

export function runtimeIdentity(value = manifest()) {
  return createHash('sha256').update(JSON.stringify({ schema: 2, wheel: value.wheelSha256,
    requirements: value.requirementsSha256, python: pins.python })).digest('hex');
}

function controlDirectory(identity) { return join(dataRoot(), 'runtimes', identity); }
function pythonPath(runtime) { return join(runtime, process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python'); }

export function currentPython() {
  try {
    const identity = runtimeIdentity();
    const control = controlDirectory(identity);
    const selected = JSON.parse(readFileSync(join(control, 'current.json'), 'utf8'));
    if (selected.schema !== 2 || selected.identity !== identity || !/^env-[a-zA-Z0-9]+$/.test(selected.generation)) return null;
    const runtime = join(control, selected.generation);
    const expected = pythonPath(runtime);
    if (selected.python !== expected || !existsSync(expected)) return null;
    if ([join(dataRoot(), 'runtimes'), control, runtime, join(runtime, '.tum-mcp-ready')].some(path => lstatSync(path).isSymbolicLink())) return null;
    if (readFileSync(join(runtime, '.tum-mcp-ready'), 'utf8') !== identity) return null;
    return expected;
  } catch { return null; }
}

function run(executable, args, { quiet = false, timeout = 600000 } = {}) {
  const env = { ...process.env }; delete env.VIRTUAL_ENV; delete env.PYTHONPATH; delete env.PYTHONHOME;
  const result = spawnSync(executable, args, { env, stdio: quiet ? ['ignore', 'pipe', 'pipe'] : ['ignore', 'inherit', 'inherit'], shell: false, timeout });
  if (result.error) throw new Error(`Managed runtime subprocess could not start (${result.error.code || 'unknown'}); check permissions and retry setup.`);
  if (result.status !== 0) throw new Error('Managed runtime setup failed; the previous runtime was retained.');
  return result;
}

function healthy(python) {
  try {
    const result = run(python, ['-I', '-c', 'from tum_mcp.server import server; from tum_mcp import __version__; print(__version__)'], { quiet: true, timeout: 30000 });
    return result.stdout.toString().trim() === packageVersion;
  } catch { return false; }
}

async function atomicWrite(path, data) {
  const temporary = `${path}.${randomUUID()}.pending`;
  try {
    await writeFile(temporary, data, { mode: 0o600, flag: 'wx' });
    await rename(temporary, path);
  } finally { await rm(temporary, { force: true }); }
}

function matchingUv(executable) {
  const found = spawnSync(executable, ['--version'], { encoding: 'utf8', shell: false, timeout: 10000 });
  return found.status === 0 && found.stdout.trim().split(' ')[1] === pins.version;
}

async function uvExecutable() {
  const cached = join(dataRoot(), process.platform === 'win32' ? 'uv.exe' : 'uv');
  if (matchingUv('uv')) return 'uv';
  if (matchingUv(cached)) {
    await atomicWrite(join(dataRoot(), 'uv-owner.json'), JSON.stringify({ sha256: createHash('sha256').update(readFileSync(cached)).digest('hex') }));
    return cached;
  }
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
    await rename(extracted, cached);
    if (process.platform !== 'win32') await chmod(cached, 0o700);
  } finally { await rm(temporary, { recursive: true, force: true }); }
  await atomicWrite(join(dataRoot(), 'uv-owner.json'), JSON.stringify({ sha256: createHash('sha256').update(readFileSync(cached)).digest('hex') }));
  return cached;
}

export async function acquireSetupLock() {
  const lock = join(dataRoot(), 'setup.lock');
  const owner = { pid: process.pid, host: hostname(), nonce: randomUUID() };
  const guard = join(dataRoot(), 'setup.claim');
  try { await mkdir(guard, { mode: 0o700 }); }
  catch { throw new Error('Another setup is claiming the lock. Retry; an interrupted setup.claim needs local review.'); }
  try {
  try { await mkdir(lock, { mode: 0o700 }); }
  catch (error) {
    if (error.code !== 'EEXIST') throw error;
    let previous;
    try { previous = JSON.parse(readFileSync(join(lock, 'owner.json'), 'utf8')); }
    catch { throw new Error('Setup lock has no readable owner. Confirm no setup is running before removing setup.lock.'); }
    if (!Number.isSafeInteger(previous.pid) || previous.pid <= 0 || previous.host !== hostname()) {
      throw new Error('Setup lock belongs to an unknown owner; preserve it for local review.');
    }
    let alive = true;
    try { process.kill(previous.pid, 0); }
    catch (failure) { if (failure.code === 'ESRCH') alive = false; }
    if (alive) throw new Error('Another setup is running; retry when it finishes.');
    const abandoned = `${lock}.${randomUUID()}.abandoned`;
    await rename(lock, abandoned);
    await rm(abandoned, { recursive: true, force: true });
    try { await mkdir(lock, { mode: 0o700 }); }
    catch { throw new Error('Another setup acquired the lock; retry when it finishes.'); }
  }
  await atomicWrite(join(lock, 'owner.json'), JSON.stringify(owner));
  } finally { await rmdir(guard); }
  return async () => {
    const current = JSON.parse(readFileSync(join(lock, 'owner.json'), 'utf8'));
    if (current.nonce !== owner.nonce) throw new Error('Setup lock ownership changed; it was preserved.');
    await rm(lock, { recursive: true, force: true });
  };
}

export async function ensureRuntime() {
  const backend = join(packageRoot, 'npm/backend');
  const value = manifest();
  for (const [name, expected] of [[value.wheel, value.wheelSha256], ['requirements.txt', value.requirementsSha256]]) {
    if (createHash('sha256').update(readFileSync(join(backend, name))).digest('hex') !== expected) throw new Error('Backend integrity check failed.');
  }
  const identity = runtimeIdentity(value);
  await mkdir(dataRoot(), { recursive: true, mode: 0o700 });
  const release = await acquireSetupLock();
  let preparing;
  try {
    let python = currentPython();
    if (!python || !healthy(python)) {
      const uv = await uvExecutable();
      const control = controlDirectory(identity);
      for (const path of [join(dataRoot(), 'runtimes'), control]) {
        if (existsSync(path) && lstatSync(path).isSymbolicLink()) throw new Error('Symbolic runtime directory preserved; review it locally.');
      }
      await mkdir(control, { recursive: true, mode: 0o700 });
      await atomicWrite(join(control, 'runtime-owner.json'), JSON.stringify({ kind: 'tum-mcp-runtime', schema: 2, identity }));
      preparing = await mkdtemp(join(control, 'env-'));
      python = pythonPath(preparing);
      run(uv, ['venv', '--managed-python', '--python', pins.python, preparing]);
      run(uv, ['pip', 'sync', '--python', python, '--require-hashes', '--only-binary', ':all:', join(backend, 'requirements.txt')]);
      run(uv, ['pip', 'install', '--python', python, '--no-deps', '--no-index', join(backend, value.wheel)]);
      if (!healthy(python)) throw new Error('New runtime validation failed; the previous runtime was retained.');
      await atomicWrite(join(preparing, '.tum-mcp-ready'), identity);
      const selected = JSON.stringify({ schema: 2, identity, generation: basename(preparing), python });
      await atomicWrite(join(control, 'current.json'), selected);
      // Published generations are never removed: existing clients may still pin one.
      preparing = undefined;
      await atomicWrite(join(dataRoot(), 'runtime.json'), selected);
    }
    const selected = readFileSync(join(controlDirectory(identity), 'current.json'), 'utf8');
    const global = join(dataRoot(), 'runtime.json');
    if (!existsSync(global) || readFileSync(global, 'utf8') !== selected) await atomicWrite(global, selected);
    await rm(join(dataRoot(), 'runtime-removal.pending'), { force: true });
    return python;
  } finally {
    try { if (preparing) await rm(preparing, { recursive: true, force: true }); }
    finally { await release(); }
  }
}


export async function removeRuntimeFiles() {
  const root = dataRoot();
  const directory = join(root, 'runtimes');
  if (!existsSync(join(root, 'runtime-removal.pending'))) throw new Error('Runtime removal must be requested with uninstall --all --purge-runtime.');
  const owned = [];
  if (existsSync(directory)) {
    if (lstatSync(directory).isSymbolicLink()) throw new Error('Symbolic runtime directory preserved for review.');
    for (const name of readdirSync(directory)) {
      const runtime = join(directory, name);
      if (!/^[a-f0-9]{64}$/.test(name) || lstatSync(runtime).isSymbolicLink()) throw new Error('Unrecognized runtime files were preserved for review.');
      let verified = false;
      const owner = join(runtime, 'runtime-owner.json');
      if (existsSync(owner) && !lstatSync(owner).isSymbolicLink()) {
        const record = JSON.parse(readFileSync(owner, 'utf8'));
        verified = record.kind === 'tum-mcp-runtime' && record.schema === 2 && record.identity === name;
      }
      const legacy = join(runtime, '.tum-mcp-ready');
      if (!verified && existsSync(legacy) && !lstatSync(legacy).isSymbolicLink()) verified = readFileSync(legacy, 'utf8') === name;
      if (!verified) throw new Error('Runtime ownership could not be verified; files were preserved.');
      owned.push(runtime);
    }
  }
  const pointer = join(root, 'runtime.json');
  let removePointer = false;
  if (existsSync(pointer)) {
    let current;
    try { current = JSON.parse(readFileSync(pointer, 'utf8')); }
    catch { throw new Error('Runtime selection metadata is unreadable; runtimes were preserved. Run setup to repair it.'); }
    removePointer = /^[a-f0-9]{64}$/.test(current.identity) && owned.includes(join(directory, current.identity));
  }
  // All candidates are checked before deletion; never remove the campus data root.
  for (const runtime of owned) await rm(runtime, { recursive: true });
  if (existsSync(directory) && readdirSync(directory).length === 0) await rmdir(directory);
  if (removePointer) await rm(pointer);
  const uv = join(root, process.platform === 'win32' ? 'uv.exe' : 'uv');
  const uvOwner = join(root, 'uv-owner.json');
  if (existsSync(uvOwner) && existsSync(uv)) {
    const expected = JSON.parse(readFileSync(uvOwner, 'utf8')).sha256;
    if (!lstatSync(uv).isSymbolicLink() && createHash('sha256').update(readFileSync(uv)).digest('hex') === expected) {
      await rm(uv); await rm(uvOwner);
    } else console.error('Modified bootstrap cache was preserved for local review.');
  }
  const leases = join(root, 'runtime-leases');
  if (existsSync(leases) && !lstatSync(leases).isSymbolicLink()) {
    for (const name of readdirSync(leases)) {
      const lock = join(leases, name);
      if (/^[a-f0-9]{32}\.lock$/.test(name) && !lstatSync(lock).isSymbolicLink()) await rm(lock);
    }
    if (readdirSync(leases).length === 0) await rmdir(leases);
  }
  await rm(join(root, 'runtime-removal.pending'), { force: true });
  console.log(`Removed ${owned.length} managed runtime(s). Saved user data was retained.`);
}
