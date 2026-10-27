import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

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
    assert.match(result.stdout, /^TUM MCP  Help/);
    assert.doesNotMatch(result.stdout, /\x1b\[/);
    assert.ok(result.stdout.split('\n').every(line => line.length <= 40));
    assert.deepEqual(result.files, []);
  }
  assert.match(invoke(['--help']).stdout, /manage/);
});

test('serve fails closed before explicit setup', () => {
  const result = invoke(['serve']);
  assert.equal(result.status, 2);
  assert.match(result.stderr, /SETUP_REQUIRED/);
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
    assert.doesNotMatch(result.stderr, /SETUP_REQUIRED|npm installation/);
  }
});
