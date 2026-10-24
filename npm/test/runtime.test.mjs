import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { existsSync, mkdtempSync, mkdirSync, readFileSync, realpathSync, rmSync, writeFileSync } from 'node:fs';
import { homedir, hostname, tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { acquireSetupLock, currentPython, dataRoot, runtimeIdentity } from '../runtime.mjs';

function isolated(action) {
  const root = realpathSync(mkdtempSync(join(tmpdir(), 'tum-mcp-runtime-')));
  const previous = process.env.TUM_MCP_DATA_DIR;
  process.env.TUM_MCP_DATA_DIR = root;
  return Promise.resolve().then(() => action(root)).finally(() => {
    if (previous === undefined) delete process.env.TUM_MCP_DATA_DIR;
    else process.env.TUM_MCP_DATA_DIR = previous;
    rmSync(root, { recursive: true, force: true });
  });
}

test('runtime selection rejects incomplete or corrupt state and survives another version becoming current', () => isolated(root => {
  assert.equal(currentPython(), null);
  const identity = runtimeIdentity();
  const control = join(root, 'runtimes', identity);
  const runtime = join(control, 'env-fixture');
  const python = join(runtime, process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  mkdirSync(dirname(python), { recursive: true });
  writeFileSync(python, 'synthetic binary never executed');
  const selected = { schema: 2, identity, generation: 'env-fixture', python };
  const pointer = join(control, 'current.json');
  writeFileSync(pointer, JSON.stringify(selected));
  assert.equal(currentPython(), null);
  writeFileSync(join(runtime, '.tum-mcp-ready'), identity);
  assert.equal(currentPython(), python);
  // A different installed package must not invalidate this package's retained runtime.
  writeFileSync(join(root, 'runtime.json'), JSON.stringify({ identity: 'a'.repeat(64), python: '/other/python' }));
  assert.equal(currentPython(), python);
  for (const value of ['{interrupted', JSON.stringify({ ...selected, generation: '../outside' }), JSON.stringify({ ...selected, identity: 'a'.repeat(64) })]) {
    writeFileSync(pointer, value);
    assert.equal(currentPython(), null);
  }
}));

test('dependency pin changes produce a different runtime even if the wheel is unchanged', () => {
  const manifest = JSON.parse(readFileSync(new URL('../backend/manifest.json', import.meta.url)));
  assert.notEqual(runtimeIdentity(manifest), runtimeIdentity({ ...manifest, requirementsSha256: 'a'.repeat(64) }));
});

test('data paths expand the current user home consistently with the backend', () => isolated(() => {
  process.env.TUM_MCP_DATA_DIR = '~/tum-update-fixture';
  assert.equal(dataRoot(), join(realpathSync(homedir()), 'tum-update-fixture'));
}));

test('an active setup lock is preserved', () => isolated(async () => {
  const release = await acquireSetupLock();
  await assert.rejects(acquireSetupLock(), /Another setup is running/);
  await release();
}));

test('a stopped setup owner is recovered without reusing its unfinished runtime', () => isolated(async root => {
  const child = spawnSync(process.execPath, ['-p', 'process.pid'], { encoding: 'utf8' });
  assert.equal(child.status, 0);
  const lock = join(root, 'setup.lock');
  mkdirSync(lock);
  writeFileSync(join(lock, 'owner.json'), JSON.stringify({ pid: Number(child.stdout.trim()), host: hostname(), nonce: 'stopped-owner' }));
  const release = await acquireSetupLock();
  assert.equal(JSON.parse(readFileSync(join(lock, 'owner.json'))).pid, process.pid);
  await release();
}));

test('unknown legacy setup locks are never removed automatically', () => isolated(async root => {
  mkdirSync(join(root, 'setup.lock'));
  await assert.rejects(acquireSetupLock(), /no readable owner/);
  assert.ok(existsSync(join(root, 'setup.lock')));
}));

async function removalFixture(root) {
  const { removeRuntimeFiles } = await import('../runtime.mjs');
  const identity = 'b'.repeat(64);
  const runtime = join(root, 'runtimes', identity);
  mkdirSync(runtime, { recursive: true });
  writeFileSync(join(runtime, 'runtime-owner.json'), JSON.stringify({ kind: 'tum-mcp-runtime', schema: 2, identity }));
  writeFileSync(join(root, 'runtime-removal.pending'), 'explicit-runtime-removal');
  return { removeRuntimeFiles, runtime, identity };
}

test('explicit runtime removal keeps credentials and user work', () => isolated(async root => {
  const { removeRuntimeFiles, runtime, identity } = await removalFixture(root);
  mkdirSync(join(root, 'workspaces')); mkdirSync(join(root, 'credentials'));
  writeFileSync(join(root, 'workspaces/assignment.txt'), 'user work');
  writeFileSync(join(root, 'credentials/session.key'), 'synthetic-key');
  writeFileSync(join(root, 'runtime.json'), JSON.stringify({ identity, python: join(runtime, 'env-fixture/bin/python') }));
  await removeRuntimeFiles();
  assert.equal(existsSync(runtime), false);
  assert.equal(readFileSync(join(root, 'workspaces/assignment.txt'), 'utf8'), 'user work');
  assert.equal(readFileSync(join(root, 'credentials/session.key'), 'utf8'), 'synthetic-key');
  assert.equal(existsSync(join(root, 'runtime.json')), false);
}));

test('unknown runtime files stop cleanup before any verified runtime is deleted', () => isolated(async root => {
  const { removeRuntimeFiles, runtime } = await removalFixture(root);
  mkdirSync(join(root, 'runtimes/user-work'));
  writeFileSync(join(root, 'runtimes/user-work/retain.txt'), 'personal');
  await assert.rejects(removeRuntimeFiles(), /Unrecognized runtime/);
  assert.ok(existsSync(runtime));
  assert.equal(readFileSync(join(root, 'runtimes/user-work/retain.txt'), 'utf8'), 'personal');
}));

test('corrupt runtime metadata is rejected before cleanup changes files', () => isolated(async root => {
  const { removeRuntimeFiles, runtime } = await removalFixture(root);
  writeFileSync(join(root, 'runtime.json'), '{interrupted');
  await assert.rejects(removeRuntimeFiles(), /selection metadata is unreadable/);
  assert.ok(existsSync(runtime));
}));
