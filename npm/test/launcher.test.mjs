import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn, spawnSync } from 'node:child_process';
import { once } from 'node:events';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, realpathSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { delimiter, dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { runtimeIdentity } from '../runtime.mjs';

const launcher = fileURLToPath(new URL('../tum-mcp.mjs', import.meta.url));

function invoke(args, environment = {}) {
  const directory = mkdtempSync(join(tmpdir(), 'tum-mcp-node-'));
  try {
    const result = spawnSync(process.execPath, [launcher, ...args], { encoding: 'utf8', env: { ...process.env, TUM_MCP_DATA_DIR: directory, ...environment } });
    result.files = readdirSync(directory);
    return result;
  } finally { rmSync(directory, { recursive: true, force: true }); }
}

test('version works without provisioning Python or modifying user configuration', () => {
  const result = invoke(['--version']);
  assert.equal(result.status, 0);
  assert.equal(result.stdout.trim(), JSON.parse(readFileSync(new URL('../../package.json', import.meta.url))).version);
});

test('bootstrap help is consistent, bounded and side-effect-free without Python', () => {
  for (const args of [['--help'], ['-h'], ['install', '--help'], ['setup', '--help'], ['update', '--help'], ['uninstall', '--help']]) {
    const result = invoke(args, { COLUMNS: '40', NO_COLOR: '' });
    assert.equal(result.status, 0, result.stderr);
    assert.match(result.stdout, /^TUM MCP  /);
    assert.doesNotMatch(result.stdout, /\x1b\[/);
    assert.ok(result.stdout.split('\n').every(line => line.length <= 40));
    assert.deepEqual(result.files, []);
  }
  const root = invoke(['--help']).stdout;
  const shared = JSON.parse(readFileSync(new URL('../help.json', import.meta.url)));
  for (const [title, rows] of Object.entries(shared.groups)) {
    assert.match(root, new RegExp(title));
    for (const [name] of rows) assert.match(root, new RegExp(`^${name}\\b`, 'm'));
  }
  assert.match(invoke(['update', '--help']).stdout, /^TUM MCP  tum-mcp update/);
});

test('serve fails closed before explicit setup', () => {
  const result = invoke(['serve']);
  assert.equal(result.status, 2);
  assert.match(result.stderr, /^Error: TUM MCP is not set up yet/);
});

test('SIGINT sent only to the Study launcher shuts down its runtime before exiting', {
  skip: process.platform === 'win32' && 'Native Windows uses console control events.',
}, async () => {
  const root = realpathSync(mkdtempSync(join(tmpdir(), 'tum-mcp-study-signal-')));
  const identity = runtimeIdentity();
  const generation = 'env-fixture';
  const control = join(root, 'runtimes', identity);
  const runtime = join(control, generation);
  const python = join(runtime, 'bin', 'python');
  const stopped = join(root, 'stopped');
  mkdirSync(dirname(python), { recursive: true });
  writeFileSync(join(control, 'current.json'), JSON.stringify({ schema: 2, identity, generation, python }));
  writeFileSync(join(runtime, '.tum-mcp-ready'), identity);
  writeFileSync(python, `#!/usr/bin/env node
const { writeFileSync } = require('node:fs');
process.once('SIGINT', () => {
  writeFileSync(${JSON.stringify(stopped)}, '');
  process.exit(0);
});
// When the test closes the input pipe, also exit on the unfixed launcher.
process.stdin.once('end', () => process.exit(1));
process.stdin.resume();
console.log('ready');
`, { mode: 0o700 });

  const child = spawn(process.execPath, [launcher, 'study'], {
    env: { ...process.env, TUM_MCP_DATA_DIR: root, PATH: `${dirname(process.execPath)}${delimiter}${process.env.PATH}` },
    stdio: ['pipe', 'pipe', 'inherit'],
  });
  const signal = AbortSignal.timeout(5000);
  const exited = once(child, 'exit', { signal });
  try {
    await Promise.race([once(child.stdout, 'data', { signal }), exited]);
    assert.ok(child.kill('SIGINT'), 'Study launcher exited before the interrupt');
    await exited;
    assert.ok(existsSync(stopped), 'Study launcher exited before the runtime handled SIGINT');
  } finally {
    child.stdin.end();
    rmSync(root, { recursive: true, force: true });
  }
});


test('update help and invalid update options do not provision a runtime', () => {
  const help = invoke(['update', '--help']);
  assert.equal(help.status, 0);
  assert.match(help.stdout, /--local/);
  assert.equal(invoke(['update', '--local', '--help']).status, 0);
  const invalid = invoke(['update', '--unknown-option']);
  assert.equal(invalid.status, 2);
  assert.match(invalid.stderr, /Usage:/);
});

test('uninstall validates scope and flags before package removal', () => {
  assert.equal(invoke(['uninstall', '--help']).status, 0);
  assert.equal(invoke(['uninstall', '--all', '--help']).status, 0);
  for (const args of [
    ['--client', ''], ['--client', 'unknown'], ['--unknown'], ['--host', 'unknown'],
    ['--client', 'cursor', '--all'], ['--client', 'claude', '--forget-credentials'],
  ]) {
    const result = invoke(['uninstall', ...args]);
    assert.equal(result.status, 2);
    assert.doesNotMatch(result.stderr, /not set up yet|npm installation/);
  }
});
