import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { currentPython } from '../runtime.mjs';

test('incomplete, corrupt, and mismatched runtime pointers cannot launch a backend', () => {
  const root = mkdtempSync(join(tmpdir(), 'tum-mcp-runtime-'));
  const previous = process.env.TUM_MCP_DATA_DIR;
  process.env.TUM_MCP_DATA_DIR = root;
  try {
    assert.equal(currentPython(), null);
    writeFileSync(join(root, 'runtime.json'), '{interrupted');
    assert.equal(currentPython(), null);
    const manifest = JSON.parse(readFileSync(new URL('../backend/manifest.json', import.meta.url)));
    const runtime = join(root, 'runtimes', manifest.wheelSha256);
    const python = join(runtime, process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
    mkdirSync(dirname(python), { recursive: true });
    writeFileSync(python, 'synthetic binary');
    writeFileSync(join(root, 'runtime.json'), JSON.stringify({ identity: manifest.wheelSha256, python }));
    assert.equal(currentPython(), null);
    writeFileSync(join(runtime, '.tum-mcp-ready'), 'unverified');
    assert.equal(currentPython(), null);
    writeFileSync(join(runtime, '.tum-mcp-ready'), manifest.wheelSha256);
    assert.equal(currentPython(), python);
    writeFileSync(join(root, 'runtime.json'), JSON.stringify({ identity: '../outside', python }));
    assert.equal(currentPython(), null);
  } finally {
    if (previous === undefined) delete process.env.TUM_MCP_DATA_DIR;
    else process.env.TUM_MCP_DATA_DIR = previous;
    rmSync(root, { recursive: true, force: true });
  }
});
