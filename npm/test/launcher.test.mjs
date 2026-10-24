import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const launcher = fileURLToPath(new URL('../tum-mcp.mjs', import.meta.url));

function invoke(args) {
  const directory = mkdtempSync(join(tmpdir(), 'tum-mcp-node-'));
  try {
    return spawnSync(process.execPath, [launcher, ...args], { encoding: 'utf8', env: { ...process.env, TUM_MCP_DATA_DIR: directory } });
  } finally { rmSync(directory, { recursive: true, force: true }); }
}

test('version works without provisioning Python or modifying user configuration', () => {
  const result = invoke(['--version']);
  assert.equal(result.status, 0);
  assert.equal(result.stdout.trim(), '0.4.0');
});

test('serve fails closed before explicit setup', () => {
  const result = invoke(['serve']);
  assert.equal(result.status, 2);
  assert.match(result.stderr, /SETUP_REQUIRED/);
});
