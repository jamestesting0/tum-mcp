import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

test('packed artifact contains the managed backend and excludes private workspace data', () => {
  const directory = mkdtempSync(join(tmpdir(), 'tum-mcp-pack-'));
  try {
    assert.ok(process.env.npm_execpath, 'Run through npm test to locate npm portably.');
    const result = spawnSync(process.execPath, [process.env.npm_execpath, 'pack', '--ignore-scripts', '--pack-destination', directory, '--json'], { encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr);
    const packed = JSON.parse(result.stdout)[0];
    const paths = packed.files.map(item => item.path);
    for (const name of ['lock.mjs', 'npm-command.mjs', 'package-manager.mjs']) assert.ok(paths.includes(`npm/${name}`));
    assert.ok(paths.includes('npm/backend/manifest.json'));
    assert.ok(paths.includes('npm/backend/requirements.txt'));
    assert.equal(paths.filter(path => /^npm\/backend\/.+\.whl$/.test(path)).length, 1);
    assert.ok(paths.includes('docs/tum-mcp.md'));
    assert.ok(paths.includes('docs/setup.md'));
    assert.ok(!paths.includes('docs/DESIGN.md'));
    assert.ok(!paths.some(path => path.startsWith('docs/local/')));
    assert.ok(!paths.includes('AGENTS.md') && !paths.includes('docs/tum-mcp-handoff.md'), 'Local agent notes must not enter the npm artifact.');
    assert.ok(!paths.includes('docs/credential-storage-options.md') && !paths.includes('docs/release-workflow.yml.example'), 'Background notes and draft workflows must not enter the npm artifact.');
    assert.ok(paths.every(path => !/(^|\/)(?:\.env|\.npmrc|session\.enc|credentials|output|tmp|node_modules)(?:\/|$)/.test(path)));
    assert.ok(!paths.some(path => path.startsWith('src/') || path.startsWith('tests/')));
  } finally { rmSync(directory, { recursive: true, force: true }); }
});
